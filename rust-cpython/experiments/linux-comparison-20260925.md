# Linux x86_64 URL and zlib comparisons

Question: do the macOS verdicts for the guarded URL quotation patch and the
zlib hybrid hold on x86_64 glibc Linux? Linux can also measure unique (USS)
and proportional (PSS) memory, which the macOS lane could not.

Builds, correctness, and host are described in
[`linux-lane-bringup-20260925.md`](linux-lane-bringup-20260925.md). All six
interpreters are installed builds from the same locked inputs. Each side's
installed `.pyc` caches came from its own `make install`, so bytecode policy
matches. No build, test, or other benchmark ran during any measurement below.
The only exception: a 5-second driver smoke test overlapped the
standard-profile `catalog_search_form` self-comparisons, which are superseded
by the paired runs.

## Verdict

- **URL patch: speed-qualified on Linux; memory within noise.**
  - `catalog_url_normalize`: 12.3% less CPU per operation than the unpatched
    fork and 12.7% less than vanilla upstream. Both 95% intervals exclude
    no-change.
  - `catalog_search_form`: 6.3% less CPU than upstream (interval excludes
    no-change) and 9.1% less than the unpatched fork (interval crosses 1).
  - `catalog_request_path`: 3.5% less than upstream, within noise against
    the fork.
  - The Linux gains are smaller than the macOS 17–19%.
  - Peak USS and PSS differences are 0.03–0.06 MB. That is the size of the
    same-interpreter order bias (+0.035 MB USS in the unpatched fork's
    self-comparison), and −0.045 MB USS against upstream. Keep the patch.
- **zlib hybrid: a real speed/RAM tradeoff; it needs a policy decision.**
  - On a sustained public decode pass it uses 38–40% less process CPU for
    one-shot and streaming zlib, and 13% less for gzip extraction.
  - It costs a steady +1.0 MB of peak USS/PSS (self-noise ±0.03 MB).
  - Almost all of that is file-backed clean private pages of the 1.8 MB
    larger extension, not heap growth.
  - Short registered tasks and ZIP reading gain less or nothing.
  - Under the objective's rule against silently exchanging speed for RAM,
    it stays an experiment. The size is the obvious next target.
- **Controls:** matched upstream and the no-Rust fork are indistinguishable
  in speed on the URL task (CPU ratio 0.995 [0.952, 1.029]), as on macOS.
- **Django:** warm Django tasks against upstream showed no difference
  beyond the standard profile's very wide noise (27–56%). No claim follows.

## Method

Two passes, both on 4-vCPU KVM (Xeon @ 2.10 GHz, 1 thread per core, 15 GiB),
load average about 1.0 at start:

1. `benchmarks/bench.py run|self-compare --local --profile standard` with
   5 timing and 3 memory pairs per workload. The harness pins children to
   one physical CPU. Its self-comparison noise limits on this host were
   4.5–30% for URL tasks and 9–56% for zlib and Django tasks. That is too
   wide to decide the effects here, so this pass is breadth only. Compact
   rows are in
   [`data/linux-standard-20260925.json`](data/linux-standard-20260925.json).
2. [`linux_paired.py`](linux_paired.py): the same harness command,
   environment, correctness payloads, and process-tree sampler, but with
   **20 alternating timing pairs and 10 memory pairs**. The child is pinned
   to CPU 3, each side gets one discarded warm-up, and both sides must return
   identical complete digests.
   - Timing is external wall time plus root `wait4` user+system CPU, per
     logical operation.
   - Memory uses the 10 ms `/proc/*/smaps_rollup` tree sampler: peak PSS,
     peak private (USS = Private_Clean + Private_Dirty), and peak RSS.
   - Intervals are seeded bootstrap 95% intervals of the median paired ratio
     or difference.
   - The workloads launch no children, so root CPU is complete.
   - Raw rows are in
     [`data/linux-paired-20260925.json`](data/linux-paired-20260925.json).

## URL results (paired, 20 timing / 10 memory pairs)

