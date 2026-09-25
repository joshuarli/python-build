# URL quote early fallback gate, 2026-09-25

## Verdict

**Reject.** Moving the short, nonempty-safe fallback ahead of the trace and profile checks did not reduce complete request-path CPU beyond local noise. The two early/fallback CPU ratios were 1.0015 and 1.0062; the early/early same-side ratio was 1.0203. The early candidate still costs about 2–4% more CPU than the pure pinned parser on this task. Keep the existing production patch and the prior crossover candidate unchanged.

## Candidate and contract

The proposed source-only overlay moves the exact `bytes` checks and `not (safe and bs_len < 32)` condition ahead of `_rust_url_gettrace()` and `_rust_url_getprofile()`. It runs the truth-value check only after both exact type checks. The fast exit, cached `_byte_quoter_factory(safe)` construction, cache-edit guard, Rust call, and original Python fallback remain byte-for-byte identical. The patch is `url-quote-early-gate-20260925.patch` (SHA-256 `357d038233fc02470bb160f1e8ae6df04fd2022d5e0ced6b2236fbce33546f28`). The early parser overlay is SHA-256 `8546198d00018cf39daf23d7c0345740f42442369c74d1af90a072000a6b3d01`.

All four arms use the same read-only staged CPython 3.16 executable (SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`). The current, prior fallback, and early arms use the same locally built extension (SHA-256 `b1ab627f758d778087fb2c8e8e8df0835396e9b9c8d3db45550c7ca74710d617`), identical to the earlier crossover experiment. The pure arm uses the pinned staged parser. All four parsers are copied into worktree-owned source-only overlays without bytecode caches. The runner uses `-B`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=1`. The three extension build commands and their resource records are in the preparation JSON.

## Complete workload result

Run `python3 rust-cpython/experiments/url-quote-early-gate-20260925.py --skip-calibration --evidence rust-cpython/experiments/data/url-quote-early-gate-20260925-breadth.json` from this worktree. The runner invokes the registered complete `catalog_search_form` (500 iterations), `catalog_request_path` (1,000), and `catalog_url_normalize` (2,000) workloads. It pairs early against fallback, current, and pure in both orders twice, plus one same-side pair for each of early and fallback. All 48 workload attempts exited successfully and matched each task's full output digest and the common input digest `7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`.

| Task | Early/fallback CPU | Early/current CPU | Early/pure CPU | Fallback self CPU | Early self CPU |
| --- | --- | --- | --- | --- | --- |
| Search form | 0.988, 1.019 | 0.970, 0.960 | 0.947, 0.961 | 1.005 | 0.993 |
| Request path | 1.002, 1.006 | 0.949, 0.947 | 1.021, 1.044 | 0.995 | 1.020 |
| URL normalize | 1.010, 0.984 | 1.008, 0.998 | 1.035, 1.027 | 1.015 | 0.986 |

Ratios are summed `wait4` user plus system CPU per complete process; below 1 favors early. Request-path early/fallback wall ratios were 1.010 and 0.998. Same-side early wall ratio was 1.040. `ru_nswap` was zero for every workload attempt. Peak RSS ranged from 32.39 to 33.25 MiB across the three Rust request-path arms, without a consistent early advantage. The host load average fell from 3.43 to 2.71 during the run. OrbStack Helper remained active, but its sampled CPU fell from 18% to 10%; system swap usage stayed at 243.88 MiB. Same-side drift, especially in request path, is larger than the proposed effect.

The JSON files preserve every attempt's order, elapsed time, separate `wait4` user/system CPU, peak RSS, swaps, full stdout SHA-256, registered output digest, source identities, host observations, and build failures if any. `wait4` directly accounts for each workload process, which has no descendants. Build records account for direct children; `rustup run` may launch `rustc`, whose CPU is outside that direct-child record. The benchmark measures complete workload invocations on this loaded macOS host, not an isolated per-call microbenchmark.
