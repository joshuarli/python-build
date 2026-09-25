# Zipfile complete-task baseline and self-noise, 2026-09-25

**Verdict: a large directory-reader gain would be resolvable in this wheel task, but there is no candidate speed result.** Seven serial control/control pairs on the unchanged installed interpreter had a maximum absolute paired difference of 0.89% in full-process wall time, 1.79% in kernel user plus system CPU time, and 0.89% in the workload's internal task time. The earlier cProfile attributed 18.6% of an instrumented four-archive task to `ZipFile._RealGetContents`. Eliminating that entire profiled cost would be a theoretical 18.6% internal-task ceiling; a real directory reader cannot remove all of it, and profiler overhead may make the share larger than its uninstrumented share. These measurements establish a timing baseline and local noise allowance, not a reason to implement a native parser by themselves.

## Workload and measurement

The unchanged registered `zip_read_wheel` CLI constructs the fixed in-memory method-8 wheel, verifies input SHA-256 `216b735da6639be9f3f2b60e2973ca8f41539161648b74d5547d68877a713df7`, opens it with `ZipFile`, reads and compares all 67 members by name on every iteration, and emits output digest `e1b97843b19af113cbb090fc676658ff5620f4896a5c1bb8f424ff75ac186071`. The work unit is one extracted byte. Each timed process reported 2,734,310,800 logical extracted bytes (1,300 reads of the same 2,103,316 decoded bytes); all 14 processes reported the expected input and output digests and operation count.

The pilot used 500 iterations and took 0.4135 s internally, so 1,300 iterations were fixed before the paired runs. Each timed internal task took 1.0586–1.0703 s, within the requested 0.7–1.5 s window. The pilot itself is retained in the raw data and consumed 0.47 s of kernel user plus system CPU. No calibration was discarded.

Both A and B labels used `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16` (SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`), the same installed `zipfile/__init__.py` (SHA-256 `6278152bb420f29870d46c4d975f564a215fcd31f543157242dd9470faedba61`), and the same workload source (SHA-256 `735cbe284df04c2e5bf7f2a6eaca2a58b6783bb011b5bbbf542728078445b9f5`). The existing `zipfile` standard `.pyc` had SHA-256 `0ed39475db15e3dd8fd0d17f150d6b6a0697835537f43f35b213e4e9b207283a`. Both labels ran from that identical stage with `PYTHONHASHSEED=1`, `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONMALLOC=default`, and the same worktree `PYTHONPATH`; no cache was written during measurement. Ordinary GC and ASLR remained enabled. A and B differed only in log label and counterbalanced order.

Every substantial invocation was a direct Python child under `/usr/bin/time -l`; the workload launches no subprocess, so kernel user plus system CPU covers its command tree of one process. Full-process wall is the external `real` field, rounded by that tool to 0.01 s. Internal time comes from the workload's uninstrumented `perf_counter` around the archive read and checks; it excludes fixture construction, imports, and process startup. The external command also recorded peak RSS and swaps, but no memory sampler, profiler, forced GC, or special allocator ran in the timing pass. The complete [raw JSON](data/zipfile-baseline-20260925.json) includes each stdout payload and `/usr/bin/time -l` log; separate logs remain under ignored `rust-cpython/work/zipfile-baseline-20260925a/`.

## Seven counterbalanced pairs

Wall, CPU, and internal entries show **A / B seconds**. Deltas are `(B / A - 1) × 100`; both labels are the same control interpreter.

| Pair | Order | Full wall | User + sys CPU | Internal task | Wall delta | CPU delta |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: |
| 1 | AB | 1.13 / 1.13 | 1.12 / 1.11 | 1.0628 / 1.0665 | +0.00% | -0.89% |
| 2 | BA | 1.12 / 1.13 | 1.10 / 1.11 | 1.0606 / 1.0642 | +0.89% | +0.91% |
| 3 | AB | 1.12 / 1.13 | 1.11 / 1.11 | 1.0586 / 1.0641 | +0.89% | +0.00% |
| 4 | BA | 1.12 / 1.13 | 1.11 / 1.11 | 1.0638 / 1.0703 | +0.89% | +0.00% |
| 5 | AB | 1.13 / 1.13 | 1.11 / 1.11 | 1.0630 / 1.0643 | +0.00% | +0.00% |
| 6 | BA | 1.13 / 1.12 | 1.12 / 1.10 | 1.0694 / 1.0599 | -0.88% | -1.79% |
| 7 | AB | 1.12 / 1.12 | 1.10 / 1.10 | 1.0594 / 1.0604 | +0.00% | +0.00% |

Across all timed processes, full-process wall was 1.12–1.13 s (median 1.13), or 0.4096–0.4133 ns per logical extracted byte (median 0.4133). Kernel user plus system CPU was 1.10–1.12 s (median 1.11), or 0.4023–0.4096 ns per byte (median 0.4060). The paired B-minus-A medians were 0.00% for wall and CPU; paired ranges were -0.88% to +0.89% wall, -1.79% to +0.91% CPU, and -0.89% to +0.61% internal time. The external wall and CPU fields have 0.01 s resolution, so their small percentage differences are quantized.

## Resources and limits

The 15 measured attempts (one pilot and 14 paired processes) consumed 15.80 s kernel user and 0.19 s kernel system CPU, **15.99 s total**, below the 60 s lane budget. Maximum observed peak RSS was 50,020,352 bytes, below 512 MiB, and every `/usr/bin/time -l` report showed zero swaps. The host had 10 CPUs and 32 GiB physical memory. Pre- and post-run `vm.swapusage` stayed at 243.88 MiB used. Process scans found no concurrent benchmark, build, compiler, or PGO process; OrbStack Helper used about 12–30% CPU and 5.8–6.0 GB RSS around the run. This was a local noise measurement on that host, not a universal confidence interval.

The profile's 18.6% number applies to its instrumented internal task, not directly to full-process wall or kernel CPU. A future candidate should preserve the same input/output checks and source-cache policy, then be compared against this control with new serial counterbalanced pairs and its own self-noise. No source patch, build, test suite, formatter, linter, hook, or remote push was run.