| Comparison | Wall/op ratio [95%] | CPU/op ratio [95%] | Peak PSS Δ MB [95%] | Peak USS Δ MB [95%] |
| --- | ---: | ---: | ---: | ---: |
| Self, candidate, `catalog_url_normalize` | 0.994 [0.956, 1.027] | 0.992 [0.957, 1.024] | +0.004 [−0.002, +0.029] | +0.004 [−0.008, +0.023] |
| Self, unpatched fork, `catalog_url_normalize` | 1.019 [0.975, 1.068] | 1.021 [0.976, 1.072] | +0.043 [+0.004, +0.067] | +0.035 [+0.002, +0.061] |
| Self, upstream, `catalog_url_normalize` | 0.980 [0.949, 1.047] | 0.990 [0.949, 1.054] | +0.002 [−0.011, +0.012] | −0.004 [−0.020, +0.012] |
| Unpatched fork → candidate, `catalog_url_normalize` | **0.881** [0.843, 0.913] | **0.877** [0.844, 0.909] | +0.054 [+0.032, +0.092] | +0.049 [+0.025, +0.102] |
| Unpatched fork → candidate, `catalog_search_form` | 0.914 [0.896, 1.010] | 0.909 [0.892, 1.019] | +0.031 [+0.008, +0.049] | +0.029 [+0.010, +0.053] |
| Unpatched fork → candidate, `catalog_request_path` | 0.984 [0.968, 1.066] | 0.981 [0.967, 1.048] | +0.049 [+0.018, +0.077] | +0.061 [+0.033, +0.084] |
| Upstream → candidate, `catalog_url_normalize` | **0.868** [0.852, 0.892] | **0.873** [0.854, 0.891] | −0.042 [−0.056, −0.020] | −0.045 [−0.070, −0.025] |
| Upstream → candidate, `catalog_search_form` | **0.943** [0.905, 0.982] | **0.937** [0.900, 0.979] | −0.023 [−0.055, +0.014] | −0.020 [−0.033, +0.006] |
| Upstream → candidate, `catalog_request_path` | **0.969** [0.912, 0.983] | **0.965** [0.917, 0.986] | +0.014 [−0.008, +0.032] | +0.012 [−0.012, +0.049] |
| Upstream → no-Rust fork, `catalog_url_normalize` | 0.993 [0.960, 1.015] | 0.995 [0.952, 1.029] | −0.070 [−0.074, −0.061] | −0.057 [−0.078, −0.037] |

Median CPU per operation for `catalog_url_normalize` (one batch of 48 URL
normalizations and 48 stable keys):

| Build | CPU per operation |
| --- | ---: |
| Unpatched fork | 0.731 ms |
| Candidate | 0.640 ms |
| Upstream | 0.750 ms |

Peak USS is about 18.9 MB on all three. The candidate's small positive USS
deltas against the unpatched fork match that fork's own self-comparison
bias, and they reverse sign against upstream, so no memory cost is
established. Every child returned the pinned complete-output digest
(`a6fedf33…4e941` for the catalog batch).

## zlib results

### Registered short tasks (paired)

The registered zlib tasks decode 16 × 1 MiB (8 × 4 KiB streams, 4 wheel
reads) per child, about 0.1 s, so interpreter startup dominates their
process CPU.

| Comparison, platform zlib 1.3 → variant | CPU/op ratio [95%] | Peak USS Δ MB [95%] |
| --- | ---: | ---: |
| Hybrid, `zlib_decode_1m` | 0.854 [0.827, 0.869] | +1.083 [+0.141, +1.280] |
| Hybrid, `zlib_stream_4k` | 0.896 [0.857, 0.944] | +0.524 [+0.223, +0.901] |
| Hybrid, `gzip_extract_1m` | 0.961 [0.927, 1.028] | +0.989 [−0.074, +1.683] |
| Hybrid, `zip_read_wheel` | 1.016 [0.987, 1.050] | +0.938 [+0.502, +2.028] |
| Full zlib-rs, `zlib_decode_1m` | 0.852 [0.815, 0.883] | +0.567 [+0.115, +1.769] |
| Full zlib-rs, `zlib_stream_4k` | 0.913 [0.897, 0.947] | +1.057 [−0.129, +1.192] |
| Full zlib-rs, `gzip_extract_1m` | 0.917 [0.886, 0.936] | +0.600 [+0.086, +1.569] |
| Full zlib-rs, `zip_read_wheel` | 0.986 [0.949, 1.004] | +1.335 [−0.700, +2.236] |
| Self, candidate: decode / stream / gzip / zip | 1.006 / 1.002 / 0.949 / 1.007 | 0.000 / +0.008 / −0.170 / +0.668 |

