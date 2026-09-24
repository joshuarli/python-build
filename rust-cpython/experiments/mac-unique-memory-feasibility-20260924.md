# Native macOS unique-memory and allocation feasibility (2026-09-24)

## Decision

Run one bounded **region-accounting feasibility probe** before adding a new
benchmark field. The installed macOS 26 SDK exposes resident private and shared
page counters per VM region through `proc_pidinfo(PROC_PIDREGIONINFO)`. Those
counters might support a useful *sampled mapped-private-resident estimate* for
our own CPython child. They do not establish exact USS, and the inspected APIs
do not expose the per-physical-page map counts needed for PSS. Keep USS/PSS
unavailable until a probe validates semantics and access; do not relabel the
existing physical footprint. The allocation pass needs a separate 3.16
compatibility decision, since current upstream Memray documentation lists
supported CPython versions only through 3.14.

No implementation, dependency, build, benchmark, or diagnostic was run in this
lane. These are interface findings and a proposed next experiment, not measured
performance or proof of a usable metric.

## What each number would mean

| Quantity | Available evidence and limit |
| --- | --- |
| RSS | `benchmarks/harness/process.py` already samples each process's resident bytes and sums the discovered tree. Shared pages can be counted once per process; process-tree reads are sequential. |
| Physical footprint | `benchmarks/harness/macos_resource.py` reads the kernel's per-process charged dirty-memory ledger, including its exact lifetime peak for the **root**. `process.py` samples and sums current charges for the discovered tree. The ledger can charge memory outside a process's mappings and includes compressed and other sub-ledgers, so it is neither private resident nor USS/PSS. There is no exact tree lifetime peak. |
| Mapped private resident | `sys/proc_info.h` declares `proc_regioninfo.pri_private_pages_resident`, `pri_shared_pages_resident`, `pri_pages_resident`, and `pri_pages_shared_now_private`. Summing leaf-region private resident counts times the task page size is a *candidate estimate*; validate submaps, aliases, COW, totals, and permissions first. The `mach/vm_region.h` warning calls sharing modes loosely defined, best-effort accounting subject to change. A mapped-private estimate omits charged memory outside mappings and might double-count aliases. |
| USS | Strictly the resident physical pages mapped only by that process, counted once even with multiple mappings. The inspected public region counters do not establish this physical-page identity or global map count. A region's `SM_PRIVATE` label is not enough: COW regions can contain both shared and private pages. |
| PSS | Each resident physical page divided by the number of processes mapping it. No inspected public SDK interface supplies page-by-page cross-process map counts. Dividing a region's shared bytes by its region reference count or the workload child count would be an unsupported approximation; system libraries are shared beyond the workload tree. |
| Peak and retained | The footprint ledger has an exact per-root lifetime maximum, but mapped-private, RSS, and current footprint over a tree are sampled snapshots. Short-lived children, peaks between samples, escaped descendants, and PID races remain possible. “Retained” means an explicitly timed post-workload snapshot while the same process is still alive; exit-time inspection cannot recover freed pages. |

The current libproc sampler checks PID start identity and repeats process-table
reads to reject detected membership changes. Region enumeration adds more
sequential calls, so the same identity checks are necessary but cannot make a
tree snapshot atomic. A missing/denied region must yield `null`, not zero or a
partial sum passed as complete.

## Candidate native interfaces, in priority order

1. **Sparse `proc_pidinfo` region scan, diagnostic first.** The installed SDK
   defines `PROC_PIDREGIONINFO`, `proc_regioninfo` with address, size, depth,
   flags, private/shared resident counts, and `PROC_REGION_SUBMAP`; `libproc.h`
   declares `proc_pidinfo`. Probe one owned, long-lived CPython 3.16 process
   at quiescent checkpoints, walking its address space and descending submaps
   correctly. Cross-check total resident pages against `TASK_VM_INFO` or
   current libproc RSS, plus `vmmap -summary` where permitted. A field can be
   named `sampled_mapped_private_resident_bytes` only if counts are stable and
   reconcile for controlled anonymous allocation, shared mapping, COW after
   fork, and process-local alias cases. Even then it remains an estimate,
   separate from USS. Each process requires its own scan, and a whole-tree
   sum can double-count shared aliases if classification is wrong.
2. **`vmmap` / `footprint` checkpoint audit.** Apple's `vmmap` guidance
   distinguishes private, COW, and shared VM regions; the local `footprint(1)`
   manual can break down private and shared dirty VM objects, but says that
   object analysis is expensive and cannot run in real time. Use these tools
   to interpret one checkpoint, not as a 50 ms sampler or a PSS oracle.
   `footprint`'s default ledger value and its VM-object view can differ.
