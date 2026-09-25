# Base64 route through `binascii.b2a_base64`

**Verdict: keep as an opt-in coverage and performance candidate with explicit memory debt; do not promote it as the default.** A standalone candidate `binascii` extension routes only contiguous default-alphabet, padded, unwrapped, no-newline inputs of at least 4096 bytes into the pinned AArch64 NEON Rust encoder. Argument parsing, validation, result allocation, and all other options stay in CPython's C wrapper. The Rust encoder writes into that wrapper's `PyBytesWriter` buffer. An invalid encoder return length discards the writer and raises `SystemError`.

The [route patch](base64-binascii-route-20260925.patch) applies after the [NEON patch](base64-neon-20260925.patch) to pinned Rust-for-CPython commit `b812b4a7b9efaca46b98544a8633b7d7e454166b`. Original `Modules/binascii.c` SHA-256 is `6a87f282b9bb1501cbd17ef652d9c003e047402a6a7916d7cc3f8863c58c610e`; original `Modules/_base64/src/lib.rs` is `3bcc6396bc10c4ae3022b05d7093751428414c0b6c694ee9bace47b725218a17`. The NEON patch is the exact measured `4b26b291d3b3931d5932b76a70fe4c18360635a5208eb7f653bfceea36521c46` bytes. The route patch is `b8e8fd86c2c64dff8a44693b14eca28880df4e2514ffe3c2178a7ed00cb42396`. Applying both to a fresh source copy produced the exact built source hashes `e2653c0d14867d5e6340f1845e59f7d9a072e0a3b00c8a9e02aaa2f0b3a4dae1` for C and `7dd969bdf6f4d44d84daf351cd17c79b7c9a54ab8956e41b0a1626a9e6edeba2` for Rust.

## Standalone build and verification

The source was copied into `rust-cpython/work/base64-binascii-route-20260925/source/Modules/` inside this lane. The C control came from the same pinned `Modules/binascii.c` and `Modules/clinic/binascii.c.h`. The candidate came from the two patched source files. The Rust translation unit was the text between `const PAD_BYTE:` and `struct BorrowedBuffer {` in the patched Rust source; this includes the NEON kernel and `rust_base64_encode_into` wrapper. Build commands used pinned `rustc +nightly-2026-09-15 --crate-type staticlib -O -C target-cpu=apple-m1 -C panic=abort` and locked LLVM 23.1.2 `clang`, SHA-256 `f8fa7184dab7d8fa7f6af268a6f1b3aa3d2e598d0cca04dc68447b4c0ca58d8e`. Each C source was compiled with `-O3 -mcpu=apple-m1 -fPIC -mmacosx-version-min=26.0`, `-isysroot /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk`, staged Python 3.16 public and `internal` includes, and the pinned source `Modules` include path for the generated Clinic header. Both used `clang -bundle -undefined dynamic_lookup -mmacosx-version-min=26.0` with the same SDK. Only the candidate link added `libroute_kernel.a`. The first C compile omitted `-isysroot` and failed at `assert.h`; all build attempts are recorded in [compact evidence](data/base64-binascii-route-20260925.json). Build CPU and peak memory were not metered, so total build resource cost is unqualified.

The standalone artifacts can be rebuilt from the pinned source and these patches with this recipe from the worktree root:

```sh
route_work=rust-cpython/work/base64-binascii-route-20260925
pin_modules=/Users/josh/d/python-build/rust-cpython/work/source-inspect/cpython-b812b4a7b9efaca46b98544a8633b7d7e454166b/Modules
stage_include=/Users/josh/d/python-build/rust-cpython/stage/include/python3.16
locked_clang=/Users/josh/d/python-build/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1/bin/clang
mac_sdk=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk
mkdir -p "$route_work/source/Modules/clinic" "$route_work/source/Modules/_base64/src" "$route_work/control" "$route_work/route"
cp "$pin_modules/binascii.c" "$route_work/source/Modules/binascii.c"
cp "$pin_modules/clinic/binascii.c.h" "$route_work/source/Modules/clinic/binascii.c.h"
cp "$pin_modules/_base64/src/lib.rs" "$route_work/source/Modules/_base64/src/lib.rs"
patch -p1 -d "$route_work/source" -i "$PWD/rust-cpython/experiments/base64-neon-20260925.patch"
patch -p1 -d "$route_work/source" -i "$PWD/rust-cpython/experiments/base64-binascii-route-20260925.patch"
python3 - <<'PY'
from pathlib import Path
root = Path('rust-cpython/work/base64-binascii-route-20260925')
source = (root / 'source/Modules/_base64/src/lib.rs').read_text()
(root / 'route-kernel.rs').write_text(source[source.index('const PAD_BYTE:'):source.index('struct BorrowedBuffer {')])
PY
rustc +nightly-2026-09-15 --crate-type staticlib -O -C target-cpu=apple-m1 -C panic=abort "$route_work/route-kernel.rs" -o "$route_work/libroute_kernel.a"
"$locked_clang" -O3 -mcpu=apple-m1 -fPIC -mmacosx-version-min=26.0 -isysroot "$mac_sdk" -I"$stage_include" -I"$stage_include/internal" -I"$pin_modules" -c "$pin_modules/binascii.c" -o "$route_work/control/binascii.o"
"$locked_clang" -O3 -mcpu=apple-m1 -fPIC -mmacosx-version-min=26.0 -isysroot "$mac_sdk" -I"$stage_include" -I"$stage_include/internal" -I"$route_work/source/Modules" -c "$route_work/source/Modules/binascii.c" -o "$route_work/route/binascii.o"
"$locked_clang" -bundle -undefined dynamic_lookup -mmacosx-version-min=26.0 -isysroot "$mac_sdk" "$route_work/control/binascii.o" -o "$route_work/control/binascii.cpython-316-darwin.so"
"$locked_clang" -bundle -undefined dynamic_lookup -mmacosx-version-min=26.0 -isysroot "$mac_sdk" "$route_work/route/binascii.o" "$route_work/libroute_kernel.a" -o "$route_work/route/binascii.cpython-316-darwin.so"
```

