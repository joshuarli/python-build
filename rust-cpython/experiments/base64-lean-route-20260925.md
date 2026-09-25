# Lean AArch64 Base64 public route

**Verdict: retain as an optional candidate.** A `no_std`/`core` AArch64 Rust kernel linked into the existing `binascii.b2a_base64` wrapper retains the measured NEON speed and removes the previous route's 1.42 MB file growth. Its standalone extension is 1,760 bytes larger than the same-source C control. Fresh-process peak RSS differences stayed within control/control noise. This is a standalone module result; an installed CPython build, full workload qualification, and Linux arm64 qualification are still needed before promotion.

## Exact source and build

The pinned CPython source commit is `b812b4a7b9efaca46b98544a8633b7d7e454166b`. Its archive is locked in `rust-cpython/sources.lock.json` at 44,210,863 bytes and SHA-256 `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`. The original `Modules/binascii.c`, `Modules/clinic/binascii.c.h`, and `Modules/_base64/src/lib.rs` SHA-256 hashes are `6a87f282b9bb1501cbd17ef652d9c003e047402a6a7916d7cc3f8863c58c610e`, `ce732ade621a63cf2dda3d28185505350e110e92431ea437b64e53fc99305797`, and `3bcc6396bc10c4ae3022b05d7093751428414c0b6c694ee9bace47b725218a17`. Apply the [NEON patch](base64-neon-20260925.patch), [C route patch](base64-binascii-route-20260925.patch), then this [lean kernel patch](base64-lean-route-20260925.patch) in that order. Their SHA-256 hashes are `4b26b291d3b3931d5932b76a70fe4c18360635a5208eb7f653bfceea36521c46`, `b8e8fd86c2c64dff8a44693b14eca28880df4e2514ffe3c2178a7ed00cb42396`, and `8d8812955b01348746f522dd0d95b175581235a54659408f776931396368049f`. The built `binascii.c`, `lib.rs`, and new `lean_route.rs` hashes are `e2653c0d14867d5e6340f1845e59f7d9a072e0a3b00c8a9e02aaa2f0b3a4dae1`, `7dd969bdf6f4d44d84daf351cd17c79b7c9a54ab8956e41b0a1626a9e6edeba2`, and `45c298891de1e03dbcd1bb8eca41f569d6e262fa4dae4f7b398f7cabf77def2e`.

The [runner](base64-lean-route-20260925.py) checks all three original file hashes before copying, applies all three patches, checks resulting source hashes, builds the three standalone extensions, checks public output identity, and optionally measures paired time and fresh-process memory. From this worktree root, extract the verified locked archive into lane scratch and pass its `Modules` directory to the runner:

```sh
lane_work=rust-cpython/work/base64-lean-route-20260925
mkdir -p "$lane_work/pinned"
curl -fL https://codeload.github.com/Rust-for-CPython/cpython/tar.gz/b812b4a7b9efaca46b98544a8633b7d7e454166b -o "$lane_work/cpython-pinned.tar.gz"
printf '%s  %s\n' 965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467 "$lane_work/cpython-pinned.tar.gz" | shasum -a 256 -c -
test "$(wc -c < "$lane_work/cpython-pinned.tar.gz")" -eq 44210863
tar -xzf "$lane_work/cpython-pinned.tar.gz" --strip-components=1 -C "$lane_work/pinned"
/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -S \
  rust-cpython/experiments/base64-lean-route-20260925.py \
  --scratch "$lane_work" --source-modules "$lane_work/pinned/Modules" \
  --evidence rust-cpython/experiments/data/base64-lean-route-20260925.json \
  --build --benchmark
```

The reported measurements used an already extracted copy of that same pinned source, verified by the three original file hashes before compilation. A replay with the new `--source-modules` argument reproduced all three artifact hashes and exact outputs in evidence run `20260925T090732-459598e5`; it did not rerun timing. Replay on a loaded host should omit `--benchmark` if only source, link size, and output identity are needed.

The C control and candidates use the staged Python 3.16 headers, pinned `binascii.c` and generated Clinic header, official locked LLVM 23.1.2 `clang` (SHA-256 `f8fa7184dab7d8fa7f6af268a6f1b3aa3d2e598d0cca04dc68447b4c0ca58d8e`), `-O3 -mcpu=apple-m1 -fPIC -mmacosx-version-min=26.0`, and the Xcode 26 SDK. Both Rust archives use pinned `rustc +nightly-2026-09-15` (`1.100.0-nightly`, commit `574ff7d98`), `--crate-type staticlib -O -C target-cpu=apple-m1 -C panic=abort`. The standard Rust route extracts the kernel from the patched `lib.rs`; the lean route compiles `lean_route.rs` directly. Candidate links add `-Wl,-dead_strip -Wl,-exported_symbol,_PyInit_binascii`. No new dependency was added. The patch does not wire an installed build.

