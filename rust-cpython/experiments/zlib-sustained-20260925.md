# Sustained public zlib tasks, 2026-09-25

**Recommendation: retain the hybrid as a measured speed candidate, without promotion.** Longer complete `zlib_decode_1m` and `gzip_extract_1m` jobs show about 35% lower process wall time and 36% lower kernel CPU for the hybrid, beyond seven-pair control self noise. All input and decoded-content digests match. The benefit is specific to these decode-heavy tasks. The installed hybrid extension is 1,592,928 bytes larger unstripped and 1,451,456 bytes larger after the earlier equal debug-strip diagnostic; sampled memory differences change sign. Broad application speed, matched upstream USS/PSS, native allocation, and product-size gates remain open.

The [raw evidence](data/zlib-sustained-20260925.json) contains all 118 workload attempts, every output payload, `wait4` user/system CPU, external wall, process memory sample, command and environment, plus every `/usr/bin/time -l` controller record. Ignored original logs and the runner remain in `rust-cpython/results/zlib-sustained-20260924/` in the isolated lane.

## Boundary and calibration

The accepted-fork platform control is `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage`; the hybrid is `/private/tmp/python-build-exp-zlib-hybrid-20260924ag/rust-cpython/stage`. Their interpreter SHA-256 values are respectively `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6` and `c3c5e030b2294d9327c4e0f657b85e84514ff131ce2a4cd90d66985fa9295c12`. Their `zlib` extension hashes are `2aef4049da6abe4b4e6725f2f79f692ef8f8b3148aa87903a0d40cdef3ef50bd` and `34e0cce48e60c1ba6622b98615a0d239a5e48cbe3cb36a428e65c623b7ba970c`. The runner rechecked these installed hashes before each main pass. The workload source SHA-256 is `735cbe284df04c2e5bf7f2a6eaca2a58b6783bb011b5bbbf542728078445b9f5`.

Both sides ran the same `-m benchmarks.workloads.zlib` child with `PYTHONHASHSEED=1`, `PYTHONNOUSERSITE=1`, `PYTHONMALLOC=default`, the same `PYTHONPATH`, and an absent `PYTHONPYCACHEPREFIX` with `PYTHONDONTWRITEBYTECODE=1`. This is the source-only import policy of the earlier hybrid qualification. Timing children had no memory sampler. The same 10 ms external sampler was used only in the separate memory pass. These tasks launched no descendants, so `wait4` covers their complete workload process CPU; `/usr/bin/time -l` covers each controller and its waited children.

Two one-iteration control pilots selected 1,707 decode iterations and initially 2,100 gzip iterations. During the long pass, the gzip control's median internal timer settled at 0.612 seconds, below the requested 0.7–1.5 second range. Those 38 gzip attempts remain in the raw evidence as calibration. A fresh 2,700-iteration gzip pass gave 0.786 seconds median control internal work and supplies the reported gzip results. Decode's median was 0.706 seconds. Each reported decode process checked 3,579,838,464 decoded bytes; each reported gzip process checked 2,831,155,200 extracted bytes. The decode input/content digests are `d890765be28e2a1df58b1c67ddf0579416ebf4165e021fae6cffc13bfd68cba4` / `a316f38cceaae9765acdb3de5b4a4ca9d59be014d03d053c10002baa3dad51fb`. The gzip pair is `1de194e61a7ceece437084b2fae6152edf3c6258f9ff0854f05869524ba3d960` / `6eb307fbef685d28bb65e832fe7c3601720b61272f303e9f66f816f55ef89055`. All 118 attempts exited successfully with these task-specific digests, no timeout, and complete process cleanup.

## Seven serial timing pairs per task

Each task ran seven control/control pairs, then seven alternating-order control/hybrid pairs. Values are medians of paired differences, hybrid minus control, per decoded or extracted byte. Ranges show all seven paired values. External wall includes interpreter startup, fixture generation, imports, result formatting, and exit. Kernel CPU is the workload process's user plus system time. Internal wall is the workload's own loop timer and is reported separately.

| Task | Control median external wall / CPU per byte | Hybrid paired wall difference (range) | Hybrid paired CPU difference (range) | Control/control wall range |
| --- | ---: | ---: | ---: | ---: |
| `zlib_decode_1m` | 0.255 / 0.249 ns | −0.089 ns (−0.094 to −0.079); −35.1% paired | −0.090 ns (−0.093 to −0.086); −36.2% paired | −0.010 to +0.011 ns |
| `gzip_extract_1m` | 0.348 / 0.342 ns | −0.124 ns (−0.131 to −0.122); −36.0% paired | −0.124 ns (−0.129 to −0.123); −36.5% paired | −0.017 to +0.004 ns |

The corresponding complete-process median wall times were 0.913 to 0.600 seconds for decode and 0.985 to 0.630 seconds for gzip; median kernel CPU times were 0.892 to 0.574 seconds and 0.969 to 0.615 seconds. Every hybrid pair was faster in both measures, and the smallest gains exceeded the largest absolute control self difference. The internal timer's paired median fell 47.0% for decode and 45.3% for gzip. Longer jobs exposed a complete-task benefit that the earlier short registered jobs did not resolve. The two interpreters still have separate PGO profiles, so precise attribution of small residual effects is limited.

## Separate memory pass and resource cost

Five counterbalanced control/hybrid memory pairs per task used the same iteration count and input digests. The sampler observed one process per attempt, 46–77 samples for decode and 52–82 for corrected gzip, with no sampling errors. Root lifetime peak RSS comes from the kernel; physical footprint is the macOS charged-memory ledger, not USS or PSS. Instrumented pass wall and CPU values are not used as speed evidence.

| Task | Median paired root peak RSS difference (range) | Median paired root physical-footprint difference (range) |
| --- | ---: | ---: |
| `zlib_decode_1m` | +81,920 bytes (−2,719,744 to +5,652,480) | −131,096 bytes (−2,916,352 to +5,455,872) |
| `gzip_extract_1m` | −65,536 bytes (−655,360 to +1,835,008) | −262,144 bytes (−851,968 to +1,638,400) |

These sign-changing results do not establish a memory direction or upstream memory parity. The maximum measured workload root RSS was 59,064,320 bytes, below the 1 GiB lane cap. The earlier equal-policy size diagnostic measured installed unstripped `zlib` extensions at 82,760 control and 1,675,688 hybrid bytes, and stripped copies at 77,056 and 1,528,512 bytes. It did not run the locked product packaging path.

Five unique `/usr/bin/time -l` controller logs cover the failed import-only pilot invocation, successful pilots, initial timing, initial memory, and corrected gzip run. Their combined kernel user plus system CPU was **94.71 seconds**, below the 200-second cap; the largest reported controller process-tree RSS was 64,569,344 bytes and every log reported zero swaps. Host swap allocation stayed at 243.88 MiB in the recorded preflight and post-pass checks. Before the first pilots on 2026-09-24, a compiler and then `target/release/xsh` used roughly one to three CPU cores, so no timing was started. On resumption, process checks showed no compiler or competing benchmark; ordinary UI and OrbStack activity remained. The corrected gzip pass waited through a transient Spotlight process before launch. No sources, dependencies, harness, formatter, linter, hook, or remote were changed.
