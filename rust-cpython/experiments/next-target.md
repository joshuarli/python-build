# Next independent public stdlib target: difflib

## Decision and scope

Scout `difflib.SequenceMatcher` for a guarded native matching kernel used by
`difflib.unified_diff` and `context_diff`. This is independent of the open
zlib backend decision: it consumes sequences of Python objects and produces
matching blocks/opcodes; it performs no compression or archive I/O. No
implementation or performance claim follows from this scouting pass.

The ranked map places `difflib` at #2 after zlib, ahead of `ipaddress` (#4)
and `zipfile` (#7). ZIP reads and imports in the zlib probe were mixed, and a
ZIP member path would compound that backend question. `ipaddress` remains a
reasonable later candidate, but this pass found a directly visible matching
loop on a complete source diff.

## Callers and proposed boundary

`Lib/difflib.py` constructs `SequenceMatcher` in `unified_diff`,
`context_diff`, `Differ` (including intraline comparisons), `HtmlDiff`, and
`get_close_matches`. `get_grouped_opcodes()` calls `get_opcodes()`, which
calls `get_matching_blocks()` and repeatedly `find_longest_match()`.
`set_seq2()` builds `b2j`, `bjunk`, and `bpopular`; `get_matching_blocks()`
caches `Match` records. The relevant unchanged suite is
`Lib/test/test_difflib.py`.

Begin with an exact built-in `str` line sequence fast path, guarded by exact
`SequenceMatcher` type, exact list/tuple containers, `isjunk is None`, and
unmodified matching state. Return the same `Match` records to the existing
Python `get_opcodes()` and formatting code. Keep arbitrary hashable elements,
callbacks, sequence subclasses, and `SequenceMatcher` subclasses on the
existing Python path. A candidate could move the `find_longest_match` inner
loop into one native call per complete `get_matching_blocks()` operation;
per-line or per-element FFI calls would erase much of the opportunity.

The boundary needs more design before code: `b2j`, `bjunk`, `bpopular`, `a`,
and `b` are Python-visible mutable attributes, and callers may change them
between construction and matching. A native index cannot silently ignore
those mutations. Either prove a cheap guard for the exact current state or
decline the fast path. Preserve `set_seq1`/`set_seq2` cache invalidation and
reuse. No new crate is proposed; use the pinned Rust workspace and existing
CPython FFI model if implementation proceeds.

## Diagnostic evidence

On 2026-09-24, the existing `stage-no-rust/bin/python3.16` processed a
2,103-line installed `difflib.py` source file against a deterministic edited
copy: one changed line every 53 lines, two inserted lines, three deleted
lines. Twenty warm complete `unified_diff` operations produced the same
SHA-256 each time:
`304f0e4ef8c2c0091a4e8ae20868c16d8f35d0f0af7aa246da18bf2b604058ec`.
`cProfile` recorded 744,741 calls and 0.158 s of **instrumented** elapsed
time for all 20 operations. Cumulative time was 0.131 s in
`get_matching_blocks()` and 0.128 s in its 1,620
`find_longest_match()` calls; `__chain_b()` accounted for 0.021 s.
The inner loop made 565,840 dictionary `get` calls. The profiled command's
`/usr/bin/time -l` reported 0.18 s kernel user CPU, 0.01 s system CPU,
25,214,976 bytes maximum RSS, and 0.20 s wall time for the entire process.

This is location evidence only. `cProfile` distorts Python call costs; the
fixture is one source file and one edit pattern, not a representative workload
set. The process totals include startup, fixture preparation, and profiling.
This scouting diagnostic predates the first candidate. The row-dictionary
reuse probe now has serial paired timing and a rejection recorded in
`difflib-kernel-probe.md`; there is still no upstream comparison, allocation
result, or memory parity result for a native difflib kernel.

## Workload and semantic gates

Use complete `unified_diff`/`context_diff` tasks over real source revisions
and generated text, plus `get_close_matches`, `Differ`, and `HtmlDiff` cases
where the candidate guard applies. Include short files, large files, mostly
equal files, reordered blocks, repetitive lines, and pathological quadratic
inputs. Compare cold import and steady work separately. Preserve emitted
text bytes, matching blocks, opcodes, grouped opcodes, exception behavior,
and callbacks against the unmodified no-Rust fork. Check unchanged
`test_difflib.py` and differential cases for `autojunk` threshold at 200,
popular elements, leftmost tie-breaking, empty inputs, junk callbacks,
non-string hashable elements, custom sequences, subclasses, and mutations of
the exposed matcher state. The comments above `find_longest_match` explain
why a common-prefix shortcut changes results.

The first prototype is bounded to one module and one guarded path. Expect a
small Rust extension and focused CPython test run; a full optimized build
with PGO, source patch integration, upstream-matched comparisons, and broad
application benchmarks cost much more and should follow only if the kernel
works. Record native extension bytes and build time alongside runtime CPU,
wall, peak and retained memory, and allocation counts. Current macOS unique
memory and allocation tooling is incomplete, so final upstream parity cannot
yet be certified.

The first two deterministic public workloads now live in
`benchmarks/workloads/difflib.py` and are registered as
`difflib_unified_mostly_equal` and `difflib_unified_reordered`. They use
generated source-like revisions with pinned input and patch digests. They
establish a repeatable comparison surface; they do not substitute for real
source revisions or the full semantic suite above.

The first pure-Python row-dictionary reuse candidate passed differential
checks but produced no useful public-path gain and increased peak RSS; it is
rejected. That result rules out the row-reuse idea, not the broader native
matching-kernel hypothesis. Any further difflib candidate must identify a
different mechanism and keep this rejected candidate as its control evidence.

**Stop** if exact semantics require broad public state replacement, the guard
rarely fires on complete workloads, kernel savings disappear at the public
API, or a meaningful workload regresses in time or memory. **Keep** only after
unchanged tests and differential cases pass and serial paired complete tasks
show a repeatable useful wall/CPU gain beyond self-comparison noise, with no
material memory, allocation, startup, or installed-size regression against
the matched controls. Until then, this is a target hypothesis.
