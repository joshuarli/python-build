# Zipfile complete-task profile, 2026-09-25

**Verdict: the warmed directory reader is a modest part of the registered wheel task.** On the unchanged pinned Rust-for-CPython interpreter, `ZipFile._RealGetContents` took 1.366 ms cumulative across four calls, 10.0% of the 13.669 ms warmed, instrumented complete `zip_read_wheel(4)` call. Its own time was 0.577 ms, 4.2% of the task. The cold profile attributed 18.6% to the directory reader because its first call triggered a one-time codec lookup. These are cProfile location measurements, not uninstrumented speed or kernel CPU shares. A native implementation is not justified until an uninstrumented complete-task baseline and control/control noise measurement establish that this size of change can be resolved.

## Workload and boundary

The registered standard workload specifies four archives. The public `zip_read_wheel` function generated the same fixed method-8 wheel-shaped archive, verified its SHA-256 `216b735da6639be9f3f2b60e2973ca8f41539161648b74d5547d68877a713df7`, read all 67 named members per archive through `ZipFile.read`, and compared each decoded byte string against the original. It returned 8,413,264 extracted bytes and output digest `e1b97843b19af113cbb090fc676658ff5620f4896a5c1bb8f424ff75ac186071`. The profile encompassed the entire function call, including fixture generation and input/output checks. Imports and result serialization occurred outside the profile.