The control extension is 90,048 bytes, SHA-256 `c3d278cfee9d3a77f912324d5a2927acdacfe2ec7c28479448d27e72111677f9`; the candidate is 1,513,184 bytes, SHA-256 `b5709f30e0cd77629e3889ed045e5b56e0ea9ffa2975d14a398d9ef41b7ccd49`. That is a 1,423,136-byte extension size increase, about 1.42 MB. `size -m` reports linked `__text` of 27,404 versus 639,548 bytes and linked `__data` of 1,896 versus 4,640 bytes; the route pulls Rust runtime code into the extension. The Rust static library is 18,691,568 bytes before linking. `nm -g` shows `_PyInit_binascii` in both extensions and a defined `_rust_base64_encode_into` only in the candidate; `llvm-objdump --disassemble --symbolize-operands` shows a branch from C at `0x1f78` to that symbol at `0x741c`. The runner checks the exact imported extension path and hash for each arm before calling the public API.

Run the [checker](base64-binascii-route-20260925.py) with staged Python 3.16 after building both extensions:

```sh
/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -S \
  rust-cpython/experiments/base64-binascii-route-20260925.py \
  --scratch rust-cpython/work/base64-binascii-route-20260925 \
  --evidence rust-cpython/experiments/data/base64-binascii-route-20260925.json \
  --benchmark
```

The checker loaded each extension as `binascii` and used the staged `base64.py`. Control and route matched on 128 exact outcomes per arm: 19 boundary and bulk lengths × three deterministic patterns through both `base64.b64encode` and direct `binascii.b2a_base64`; alternate alphabet, padding, wrapping, newline, invalid alphabet, bytes, bytearray, memoryview, array, rejected strided memoryview and invalid input; plus a 20,000-record public catalog. Three runs in the evidence each passed. The large input checks cover both padding tails. Fresh process import and encoding passes had matching output hashes.

| Input bytes | Control median public wall | Route median public wall | Route/control |
| --- | ---: | ---: | ---: |
| 65,538 | 23.99 µs | 8.55 µs | 0.356 |
| 1,048,576 | 386.38 µs | 137.75 µs | 0.357 |

The table uses the third bounded run: five alternating pairs per size, about 32 MiB encoded per sample. At 65,538 bytes, median kernel user/system CPU per call was 23.9/0.1 µs for control and 8.5/0.0 µs for route. At 1 MiB it was 378.9/6.0 µs for control and 131.6/4.5 µs for route. Exact raw samples, order, host load, and swap are in the JSON. Earlier runs found similar route/control ratios near 0.35–0.37. Host load stayed near three, and OrbStack consumed CPU; these observations support a source candidate, not a quiet-host speed qualification.

The fresh process memory pass encoded one 1 MiB input after loading its assigned extension in an otherwise identical process. Both arms also imported the staged `binascii` at startup before replacing it. Three alternating control/route pairs reported candidate peak RSS higher by 1,671,168, 1,605,632, and 2,031,616 bytes with `/usr/bin/time -l`. A subsequent control/control pair differed by 311,296 bytes. All fresh process output hashes matched and each had zero swaps. The timed process's peak RSS includes both loaded extensions and cannot attribute memory. The candidate's larger file and resident cost are material. The source patch does not include build-system wiring or establish package-level compatibility; an integrated build would need to link the Rust archive into `binascii` on AArch64 and confirm other platform behavior. No test suite, formatter, linter, hook, full CPython build, commit, or push ran in this lane.
