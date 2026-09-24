# macOS CPython 3.16 allocation feasibility (2026-09-24)

## Recommendation

Keep the allocation gate **unavailable** for the pinned Rust-for-CPython 3.16
build today. A dependency-free route is plausible: use the installed Xcode
**Allocations** instrument for native heap and anonymous-VM events, and a
separate, optional CPython allocator-domain observer for Python request counts
and bytes. First run the small export-and-coverage probe below. Until it proves
that counts, requested bytes, and child coverage can be extracted and reconciled,
these are diagnostic candidates, not benchmark metrics. Do not reuse the locked
Memray wheel or label `tracemalloc` snapshots as lifetime allocations.

This lane inspected interfaces and installed tools only. It ran no allocation
recording, workload, build, package install, or performance test. No CPython
3.16 stage or Memray installation exists in this worktree, so compatibility and
overhead remain unmeasured.

## Established boundary

| Path | What is established | Remaining limit |
| --- | --- | --- |
| Existing Memray harness | `benchmarks/harness/allocations.py` invokes `memray run --native --trace-python-allocators`, obtains count and requested-byte totals, and can aggregate separate fork capture files. It runs outside the timing pass. | Memray's current supported-environments page lists CPython 3.8–3.14, although macOS arm64 is supported. The repository locks `memray==1.20.0` only as a `cp314` x86_64 musl wheel. No compatible 3.16 binary or import proof is present. `--follow-fork` cannot follow `exec`; macOS `multiprocessing` defaults to spawn. A successful parent capture would not prove whole-tree coverage. Native stacks may be incomplete on macOS. |
| `tracemalloc` | A standard-library option for live Python-traced blocks, snapshot differences, and current/peak traced bytes. It can help localize retained Python memory without a package. | Snapshots contain surviving blocks, not lifetime allocation events. Freed and reallocated blocks disappear; differences are net changes. It omits direct Rust/C system allocations unless those callers explicitly register them with Python's tracer. It cannot satisfy native-plus-Python counts/bytes per operation. |
| CPython allocator hooks | `PyMem_GetAllocator`/`PyMem_SetAllocator` expose RAW, MEM, and OBJ domains; a wrapper can count successful requests and requested bytes. The 3.16 C-API contract requires thread safety and, after initialization, wrapping the previous allocator. | An observer installed after initialization misses startup. RAW/MEM/OBJ domain counts can represent nested underlying work; report each domain and never sum them blindly. Arena hooks see arena requests, not every Python object. Direct Rust/C `malloc` and anonymous mappings bypass these hooks. An early-start observer needs a diagnostic build or launcher change and must preserve allocation semantics. |
| Apple Allocations | Xcode 26.6 is installed. `xctrace list templates` lists `Allocations`; `xctrace record --template Allocations --launch -- ...` and `xctrace export --toc/--xpath` are supported by the installed CLI. Apple's documentation says this instrument tracks size and count for heap and anonymous-VM allocations. | No trace was recorded here. The export schema, whether it exposes *lifetime events and requested bytes* usable as stable machine-readable totals, short-lived spawn-child coverage, Rust/system call attribution, permissions, file size, and observer overhead are unproved. Heap `malloc` backing Python arenas overlaps Python-domain activity; native and Python event totals must remain separate. |

`heap` and `leaks` inspect retained native allocations, so they cannot replace
lifetime counts. `MallocStackLoggingNoCompact` preserves freed allocation
history for diagnosis but can produce large logs and is not itself a bounded,
normalized per-operation benchmark. `xctrace` is installed tooling, not a new
project dependency; using it for an optional experiment changes no source pin.

## Smallest decisive next check

In an isolated follow-up lane with the exact pinned 3.16 interpreter available,
launch a short deterministic fixture under `xctrace record --template
Allocations --launch -- <python3.16> <fixture>`, writing the trace outside the
stage tree. Give the fixture known batches of Python object allocations,
`ctypes` calls to `malloc`/`free`, an anonymous mapping, and one `spawn` child
which repeats a distinguishable batch. Export the table of contents and relevant
tables with `xctrace export`; retain the trace, raw XML, fixture, and exact
interpreter/source identities. Keep the probe below 30 CPU seconds of workload
and 512 MiB fixture RSS, with a hard wall timeout. Measure the whole command
tree's user/system CPU, elapsed time, peak RSS, and process count; report any
unavailable memory field as missing. Record trace size. Xcode's recording and
export processes may exceed the fixture's budget; stop if they do.

The probe passes only if the exported records permit an unambiguous count and
requested-byte sum for the controlled native batches, identify the anonymous
mapping separately, and show whether each child has a complete lifetime record.
Compare the exported totals with known requests, accounting for profiler and
interpreter startup activity by using marked phases or deltas. A live-only total,
an undocumented/nonrepeatable XML field, missing child, or ambiguous byte
meaning fails the gate. Record a second self-comparison to bound trace variance.

If that passes, add a diagnostic-only CPython RAW/MEM/OBJ wrapper in the
experimental lane, using the existing allocator as the backend and atomic
counters without allocating in callbacks. Validate zero-size, calloc overflow,
realloc success/failure, threads, and startup coverage before comparing control
and candidate. Check that the wrapper does not alter correctness and report its
overhead in a separate pass. For a workload with `exec`/spawn children, arrange
explicit observation for every interpreter process or mark allocation coverage
incomplete. Keep separate `native_heap`, `native_vm`, and `python_raw/mem/obj`
metrics; do not add the overlapping streams into one allocation total. Normalize
each by the workload's semantic operation count. Record capture/process count,
missing descendants, profiler version/settings, interpreter identity, cache
policy, raw observations, and self-comparison noise. Profiled elapsed time is
never a speed result.

If export or child coverage fails, the bounded recommendation is to leave
native-plus-Python allocation counts unavailable while using `tracemalloc` and
Apple tools for targeted diagnostics. A Memray release that officially supports
3.16 would require a separately approved dependency/lock decision and a direct
compatibility probe; it is not a shortcut around spawn coverage.

## Evidence

- Repository contract: `rust-for-cpython.md` requires a separate allocation
  pass with native/system and Python activity distinguished, counts and bytes
  per operation, and no timing inference from profiled runs.
- Existing implementation: `benchmarks/harness/allocations.py`,
  `benchmarks/harness/runner.py`, and `benchmarks/inputs.lock.json`.
- Local read-only checks: `python3 --version` reported 3.13.7; `uname -sm`
  reported Darwin arm64; `xcodebuild -version` reported Xcode 26.6;
  `xcrun xctrace list templates` listed Allocations; `xcrun xctrace help
  record/export` documented launch and XML export. No stage or Memray files
  were found in this assigned worktree. These commands were lightweight;
  no substantial command needed CPU/memory accounting.
- [Memray supported environments](https://bloomberg.github.io/memray/supported_environments.html)
  documents Python versions, macOS stacks, fork, and `exec` limits;
  [Python allocator tracing](https://bloomberg.github.io/memray/python_allocators.html)
  explains `pymalloc` and `--trace-python-allocators`.
- [CPython 3.16 `tracemalloc`](https://docs.python.org/3.16/library/tracemalloc.html)
  describes live snapshots and traced blocks;
  [CPython memory C API](https://docs.python.org/3.16/c-api/memory.html)
  specifies allocator domains and wrapper requirements.
- [Apple's memory tools](https://developer.apple.com/documentation/xcode/gathering-information-about-memory-use)
  describe Allocations coverage; [malloc debugging features](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/ManagingMemory/Articles/MallocDebug.html)
  describe stack logging.