The interpreter was `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16` (SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`). Its installed `zipfile/__init__.py` hash was `6278152bb420f29870d46c4d975f564a215fcd31f543157242dd9470faedba61`, matching the pinned source examined in [the headroom scout](zipfile-headroom-20260925.md). No interpreter or source build was changed.

## Cold instrumented call rows

Times are cumulative (`cum`) and own (`self`) cProfile seconds summed across calls. Child rows overlap parent rows and must not be added together. The denominator for the percentages is the `zip_read_wheel` cumulative time of 14.283 ms. The complete [raw JSON](data/zipfile-profile-20260925.json) retains all 211 call rows, result values, resource logs, and attempt history; the binary `.prof` and command logs remain in the lane's ignored `rust-cpython/work/zipfile-profile-20260925a/` directory.

| Function | Calls | Cum ms | Self ms | Cum share |
| --- | ---: | ---: | ---: | ---: |
| `zip_read_wheel` | 1 | 14.283 | 0.400 | 100% |
| `ZipFile.__init__` | 4 | 2.704 | 0.021 | 18.9% |
| `ZipFile._RealGetContents` | 4 | 2.662 | 0.585 | 18.6% |
| `ZipInfo._decodeExtra` | 268 | 0.064 | 0.047 | 0.4% |
| `ZipFile.read` | 268 | 6.588 | 0.209 | 46.1% |
| `ZipFile.open` | 268 | 2.700 | 0.515 | 18.9% |
| `ZipExtFile.read` | 268 | 3.294 | 0.111 | 23.1% |
| `ZipExtFile._read1` | 268 | 3.183 | 0.432 | 22.3% |
| `zlib.Decompress.decompress` | 268 | 1.320 | 1.320 | 9.2% |
| `_read_local_file_header` | 268 | 0.748 | 0.132 | 5.2% |
| `ZipExtFile._update_crc` | 268 | 0.387 | 0.078 | 2.7% |
| `zlib.crc32` | 871 | 0.457 | 0.457 | 3.2% |
| `_wheel_archive` fixture creation | 1 | 3.080 | 0.031 | 21.6% |
| `_digest` expected-output digest | 1 | 1.007 | 0.066 | 7.1% |

`zlib.crc32` includes archive construction, directory filename CRC, and extraction CRC; its global row cannot isolate one phase. `_read_local_file_header` verifies each member's local header. `ZipExtFile._update_crc` checks decoded content. The directory row includes its own parsing plus `ZipInfo` construction and validation. The separately registered `zipimport_cold` workload uses `zipimport._read_directory`; this profile says nothing about that path.

## Command-tree resources and attempts

The host had 10 CPUs and 32 GiB physical memory. Before and after the profile, `vm.swapusage` reported 243.88 MiB used. Process scans found no benchmark, compiler, PGO, or build process; OrbStack Helper was active at roughly 14–18% CPU with about 5.8–6.0 GB RSS. `/usr/bin/time -l` measured the direct Python child. The workload creates no subprocess, so its user/system CPU record covers this command tree. Peak RSS is kernel reported; the process count of one follows from command and workload inspection, not a peak process sampler. Each attempt has a distinct ignored raw log.

| Attempt | Status | User CPU | Sys CPU | Elapsed | Peak RSS | Swaps |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `001` | Import failed before profiling: missing `PYTHONPATH` | 0.05 s | 0.02 s | 0.08 s | 26,755,072 B | 0 |
| `002` | Successful four-archive profile | 0.05 s | 0.01 s | 0.08 s | 39,960,576 B | 0 |

The two attempts consumed 0.13 s of kernel-accounted user plus system CPU in total, below the 20 s controller budget. The 39.96 MB largest peak RSS is below 512 MB. The successful call's internal elapsed time was 9.696 ms; it excludes imports, profile serialization, and startup, while `/usr/bin/time -l` includes them. Neither time is an uninstrumented latency verdict. No tests, formatter, linter, hooks, source edits, or build were run.

## Warmed complete-task profile

A follow-up used the same pinned interpreter and public workload. In one process, `zip_read_wheel(1)` first read and checked a full archive before the profiler was enabled. It returned 2,103,316 extracted bytes, the same input SHA-256 and output digest as the four-archive task. Then cProfile covered one unchanged `zip_read_wheel(4)` call; it again returned 8,413,264 extracted bytes and those fixed digests. Thus only the one-time interpreter and codec state changed, while the profiled task and checks stayed intact. The profile contains 90 call rows, retained in the same raw JSON.

| Function | Cold cum ms | Warm cum ms | Warm self ms | Warm cum share |
| --- | ---: | ---: | ---: | ---: |
| `zip_read_wheel` | 14.283 | 13.669 | 0.441 | 100% |
| `ZipFile._RealGetContents` | 2.662 | 1.366 | 0.577 | 10.0% |
| `ZipFile.read` | 6.588 | 6.563 | 0.217 | 48.0% |
| `ZipExtFile.read` | 3.294 | 3.333 | 0.117 | 24.4% |
| `ZipExtFile._read1` | 3.183 | 3.216 | 0.451 | 23.5% |
| `zlib.Decompress.decompress` | 1.320 | 1.431 | 1.431 | 10.5% |
| `_read_local_file_header` | 0.748 | 0.587 | 0.130 | 4.3% |
| `ZipExtFile._update_crc` | 0.387 | 0.398 | 0.079 | 2.9% |
| `zlib.crc32` | 0.457 | 0.480 | 0.480 | 3.5% |
| `_wheel_archive` fixture creation | 3.080 | 3.755 | 0.033 | 27.5% |

Cold `_RealGetContents` included a single `<frozen encodings>.search_function` call at 1.253 ms cumulative, associated with first use of CP437 decoding; the warm profile has no such row. The directory reader's own time stayed similar (0.585 → 0.577 ms), while cumulative time dropped by 1.296 ms and its complete-call share dropped from 18.6% to 10.0%. Other rows moved in both directions, so the cold/warm difference is attribution evidence, not a speed comparison. Even zero-cost directory construction would remove at most the warm 10.0% of this profiled call; real code can remove less and may add cost.

Before the warm run, the host still had no benchmark or compiler process, 159,183 free 16 KiB pages, and 243.88 MiB used swap; swap usage was unchanged afterward. Attempt `003` used `/usr/bin/time -l`: 0.06 s user plus 0.02 s system CPU, 0.09 s elapsed, 43,450,368 B peak RSS, zero process swaps. The process had no children, so the direct-child CPU account covers its command tree. These totals include the warm iteration and profiling setup, while the 13.669 ms cProfile root row includes only the four profiled iterations and their fixture/checking work. This follow-up used 0.08 s CPU, below its 5 s budget and 512 MB RSS bound. No source edit, test, formatter, linter, hook, build, or push occurred.