| Standalone extension | Bytes | SHA-256 | Mach-O `__text` bytes |
| --- | ---: | --- | ---: |
| C control | 90,048 | `c3d278cfee9d3a77f912324d5a2927acdacfe2ec7c28479448d27e72111677f9` | 27,404 |
| Standard Rust with dead stripping | 478,480 | `f6fd7b5e561b205107c31b65a9229c1262e62fff84f3b8c5f8090bda6605a022` | 234,940 |
| Lean Rust with dead stripping | 91,808 | `350defec785b2956268d7ece4cc9e9384d9778ba04163f3b215089e74f43bbe1` | 32,684 |

`nm -g` shows `_PyInit_binascii` as the sole globally defined symbol in the lean extension. The previous unstripped standard Rust route was 1,513,184 bytes; dead stripping alone removes 1,034,704 bytes, and the lean kernel removes another 386,672 bytes. The lean delta from C is 1,760 bytes, 1.96% of the C file size. The lean static archive is not distributed; only its linked extension is measured here.

## Behavior, time, and memory

Run `20260925T090337-2422b2b3` in [compact evidence](data/base64-lean-route-20260925.json) loaded all three exact extensions as `binascii` and compared 128 outcomes per arm plus the 20,000-record public catalog. Inputs span 0–1,048,578 bytes, three byte patterns, both padded tails, `base64.b64encode`, direct `b2a_base64`, alternate alphabet, padding, wrapping, newline, buffer variants, and invalid inputs. All outcomes and catalog digests matched the C control. The route still calls Rust only for contiguous inputs of at least 4,096 bytes with default alphabet, padding, no wrap, and no newline; CPython's C wrapper owns argument parsing, allocation, and all other options. The Rust wrapper checks output length, and the C wrapper rejects an unexpected returned length with `SystemError`. The lean kernel uses `core::arch::aarch64` NEON intrinsics and aborts on an unexpected Rust panic rather than unwinding through C. It needs an isolated static link review if combined with other Rust libraries in one extension.

The final linked binary hash was timed in run `20260925T090210-9177148b`, five alternating pairs per size, roughly 32 MiB per sample. `perf_counter_ns` measured elapsed time; `getrusage(RUSAGE_SELF)` measured kernel-accounted CPU. Each row is median per public call:

| Input | C wall / user / system | Lean wall / user / system | Lean/C wall |
| --- | ---: | ---: | ---: |
| 65,538 bytes | 24.05 / 23.97 / 0.05 µs | 8.51 / 8.49 / 0.03 µs | 0.354 |
| 1,048,576 bytes | 392.66 / 381.84 / 6.84 µs | 140.72 / 134.00 / 7.00 µs | 0.358 |

The 65 KiB same-arm wall ranges were 23.94–24.16 µs for C and 8.30–8.89 µs for lean; 1 MiB ranges were 381.95–394.05 and 135.26–152.90 µs. This preserves the earlier NEON route's approximate 0.35–0.37 ratio on a loaded host. Background system activity was substantial; these timings are a bounded diagnostic, not quiet-host qualification.

`/usr/bin/time -l` measured fresh processes that imported the assigned extension and encoded one 1 MiB input. Three alternating C/lean pairs yielded lean-minus-C peak RSS of −180,224, +49,152, and +229,376 bytes. A C/C pair differed by 294,912 bytes. All eight output hashes matched, each child reported zero swaps, and system swap remained at 235.88 MiB. These observations do not resolve a resident-memory difference below roughly 0.3 MB, but they do not reproduce the earlier 1.6–2.0 MB debt. The Python startup path also loads staged `binascii` before replacing it in the child, as in the prior route measurement; both arms share that cost.

The metered rebuild run `20260925T090256-c73b241c` records wall, child CPU, and `/usr/bin/time -l` peak RSS for each patch, compiler, and linker command. Commands are stored once under `build_commands` in the evidence and referenced by ID from attempts. The largest observed compiler peak was 122.3 MB for standard Rust and 108.4 MB for lean Rust; the lean link peaked at 35.9 MB. Earlier unmetered calibration and failed preflight attempts are retained in the JSON with unavailable resource fields marked null; total exploratory resource cost is unqualified. No CPython suite, formatter, linter, hook, full installed build, commit, or push ran.