3. **Mach task region APIs.** `mach_vm_region` with extended info exposes
   resident, COW-private, share-mode, and reference-count fields, but the
   region-mode warning still applies. Accessing a separate process's task port
   can require debugger permission/entitlements and is restricted for protected
   processes. Prefer the libproc path already used by this harness; do not
   require SIP changes, root, or signing changes for a benchmark gate.

`task_vm_info` has resident and footprint values, but no USS/PSS field. The
`footprint(1)` manual explicitly warns that dirty VM-object accounting is
costly, and its kernel ledger can include nonmapped charges. `vmmap` sharing
mode alone describes a region, not every page in it. Neither tool turns a
root lifetime peak into an exact concurrent tree peak.

## Allocation counts on CPython 3.16

The existing `benchmarks/harness/allocations.py` runs Memray separately with
`--trace-python-allocators`, tracks native/system calls and Python allocator
events, and handles captured child processes. Memray's official supported
environments page says macOS arm64 is supported, but lists CPython 3.8–3.14;
it also says an `exec` child is not tracked. macOS multiprocessing uses spawn,
so each interpreter child would need its own profiler launch or the result
must be marked incomplete. Native stacks can be weak on macOS. Do not assume
the Linux 3.14 wheel lock works in this experimental 3.16 interpreter or add
a package without the project's dependency decision.

For a dependency-free *diagnostic*, CPython's `tracemalloc` sees traced Python
blocks and high-water size, not all native allocations or a reliable lifetime
allocation count by itself. `PyMem_SetAllocator`/`PyObject_SetArenaAllocator`
can count Python memory-domain calls in an instrumented build or early-start
shim, but must preserve allocator contracts and cannot count direct Rust/C
`malloc` or mappings. Apple's Allocations instrument and malloc stack logging
can inspect system allocator activity, but are intrusive, produce large logs,
and do not automatically distinguish Python allocator events or cover every
`mmap`. `heap` is a retained allocation snapshot, not a lifetime allocation
counter. These are explanatory profiles, not substitutes for the required
separate native-plus-Python allocation pass.

## Next experiment and stop criteria

1. In an isolated follow-up lane, use a tiny native or `ctypes` read-only
   region probe against one controlled CPython 3.16 child. Record OS/SDK,
   page size, API return codes, privilege/signing state, region count, missing
   regions, and per-scan elapsed/CPU/RSS. Time the complete probe with
   `/usr/bin/time -l`. Keep it under 30 CPU seconds and 512 MiB observer RSS;
   no full benchmark or build.
2. At four controlled states (idle, anonymous pages touched, parent/child COW
   sharing, child writes), compare private/shared/resident deltas to the known
   allocation and `vmmap` summary. Include a double mapping or shared mapping
   to expose aliasing. Require complete scans and stable PID identity. Repeat
   enough to see whether observer time permits useful checkpoints; keep it
   outside timed passes.
3. Stop without adding a benchmark field if access fails for an ordinary
   same-user child, if traversal cannot handle submaps/aliases, if private
   counts do not follow the controlled transitions, or if scans materially
   perturb a short workload. If it succeeds, add an explicitly named sparse
   mapped-private diagnostic, self-compare on a quiet host, and leave
   USS/PSS `null` unless a stronger page-identity interface is demonstrated.
4. Independently check Memray against the exact pinned 3.16 interpreter and
   macOS arm64 version in a throwaway environment only after the dependency
   decision. If unsupported, retain allocation status as unavailable and
   choose an explicitly scoped native instrumentation experiment.

## Sources inspected

- Installed Xcode macOS SDK: `usr/include/sys/proc_info.h`,
  `usr/include/libproc.h`, `usr/include/mach/vm_region.h`,
  `usr/include/mach/task_info.h`, and `usr/share/man/man1/{footprint,vmmap,heap,malloc_history}.1`.
- Apple's [Viewing Virtual Memory Usage](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/ManagingMemory/Articles/VMPages.html) explains COW/private/shared regions and `vmmap` summaries; its [debugging tool entitlement](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.cs.debugger) and [SIP runtime protections](https://developer.apple.com/library/archive/documentation/Security/Conceptual/System_Integrity_Protection_Guide/RuntimeProtections/RuntimeProtections.html) describe task-port limits.
- Apple's [malloc debugging features](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/ManagingMemory/Articles/MallocDebug.html) and [Xcode memory tools](https://developer.apple.com/documentation/xcode/gathering-information-about-memory-use) describe stack logging and Allocations.
- Memray's [supported environments](https://bloomberg.github.io/memray/supported_environments.html) and [Python allocator tracing](https://bloomberg.github.io/memray/python_allocators.html) describe version, macOS, child-process, and allocator coverage.
- Local `mac-footprint-20260924.md` and `mac-sampler-overhead-20260924.md` give the existing sampler's contract and bounded overhead observations.
