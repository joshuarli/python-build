# `difflib.unified_diff` one-shot native dispatch contract, 2026-09-24

## Verdict

**Reject a one-shot matching-block cache injection as a transparent optimization
of the public `unified_diff` generator under a cheap guard.** A small guard can
cover ordinary, synchronous calls with exact immutable `tuple[str]` inputs,
but it cannot guarantee the pinned generator's behavior when Python executes
between its matching steps. Exact `list[str]` inputs, which are both registered
workloads, additionally expose changes made after a snapshot and during the
matching loop. Trace callbacks give a deterministic counterexample. A signal
handler or finalizer can likewise run Python at an allocation or interpreter
checkpoint. Keeping all such observations would require the Python matching
loop's callback/exception checkpoints, eliminating the proposed one-shot
boundary. Do not write or benchmark a native kernel on the basis of this
contract. A narrower, explicitly changed behavior contract would require an
upstream scope decision.

This does **not** reverse the snapshot-cost finding. That measurement says
copying and scanning the benchmark inputs is affordable enough for further
investigation; it does not establish semantic eligibility. The earlier
`difflib-guard-audit-20260924.md` separately rejects the public
`SequenceMatcher` boundary because its stored state is mutable.

## Pinned evidence

- Base commit: `4ed695323de9f751d84609d6d4d0e7f55781ebe5`.
  Installed fork: `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`.
  Its `lib/python3.16/difflib.py` SHA-256 is
  `3a5bb23205537cd9a2a68255b4ca00d710573e0a18129b0166351bf126875cf3`.
  The unchanged installed `test/test_difflib.py` SHA-256 is
  `1cc1876aebc3bcf206d1dfc5ad0254e5957fd0e542c515714cf08435432bdb46`.
- Source pin: `rust-cpython/sources.lock.json`, CPython commit
  `b812b4a7b9efaca46b98544a8633b7d7e454166b`. Source read from the
  verified `rust-cpython/work/source-inspect/cpython-b812b4a7b9efaca46b98544a8633b7d7e454166b/Lib/difflib.py`.
- The focused [diagnostic](difflib_one_shot_contract_probe.py) ran on the
  installed interpreter. `/usr/bin/time -l` reported 0.03 s elapsed,
  0.02 s user CPU, 0.00 s system CPU, 20,905,984-byte maximum RSS and
  10,682,824-byte peak physical footprint. One process; no subprocess or
  benchmark was launched. These are process-level resource observations,
  not native candidate measurements.

## Observable phase order

`unified_diff` is a generator (`Lib/difflib.py:1101`). Calling it performs no
body work: inputs and globals are read on its first `next()`. The order then is:

1. `color` is evaluated, then `can_colorize()` and `get_theme()` choose `t`.
2. `_check_types()` runs. It inspects only element zero of each nonempty
   input and then checks filename/date/lineterm argument types. A later
   bytes element passes this check; an unhashable later element can fail in
   matcher construction. Earlier validation in a new path would change the
   failure and its timing.
3. `SequenceMatcher(None, a, b)` is looked up as a module global and
   constructed. The default `isjunk=None` and `autojunk=True` are part of
   this call. The constructor builds `b2j`, `bjunk`, and `bpopular` from the
   then-current `b`, and retains `a` and `b` by reference.
4. `.get_grouped_opcodes(n)` is called; its generator starts on the `for`'s
   first advancement. It calls `get_opcodes()`, `get_matching_blocks()`, and
   `find_longest_match()`. `Match(...)` and later `Match._make(...)` are
   dynamically resolved. Grouping can yield before all groups are consumed.
   On a changed input, this work completes for the first group before the
   first `--- ` header is yielded.
5. Headers, hunk ranges, and output lines are rendered in Python. The
   renderer slices the original `a` and `b` afresh as it proceeds after each
   yield. Mutating `a[0]` after the first header changes the later removed
   line; mutating before the first `next()` can change matching itself.

`n` participates in the existing grouped-opcode generator. Filename/date
formatting, color attributes, and line interpolation stay at their existing
yield points. A kernel that pre-renders text, moves `_check_types`, snapshots
at generator creation, or computes all groups before constructing the matcher
changes observable errors or callback order.

## The smallest candidate boundary and its guard

The only plausible insertion is **inside `unified_diff`, after its existing
theme selection, `_check_types`, and construction of the local matcher, but
before the existing `for group in matcher.get_grouped_opcodes(n)`**. The
candidate would compute the exact matching-block list once and set only the
local matcher's `matching_blocks` cache. It would leave `get_opcodes`,
`get_grouped_opcodes`, `_format_range_unified`, color handling, and rendering
in Python. It must never modify the public `SequenceMatcher` implementation
or a matcher passed in by a caller.

