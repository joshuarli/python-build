# Rust-for-CPython performance report

Measured 2026-09-24 on a 2021 MacBookPro18,3 (Apple M1 Pro, 8 performance
cores + 2 efficiency cores, 32 GiB RAM), macOS 26.5.2. The build used CPython
3.16.0a0 from Rust-for-CPython commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b`, LLVM 23.1.2, Xcode 26.6 with
SDK 26.5, `-mcpu=apple-m1`, macOS 26.0 deployment target, ThinLTO, and
CPython's `-m test --pgo -j 9` profile task.

## Matched interpreter comparison

The baseline and candidate use the same locked source and C toolchain. The
baseline was configured with Cargo disabled and has no `_base64`; the
candidate was built with the pinned Rust nightly and the Rust `_base64`
extension. Both use the same PGO task and ThinLTO configuration. Public
`base64.b64encode` still calls `binascii` on both builds.

The enhanced benchmark ran five alternating baseline/candidate timing pairs
for each smoke workload. These are local macOS timing-only measurements;
memory and allocation metrics are not available in this mode. The table's
change is candidate over baseline, with positive values meaning slower.
Changes and noise limits use the five paired rounds; the paired median ratio
need not equal the ratio of the two side medians shown.
The host's 1-, 5-, and 15-minute load averages at run start were 2.79, 6.06,
and 5.29. The machine was not isolated from other work.

| Workload | Baseline median | Rust candidate median | Paired change | Noise limit | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Interpreter startup | 20.535 ms | 20.516 ms | +0.13% | 4.87% | Within noise |
| Base64, 64-byte input × 100,000 | 11.326 ms | 6.282 ms | −44.96% | 8.83% | Faster |
| Base64, 1-MiB input × 16 | 6.080 ms | 9.296 ms | +52.92% | 16.45% | Slower |
| Serialization roundtrip × 100 | 168.051 ms | 165.975 ms | −1.26% | 2.25% | Within noise |
| Multiprocessing pool × 20 tasks | 234.431 ms | 238.631 ms | +0.60% | 4.04% | Within noise |

The benchmark's overall verdict is **fail** because the large Base64 workload
regressed beyond its measured noise limit. The other three interpreter-level
workloads are within noise; the small Base64 workload improved. This does not
show a general CPython speedup: only the new extension is called directly by
the Base64 workloads.

The harness recorded 304,482,435 installed bytes for the no-Rust baseline and
304,781,613 bytes for the Rust candidate, a 299,178-byte (0.10%) increase.
The total bytes across extension modules increased by 386,528 bytes. These are
installed-tree sizes, not compressed release-archive sizes.

## Direct Base64 measurements

The staged Rust interpreter ran vendored pyperf 2.10.0 benchmarks with
10 processes, 8 values per process, 2 warmups, and a 100-ms minimum value
duration. The numbers below are median time per call across 80 values. Each
encoder produced bytes identical to `binascii.b2a_base64(..., newline=False)`.

| Input size | Rust `_base64` | Direct `binascii` C | Public `base64.b64encode` | Rust vs C | Rust vs public API |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 64 bytes | 66.21 ns | 109.50 ns | 130.13 ns | −39.5% | −49.1% |
| 4 KiB | 2.308 µs | 1.598 µs | 1.619 µs | +44.4% | +42.6% |
| 1 MiB | 563.03 µs | 381.57 µs | 380.19 µs | +47.6% | +48.1% |
| 16 MiB | 8.983 ms | 6.107 ms | 6.104 ms | +47.1% | +47.2% |

A first run with 5 processes and 8 values reproduced the same pattern: about
66 ns for 64-byte Rust calls, 2.27 µs at 4 KiB, 562 µs at 1 MiB, and 8.99 ms
at 16 MiB. The larger-input slowdown is therefore repeatable across the two
pyperf runs, not a single outlier. Pyperf still reported system jitter on a
few cases, so sub-1% differences are not treated as meaningful.

## Interpretation and scope

The Rust encoder is useful evidence that the extension boundary works, and it
is faster for very small inputs. At 4 KiB and above, the existing C encoder is
about 43–48% faster. Do not route the public Base64 API to this implementation
until the bulk path is improved and remeasured.

The separate [`zlib-proof`](zlib-proof/README.md) links the pinned
`libz-rs-sys-cdylib` 0.6.7 C ABI beneath the unchanged CPython
`Modules/zlibmodule.c`. Its extension has no dynamic `libz` dependency, and
1,892 CPython tests passed across `zlib`, `gzip`, `tarfile`, `zipfile`,
`zipimport`, and `binascii`. This is a compatibility proof; zlib throughput
and compressed-byte comparisons have not been measured. The regular lane and
production builds still use their existing zlib backend.

Beyond the `_base64` extension and this isolated zlib backend proof, no
standard-library implementation has been migrated into the product or broadly
optimized in Rust. The ranked candidates in `rust-cpython/README.md` remain
future work.

The macOS harness runs locally without CPU affinity, a container/network
boundary, process-memory sampling, or allocation tracing. This is a same-source
Rust-on/Rust-off comparison, not a comparison against vanilla upstream CPython
or Astral PBS. Raw local results are in
`benchmarks/results/rust-cpython-enhanced-macos/`,
`rust-cpython/results/base64-pyperf-enhanced-macos.json`, and
`rust-cpython/results/base64-pyperf-confirmation.json`.
