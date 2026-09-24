# macOS Allocations export probe (2026-09-24)

## Decision

**Reject Xcode 26.6 `xctrace export` as the current allocation benchmark
gate.** The installed tool recorded the pinned 3.16 fixture without a privacy
prompt, and its Statistics detail exported lifetime category counts. The
export did not expose the fixture's requested `malloc` bytes, per-allocation
freed events, or allocation totals attributed to the spawn child. The child
appeared in a generic `process-info` table, which is insufficient to establish
its allocation coverage. Do not treat the matching aggregate bucket count as
proof of child coverage. Keep native and Python lifetime allocation metrics
unavailable for this macOS lane; these exports remain useful diagnostics.

## Fixture and bounds

`rust-cpython/experiments/mac-allocation-probe-20260924.py` makes 512 live
`bytearray(777)` objects in each process. The parent issues seven
`malloc(65537)`/`free` pairs and touches a 3 MiB anonymous `mmap`; one
`multiprocessing` **spawn** child issues nine `malloc(73729)`/`free` pairs
and touches a 5 MiB mapping. Both print their role and PID. The exact native
malloc request sum is 1,122,320 bytes across 16 requests. The child is joined
before the parent exits. These are controlled calls, not a count of all Python
or process allocations.

The read-only executable was
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`
(SHA-256 `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`).
This worktree started at `d1fe4149217c0878856165d27f378f5edc04b0bc`.
Host: macOS 26.5.2 arm64, Xcode 26.6 build 17F113; trace TOC reports
Instruments 16.0 (17F113). The installed `Allocations` template recorded
heap and VM allocations, kept freed-memory events, and used deferred mode.

The fixture alone completed in 1.14 s wall, 0.06 s user and 0.03 s system
for the timed root, with 29,163,520 B peak root RSS and zero swaps reported
by `/usr/bin/time -l`. The child printed its completion marker. The recorder
used `--time-limit 8s --no-prompt` within a 45 s `gtimeout` with a five-second
kill grace. The fixture itself had a 10 s child join limit. No command reached
its time limit; the recorder stayed below 2 GiB RSS and 120 CPU s. Its output
stayed below 17 MiB per trace. The fixture stayed far below 30 CPU s and
512 MiB RSS; the root RSS measure alone does not establish the child's peak.

| Pass | Wall s | User s | System s | Peak RSS B | Trace disk KiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Record 1 | 18.76 | 5.17 | 2.69 | 711,016,448 | 16,972 |
| Record 2 | 6.53 | 2.42 | 1.20 | 707,608,576 | 16,732 |
| TOC export 1 | 2.20 | 0.62 | 0.50 | 147,832,832 | n/a |
| Statistics export 1 | 2.15 | 0.62 | 0.46 | 148,389,888 | n/a |
| TOC export 2 | 2.22 | 0.60 | 0.53 | 148,062,208 | n/a |
| Statistics export 2 | 2.22 | 0.60 | 0.53 | 148,783,104 | n/a |

All substantial commands used `/usr/bin/time -l` around `gtimeout` and
`xcrun xctrace`; the figures are kernel-accounted command-tree observations,
not profiled workload speed. The recorder may use Xcode helpers outside that
wait tree. `time -l` reported zero swaps for each command. Host swap use was
251.88 MiB before and 243.88 MiB afterward; these snapshots cannot attribute
swap to the probe. The `process-info`, Allocations List, Statistics, and one
`kdebug` export also completed in about 2.1–2.2 s apiece with about 147–152
MiB measured peak RSS. Their XML files were at most 373 KiB. No system setting,
dependency, source pin, or stage file was changed.

## What the XML proves

Both TOCs contain the same Allocations track details: `Statistics` and
`Allocations List`. Their run process lists contain only the launched parent
and kernel. The generic `process-info` export from pass 1 contains the logged
parent PID 46635 and child PID 47348, while the TOC target is parent 46635.
Pass 2 logged parent 61743 and child 61962; its TOC again lists only the
parent. Thus the recording saw the child as a process, but its Allocations
detail does not identify a separate child capture or per-process totals.

The `Statistics` detail had 60 rows and the same column names on both passes:
`category`, `persistent-bytes`, `count-persistent`, `total-bytes`,
`transient-bytes`, `count-events`, `count-transient`, and `count-total`.
`Malloc 80.00 KiB` had `count-total=16`, `count-transient=16`, and
`total-bytes=1,310,720` in both. Sixteen exactly matches the fixture's two
batches **if both processes are included**, but the 80 KiB size is malloc's
rounded size class, not either requested size. It exceeds the known requested
sum by 188,400 bytes (16.8%). The export has no per-request size field or
role/PID on this row. Interpreter and profiler activity could contribute to
the bucket, so this aggregate match does not establish all 16 fixture calls.

The Allocations List export from pass 1 had 1,068 rows, every one marked
`live="true"`. It contained neither `65537` nor `73729` size rows; both
fixture batches had been freed. Therefore it cannot independently reconstruct
the lifetime requests or their bytes. The generic `kdebug` export has thread
and process identities but no documented malloc request-size or lifetime
allocation field. The first Statistics row reports `All VM Regions` total
33,734,656 B and 17 allocations; the repeat reports 25,346,048 B and 15.
The separate `All Anonymous VM` row reports only one 49,152 B event in both,
not the known 3 MiB and 5 MiB mappings. `VM: Memory Tag 255` totals 8,404,992
B in both, near the sum of both mappings, but is an aggregate tag with no
per-mapping PID or request size. Anonymous mapping identity and child coverage
are therefore unresolved.

The Statistics schema and selected bucket totals were stable across these two
captures; that does not establish a stable documented interface or complete
event coverage across workloads. The raw `.trace` directories and XML exports
are retained only under ignored
`rust-cpython/work/allocation-probe-20260924x/` in this worktree. No raw trace
or XML is committed. This probe did not run a benchmark or make a speed claim.
