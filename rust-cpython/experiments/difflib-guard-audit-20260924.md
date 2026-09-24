# `difflib` native guard feasibility, pinned CPython 3.16

## Decision

**Stop the proposed native matching-block kernel at the public
`SequenceMatcher.get_matching_blocks()` boundary.** Exact `SequenceMatcher`,
exact list/tuple inputs, exact `str` elements, and `isjunk is None` do not
establish a cheap, sound snapshot of the Python-visible matching state.
The matcher stores its sequences, index, junk set, result caches, and methods
in mutable Python-visible state. A native computation from a separately
cached index can disagree with the pinned Python algorithm after ordinary
mutation. An identity or length check cannot rule that out; a structural
check and element validation on every uncached operation defeats the
proposed cheap guard, and even that needs care around callback and exception
behavior. Do not implement or time this matcher-level kernel on the strength
of the scout's type restriction.

**A separate, conditional experiment remains plausible:** an internal
one-shot path for `unified_diff` using the matcher it creates locally. It
should retain the existing Python matcher path when `SequenceMatcher` or
relevant methods have been replaced, or when the inputs are not exact
list/tuple containers of exact `str` elements. The path would make stable
tuple snapshots before native matching, then keep the existing grouped
opcode and rendering behavior. This is a different contract and cost model
from accelerating every eligible public matcher. It is a hypothesis, not an
implementation recommendation or a proven compatibility result. If its
snapshot and validation costs consume the available headroom, keep the
Python path.

## Evidence and exact boundary

- Source examined: verified extracted fork source
  `rust-cpython/work/source-inspect/cpython-b812b4a7b9efaca46b98544a8633b7d7e454166b/Lib/difflib.py`;
  SHA-256 `3a5bb23205537cd9a2a68255b4ca00d710573e0a18129b0166351bf126875cf3`,
  matching the prior probe's staged source. Pin is
  `rust-cpython/sources.lock.json` (`b812b4a7b9efaca46b98544a8633b7d7e454166b`).
- `set_seq1` and `set_seq2` (lines 197–265) invalidate `matching_blocks`
  and `opcodes` only when passed a different object by identity. `set_seq2`
  also rebuilds `b2j`, `bjunk`, and `bpopular`; mutating a retained list or
  calling `set_seq2` with that same list does not rebuild the index.
- `__chain_b` (lines 267–304) makes an ordinary dict of ordinary lists and
  ordinary sets. `find_longest_match` (lines 306–420) reads `self.a`,
  `self.b`, `self.b2j`, and `self.bjunk` afresh. Its inner loop consumes the
  index's list entries directly, including their order. Its extension loops
  read the current sequence elements and junk membership.
- `get_matching_blocks` (lines 422–491) returns the existing
  `matching_blocks` object when set, calls `self.find_longest_match` for each
  region otherwise, then stores a mutable list of `Match` values. `get_opcodes`
  (lines 493–546) likewise returns or builds a mutable cached list.
  `get_grouped_opcodes` (lines 548–596) edits its local reference to that
  opcode list while producing groups. A new native route must respect those
  cache objects and dispatch points, not merely produce equivalent fresh
  matches for untouched instances.
- `unified_diff` (lines 1101–1175) is a generator that creates a matcher
  inside iteration, calls `get_grouped_opcodes`, and later reads the original
  `a` and `b` for output lines. `_check_types` (lines 1271–1287) checks only
  the first element of each sequence, so it does not certify every element.
  The registered `benchmarks/workloads/difflib.py` inputs are generated
  `list[str]` revisions with 512 or 396 source-like lines and digest-check
  complete emitted diffs. They create a fresh matcher per diff; they do not
  exercise public matcher reuse.

## Why a public matcher guard is expensive

The usual API permits `set_seq1`, `set_seq2`, junk callbacks, arbitrary
hashable elements, and cached reuse. Exact `str` elements remove user-defined
hash/equality callbacks for those elements, but they do not make the matcher
or its containers private. The following are observable in this pinned
implementation, even where they are not specifically promised as a formal
API contract:

| State or dispatch | Mutation the Python path observes | Why a cheap native check fails |
| --- | --- | --- |
| `a`, `b` | Reassign an attribute, mutate a retained list, or replace one exact `str` without changing length. | Identity and length cannot prove element identity or the relation between `b` and its older `b2j`. |
| `b2j` | Replace a mapping, add/remove a key, or edit/reorder a value list in place. | Dict identity and size miss edits; a dict version would miss nested list edits and is not a suitable Python-level contract. The Python loop can use even stale or deliberately edited indices. |
| `bjunk` | Add/remove an element or replace the set. | It changes prefix/suffix extension without changing `b2j`. |
| `bpopular` | Mutate or replace after `__chain_b`. | `find_longest_match` does not read it; a native route must not treat it as a live popularity policy. It matters at the public state and rebuilding boundary, not as an extra current-match guard. |
| `matching_blocks`, `opcodes` | Replace or edit cached lists, including between calls. | The Python methods return/use the current objects. Recomputing would change behavior. |
| Methods and globals | Patch `find_longest_match`, `get_matching_blocks`, `get_opcodes`, `get_grouped_opcodes`, `SequenceMatcher`, or `Match`; subclass a matcher. | Dynamic dispatch and global lookup are visible in the Python path. Exact instance type alone does not establish unchanged class methods or globals. |

`isjunk` and `autojunk` can also be changed after indexing. Their *current*
values are not read by `find_longest_match`; the already-built index and
`bjunk` determine that operation. A guard that recomputes the index from the
current options would itself change semantics. Conversely, the next genuine
`set_seq2` rebuild uses the then-current options. The result is a stateful
contract, not just an algorithm over two current sequences.

The obvious complete validation requires walking both sequences to confirm
exact element types, walking every `b2j` key and index list (and checking
their order, bounds, and types), checking junk membership, and examining
cache and method state. It costs at least linear work in the data/index size
per uncached operation and still has to reproduce behavior of deliberately
inconsistent state and malformed entries, including Python exceptions. A
private generation counter would not see direct Python container edits;
proxies or a changed public attribute contract would be a compatibility
change. CPython's GIL only prevents concurrent Python execution during a
chosen native section; it does not repair stale state before entry, nor by
itself cover reentrant callbacks or signals at allocation/dispatch points.

## Narrower public diff boundary and cost

`unified_diff` constructs and consumes a fresh matcher locally, so ordinary
callers cannot edit that matcher's `b2j`, `bjunk`, or caches between its
construction and matching. This removes the main state guard problem for
that call, provided the optimized route checks the callable/class dispatch
it would otherwise skip. Module globals and class methods remain patchable;
the generator's lazy execution and order of type checking, color setup,
matching, first yield, and line rendering must remain observable. Exact
tuple inputs are stable without a sequence copy. Exact list inputs, including
both registered workloads, need tuple snapshots or another proven stable
view if native matching assumes fixed elements; copying costs O(len(a) +
len(b)) references and temporary memory for each complete diff. An exact
`str` scan also costs O(len(a) + len(b)). The standard `__chain_b` already
does O(len(b)) work, so the additional copy/scan is not automatically fatal,
but its price must be measured against full patch latency and CPU. The
native index/output may add further memory.

Snapshots preserve the sequences used by matching, while the existing
renderer must still read original `a` and `b` after yields to retain the
current generator behavior. Mutation between yields therefore remains
visible in rendered lines. Mutation during matching through signals,
finalizers, or other reentrancy is a difficult exactness edge: a snapshot
can differ from the current Python loop's live reads. A proposed implementation
must either prove that its chosen boundary preserves these cases, or make the
accepted semantic restriction explicit before it is considered compatible.
The safe current default for such cases is the Python path. `context_diff`
uses the same fresh-matcher pattern but needs its own public output check;
`Differ` and `get_close_matches` have distinct matcher reuse and callbacks.

## Smallest next empirical check

After the concurrent URL comparison is finished and the host is quiet, run
one **no-native, no-source-change cost check**: on each registered complete
`unified_diff` workload, pair the normal task with the same task that, once
per diff immediately before invoking `unified_diff`, creates `tuple(a)` and
`tuple(b)` and scans both snapshots with `type(x) is str`. Keep the usual
full-output digest check and report wall and kernel user/system CPU per diff,
plus peak RSS, in serial counterbalanced pairs with control self-comparison.
This is a proxy for a possible per-diff snapshot/eligibility
cost, not a native speed estimate: it adds the operations beside the Python
matcher rather than replacing its work. Stop the one-shot route if that cost
already consumes the plausible matching headroom or creates material memory
growth. If it remains small, next specify a private one-shot dispatch and
its monkeypatch/reentrancy contract before writing a native kernel.

This audit made no source change, ran no benchmark or tests, and fetched no
input. The recommendation is static and does not claim a measured speedup.