At minimum, a speculative fast route would need identity guards against
the captured originals of the module global `SequenceMatcher` and `Match`,
`Match._make`, and these `SequenceMatcher` methods: `__init__`, `set_seqs`,
`set_seq1`, `set_seq2`, `_SequenceMatcher__chain_b`, `find_longest_match`,
`get_matching_blocks`, `get_opcodes`, and `get_grouped_opcodes`. All checks
must be made **at first iteration**, after construction and immediately
before injection; on any failure the original matcher must enter the
existing `for` untouched. The guard must also require an exact matcher
instance, its original `a is a` and `b is b`, `isjunk is None`,
`autojunk is True`, empty result caches, exact tuple or list containers, and
every element's type exactly `str`. Type checks on a list have to take a
stable reference snapshot; `_check_types` alone is insufficient. A callable
patched on the class may change behavior even if the global class object is
unchanged. A patched `Match` matters even if the native triples have the
right integers.

These guards are **necessary, not sufficient**. A patched constructor can
change state then restore its method identity; checking identities afterward
cannot attest to the history. More directly, the diagnostic changes `a[1]`
from `X` to `B` at the pinned `find_longest_match` line 380, for `a =
["A\\n", "X\\n"]`, `b = ["A\\n", "B\\n"]`. The Python path emits no
diff; a one-shot computation over an earlier snapshot would emit a change.
All containers and elements were exact built-in types before the callback.
`sys.gettrace()` / `sys.getprofile()` can detect the common trace/profile
forms, but do not exclude signal handlers, finalizers, or transient changes
made within construction. A one-shot native call also shifts where pending
signals and exceptions are handled relative to Python's bytecodes. Thus no
cheap predicate of current object identities and types proves an equivalent
execution history or excludes future reentrancy.

An exact tuple of exact strings removes input mutation, but does not freeze
the module's `Match`, matcher methods, color helpers, or other Python state
that the original loop reads between calls. Freezing these dependencies or
promising a quiescent callback interval would be a new contract. The
registered workloads use lists, so a tuple-only route would not qualify
them in any event.

## Native ABI if the contract were deliberately narrowed

For a future explicit pure-input contract, the native boundary should accept
two owned, stable sequences of exact Python `str` references and the fixed
`isjunk=None`, `autojunk=True` policy. It must implement the pinned
`SequenceMatcher` tie break, popularity threshold (`len(b) >= 200`, count
strictly greater than `len(b)//100 + 1`), extension and block coalescing
rules. It should return an ordered sequence of `(a_start, b_start, size)`
integer triples including the terminal `(len(a), len(b), 0)`; Python would
construct the pinned `Match` values and inject the private cache. It must
report allocation failure as `MemoryError`, without silently falling back
after partial side effects or changing exception order. No `n`, filenames,
color theme, text rendering, or Python-owned matcher state should cross the
ABI. Retaining snapshots, a `b2j` equivalent, dynamic rows, triples, and a
Python cache at once can cause O(len(a) + len(b) + index + output) extra live
memory, with poor cases much larger than the input. Worst-case index/row
growth and installed extension bytes need explicit gates before adoption.

## Required evidence before any reconsideration

- Decide explicitly whether callback timing and in-loop mutation may change.
  If not, stop here; a cheap one-shot dispatch is unsuitable.
- If the contract is narrowed, add targeted tests adjacent to
  `Lib/test/test_difflib.py` for generator creation versus first `next()`,
  theme/type/error order, patched `SequenceMatcher`, `Match`, and each
  matcher dispatch method, exact tuple/list and mixed-element fallback,
  `isjunk`/`autojunk` behavior, mutation before first `next()` and after
  each header/hunk yield, signal/trace behavior promised by that contract,
  and no partial-cache publication on errors. Keep the upstream test file's
  existing cases unchanged until a candidate exists.
- Only then compare exact matching blocks, opcodes, and complete rendered
  output, including ties and 200-element popularity cases, on the installed
  interpreter. Run the unchanged `test.test_difflib`, the two registered
  complete workloads, paired wall and kernel CPU, peak/unique memory where
  supported, allocations, and installed size. Stop a candidate if either
  workload lacks useful full-task gain or memory/size exceeds the upstream
  acceptance gate in `rust-for-cpython.md`.

No build, native code, benchmark, dependency, production source, or existing
test was changed in this lane. The diagnostic is a behavioral probe, not a
test suite for a kernel.
