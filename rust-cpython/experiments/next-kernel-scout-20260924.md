# Next kernel scout after URL quotation: `difflib.SequenceMatcher`

## Recommendation

**Profile, then prototype a guarded native matching-block kernel for the
public `difflib.unified_diff` path.** This is an independent hypothesis, not a
measured improvement or an accepted patch. It uses the pinned Rust workspace
and CPython FFI model without a new crate, source pin, or fixture. The earlier
`j2len` row-dictionary reuse probe is rejected and is not this candidate.

The choice follows the existing evidence. On one deterministic source diff,
the prior diagnostic attributed 0.131 of 0.158 instrumented seconds to
`get_matching_blocks` and 0.128 seconds to its 1,620
`find_longest_match` calls across 20 complete diffs. Its inner loop made
565,840 dictionary `get` calls. These overlapping `cProfile` times locate
work; they do not predict an uninstrumented speedup. Two registered,
digest-checked complete `unified_diff` workloads are already available.
The row-reuse candidate produced no useful complete-workload gain and raised
peak RSS, so native code must reduce more than dictionary allocation.

The ranked map also lists `tomllib`, but its existing profile covers only
133–798-byte local documents and establishes no application bottleneck.
Its exact error and callback contract makes a whole parser a larger first
change. `ipaddress` has no registered representative workload yet. Thus
`difflib` has the clearest measured location and nearest public-workload gate
among independent, no-new-dependency hypotheses. This priority is an
inference from the existing reports, not a measured cross-module ranking.

## Path, mechanism, and compatibility boundary

The exact public path is `difflib.unified_diff(a, b)` ->
`SequenceMatcher.get_grouped_opcodes()` -> `get_opcodes()` ->
`get_matching_blocks()` -> repeated `find_longest_match()` calls in pinned
`Lib/difflib.py`. A candidate would compute all matching blocks for one
eligible matcher in one native call, then return the same `Match` objects to
the existing Python opcode and formatting code. A call per line or per
candidate match would leave excessive Python/native crossings. The likely
bottleneck is repeated Python bytecode execution and Python dictionary
lookups in the longest-match search; the profile supports the location, while
the size of any removable cost remains unknown.

Limit the first path to exact `SequenceMatcher`, exact list/tuple sequences of
exact `str` elements, and `isjunk is None`. Keep the existing Python path for
callbacks, subclasses, custom sequences and elements. Preserve `autojunk`,
the 200-element threshold, popular-element filtering, leftmost tie-breaking,
matching blocks, opcodes, grouped opcodes, and rendered patch bytes.
`a`, `b`, `b2j`, `bjunk`, and `bpopular` are publicly reachable and mutable;
callers can also reuse a matcher after `set_seq1` or `set_seq2`. A native
index must reflect such mutation. The first design gate is a cheap,
demonstrably sound eligibility guard for the current Python-visible state.
If proving it requires copying or validating every element and index on
every operation, stop before implementing the kernel. Do not silently alter
the exposed matcher state contract for speed.

## First control and workload gate

First repeat a **quiet-host, uninstrumented self-comparison** of the last
accepted fork on `difflib_unified_mostly_equal` and
`difflib_unified_reordered`, then profile complete batches separately to
verify that matching still dominates both shapes. The existing reordered
case was slower under the rejected row-reuse probe, so both are required.
Use unchanged `Lib/test/test_difflib.py` and exact differential comparisons
of matches, opcodes, and emitted text for normal, repetitive, junk, autojunk,
ties, mutable state, and subclasses before any performance verdict.

The registered workloads in `benchmarks/workloads/difflib.py` already check
full patch digests and count complete diffs; `benchmarks/workloads/registry.py`
assigns 500 mostly-equal and 1,000 reordered diffs per normal run. No new
workload is needed for the first gate. A later acceptance pass should add
real source revisions, `context_diff`, `Differ`, `HtmlDiff`, and
`get_close_matches` to ensure the guard helps more than these generated
source-like inputs.

If a prototype survives correctness, compare it with the same-stage fork
without the patch in serial counterbalanced complete tasks. Record wall time
and kernel user/system CPU per diff, peak and retained process memory,
allocation counts/bytes when available, installed extension size, and cold
import. Calibrate control and candidate against themselves. The matched
upstream 3.16 build is the separate resource baseline. Current macOS
unique/proportional memory and allocation coverage is incomplete, so a
timing result alone cannot qualify upstream resource parity.

The expected tradeoff is fewer Python loop operations at the cost of an
additional native module, a possible copied index and temporary output
storage, and a higher compatibility and maintenance burden around visible
matcher state. No magnitude is claimed. **Stop** if the state guard cannot be
sound and cheap, if the eligible path rarely runs, if either complete diff
shape lacks a useful wall and CPU gain beyond self-noise, or if startup,
memory, allocation, or installed-size costs are material. Keep a candidate
only after exact public behavior and the complete-workload/resource gates
pass.