Short-task memory is noisy. The zip-read self-comparison alone shows
+0.67 MB.

### Sustained public decode (paired, `--iterations` raised)

| Comparison | Iterations per child | CPU/op ratio [95%] | Peak PSS Δ MB [95%] | Peak USS Δ MB [95%] |
| --- | ---: | ---: | ---: | ---: |
| Self, candidate, `zlib_decode_1m` | 400 | 1.012 [0.995, 1.054] | −0.004 [−0.027, +0.011] | +0.000 [−0.033, +0.018] |
| Hybrid, `zlib_decode_1m` | 400 | **0.616** [0.597, 0.627] | **+1.034** [+1.010, +1.051] | **+1.028** [+0.979, +1.053] |
| Self, candidate, `zlib_stream_4k` | 200 | 1.007 [0.941, 1.024] | −0.001 [−0.018, +0.015] | −0.012 [−0.033, +0.004] |
| Hybrid, `zlib_stream_4k` | 200 | **0.605** [0.583, 0.623] | **+1.014** [+0.999, +1.050] | **+1.008** [+0.995, +1.044] |
| Self, candidate, `gzip_extract_1m` | 400 | 1.001 [0.982, 1.044] | +0.009 [−0.003, +0.025] | −0.010 [−0.025, +0.006] |
| Hybrid, `gzip_extract_1m` | 400 | **0.873** [0.815, 0.916] | **+0.962** [+0.940, +0.998] | **+0.975** [+0.954, +0.999] |

These are the baseline-sized sustained decode and gzip passes that the macOS
queue named as the zlib decision gate. Raw rows are in ignored
`results/linux/paired-sustained/`. The table values are reproducible with
`linux_paired.py --iterations`.

### Where the +1 MB goes

A one-process `smaps` probe imported `zlib` and decoded about 1.1 MB once.

| Measurement | Platform zlib | Hybrid |
| --- | ---: | ---: |
| Private pages mapped from the zlib extension | 48 KB | 1,116 KB |
| Anonymous memory after decoding | 3,912 KB | 3,948 KB |
| Total Private_Clean at import | 6,820 KB | 7,748 KB |

The cost is therefore clean, file-backed pages of the larger extension,
touched at load and not shared with another process. Heap growth is only
about 36 KB. Such pages are reclaimable, and processes sharing the same
file would split them in PSS. They still count against a single process's
unique memory.

The hybrid's debug-stripped extension (1,834,816 bytes) is almost as large
as the full zlib-rs extension (1,831,992 bytes), although the hybrid routes
only inflate to Rust. The unused deflate side of the static archive appears
to be linked in. CPython's module link does not pass `--gc-sections`.

## Next actions

1. **zlib hybrid size experiment:** link the prefixed archive with section
   garbage collection, or build an inflate-only archive, and repeat the
   sustained pass. If the +1 MB falls to near the inflate code size while
   the 38–40% CPU gain holds, present the remaining tradeoff for a product
   decision. Otherwise leave the hybrid as an experiment with this record.
2. **URL patch:** Linux adds a second platform on which the patch is
   speed-qualified without an established memory cost. Remaining gates are
   broader applications and the small fresh-import CPU cost measured on
   macOS, which has not yet been re-measured on Linux.
3. **Allocation pass:** Memray has no 3.16 wheel in the locks. The Linux
   lane now has PSS/USS, but allocation counts remain unavailable on both
   platforms.
4. **Cold Django first request:** still the next workload to add. The
   standard profile's Django noise on this host (27–56%) means a Linux
   Django verdict also needs the many-pair method.

## Resources

GNU `time -v` over each driver command:

| Pass | User CPU s | System CPU s |
| --- | ---: | ---: |
| Standard-profile runs (35 commands) | 380.7 | 36.0 |
| Paired runs (22 commands) | 689.8 | 46.9 |
| Sustained zlib paired runs (6 commands) | 165.2 | 80.7 |

Maximum RSS reported for any single driver or benchmark command was
69,700 KB. This is a per-process peak, not a tree total. No swap is
configured.
