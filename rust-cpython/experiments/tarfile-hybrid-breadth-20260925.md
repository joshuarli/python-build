# Public tarfile extraction with the zlib inflate hybrid, 2026-09-25

**Verdict: this application-breadth task does not establish a hybrid speed gain.** Seven paired complete-process runs had a hybrid-minus-control median wall change of +0.05% and a median kernel CPU change of +0.88%. The internal extraction timer changed +0.40%. These small directions do not exceed the relevant control self-comparison variation or the 0.01-second resolution of `/usr/bin/time -l` CPU accounting. The result narrows the earlier direct-gzip gain: a complete tarfile operation spends enough time in archive parsing, member handling, and byte verification that the hybrid's inflate gain did not yield a measured task benefit here. It does not imply upstream CPython parity.

[Raw evidence](data/tarfile-hybrid-breadth-20260925.json) retains all 35 successful attempt payloads and measurements. Ignored original stdout, stderr, resource records, the controller, and the two failed controller logs remain in `rust-cpython/results/tarfile-hybrid-breadth-20260925/` in this worktree. The first controller launch failed before starting a child because its import path was absent. The second failed after launching one pilot because it read `/usr/bin/time` output before waiting for the child; that pilot's unique logs remain, but it was not usable calibration. The corrected controller used new `v2-` attempt IDs and completed without a validation failure.

## Workload and controls

`tarfile_hybrid_breadth.py` constructs a deterministic gzip-compressed USTAR fixture once per process, outside its internal timer. It has 24 small files and one 1,048,576-byte bulk resource, totaling 1,056,892 extracted bytes per iteration. The compressed archive is 1,050,296 bytes, SHA-256 `c3a1efad63406bc8045a04de881d778c171bdf9aa23e37f6196d36808a565c5f`. The canonical full content and metadata digest is `882e28e798c459b79bd291bcac95cdd6b84f4ea11f332788a2d4202197e2d0fc`. Each iteration calls the public `tarfile.open(fileobj=BytesIO(...), mode='r:gz')`, reads every member with `extractfile`, checks count and byte lengths, and compares the complete content and metadata digest. Every successful process checked the fixed archive and content digests. The workload source SHA-256 was `8c8b05c6eecd97de00ee59e5b5c61f757d8785bc25d51fa511a0f702081d3559`.

The accepted-fork platform control was `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage`; the hybrid was `/private/tmp/python-build-exp-zlib-hybrid-20260924ag/rust-cpython/stage`. Their interpreter SHA-256 values were `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6` and `c3c5e030b2294d9327c4e0f657b85e84514ff131ce2a4cd90d66985fa9295c12`. Their installed `zlib` extension hashes were `2aef4049da6abe4b4e6725f2f79f692ef8f8b3148aa87903a0d40cdef3ef50bd` and `34e0cce48e60c1ba6622b98615a0d239a5e48cbe3cb36a428e65c623b7ba970c`. The controller checked these identities before calibration.

Both interpreters used the same script, `PYTHONHASHSEED=1`, `PYTHONNOUSERSITE=1`, `PYTHONMALLOC=default`, `PYTHONDONTWRITEBYTECODE=1`, no inherited `PYTHONPATH`, and the same nonexistent `PYTHONPYCACHEPREFIX`. This forced a source-only installed bytecode policy on both sides; the prefix remained absent. The interpreters have separate PGO build profiles, which limits attribution of very small differences. Ordinary GC and ASLR remained enabled.

A 100-iteration control pilot took 0.1035 seconds internally, selecting 966 iterations. Each reported timing process extracted and checked 1,020,957,672 logical bytes. The seven control comparison runs took 0.994–1.005 seconds internally, within the requested 0.7–1.5-second band. The full-process timer includes interpreter startup, imports, fixture construction and digest, extraction, output, and exit. The internal timer covers repeated opening, extraction, digest verification, and count checks only.

## Serial paired timing

Seven control/control pairs ran first, followed by seven alternating-order control/hybrid pairs. Each attempt was a separate `/usr/bin/time -l` child with no profiler or memory sampler. External wall came from the controller's `perf_counter` around spawn and exit; kernel root user plus system CPU came from `/usr/bin/time -l`. Each process launched no descendants. Values below are per logical extracted byte; paired changes use the within-pair control denominator.

| Metric | Control median | Hybrid median | Hybrid paired median change (range) | Control/control paired range |
| --- | ---: | ---: | ---: | ---: |
| Full-process wall | 1.139 ns | 1.143 ns | +0.05% (−0.66% to +2.97%) | −0.37% to +0.40% |
| Kernel user + system CPU | 1.107 ns | 1.117 ns | +0.88% (0 to +1.77%) | 0 to 0% at 0.01-second resolution |
| Internal wall | 0.974 ns | 0.978 ns | +0.40% (+0.10% to +1.07%) | −0.41% to +0.88% |

The first comparison pair's +2.97% full-wall change was an isolated high result; CPU and internal time did not show a corresponding large shift. Because the CPU field is rounded to hundredths of a second, the +0.88% median is one accounting tick per approximately 1.13-second run. These observations support no speed gain and do not establish a small regression.

## Separate memory and resource pass

Three counterbalanced control/hybrid pairs used the same iteration count with an external 10 ms sampler and no timing claim. The sampler observed exactly one workload process per attempt, with 81–84 samples each and no sampling errors. Its median paired hybrid-minus-control peak RSS was +409,600 bytes, range −1,212,416 to +2,768,896 bytes. The median paired kernel lifetime peak physical-footprint difference was +229,376 bytes, range −1,392,640 to +2,555,904 bytes. The changing signs do not establish a memory direction. Physical footprint is macOS charged memory, not USS or PSS; 10 ms samples may miss a transient peak.

The corrected controller's `/usr/bin/time -l` ledger recorded 38.80 user plus 0.70 system CPU seconds, 46,710,784 bytes maximum resident size, and zero swaps for the controller and waited workload children. The two earlier failed controller commands used approximately 0.14 CPU seconds together, so the lane remained below 40 CPU seconds and 1 GiB peak RSS. Host swap allocation was 243.88 MiB before and after the run; preflight showed no compiler or competing benchmark, while OrbStack Helper used roughly one fifth of a CPU core. Memory, native allocations, and matched upstream CPython resource parity remain unqualified. No build, dependency, production source, formatter, linter, hook, or push was involved.
