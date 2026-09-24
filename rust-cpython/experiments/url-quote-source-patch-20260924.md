# Guarded URL quotation source patch, 2026-09-24

## Candidate and source identity

`rust-cpython/patches/0001-rust-url-quote.patch` applies the accepted lean guarded URL quotation overlay to the pinned Rust-for-CPython fork. The verified codeload archive was 44,210,863 bytes with SHA-256 `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`; its commit is `b812b4a7b9efaca46b98544a8633b7d7e454166b`. The initial and post-application `Cargo.lock` SHA-256 was `55f5f3bf547d3b9e7896a5feb6d17aa3b607610c7c21d919164f0877a8d05023`. Downloads, extractions, and compile products stayed in this lane's ignored `rust-cpython/work/url-source-patch/` directory.

`rust-cpython/patches/manifest.json` records the patch digest, authorship, source, license, compatibility, and reproducer. The build driver's `_source_patch_inputs()` accepted the manifest, and `_apply_source_patches()` applied the patch to a second fresh extraction while rechecking `Cargo.lock`. `git apply --check` also passed on that extraction before application. The patch contains no Cargo package, dependency, or lock change.

## Build route and boundary

The patch adds `Modules/_rust_url_quote/quote.rs`, a two-pass `no_std` kernel, and `Modules/_rust_url_quote/module.c`, which owns all CPython object checks, allocation, and errors. The C module uses a stateless multiphase definition with `m_size = 0` and declares per-interpreter GIL support. The existing Python `quote_from_bytes` validation, normalization, and early return remain ahead of the branch. Only exact `bytes` input, normalized exact `bytes` safe, and length below 200,000 enter Rust. Other cases use the unchanged quoter path. A missing required extension raises at `urllib.parse` import.

`Makefile.pre.in` builds a private static archive through `rustup run nightly-2026-09-15 rustc --edition=2024 --crate-type=staticlib -C opt-level=3 -C panic=abort --target=aarch64-apple-darwin`. It is a normal build-directory target dependent on the Rust source. `MODULE__RUST_URL_QUOTE_LDEPS` orders it before the shared extension link; `MODULE__RUST_URL_QUOTE_LDFLAGS` places it after the C object. The rule has no ignored error or alternate compiler path: absent `rustup`, pinned compiler, or archive stops the build. The build driver already sets `RUSTUP_TOOLCHAIN` and constrains PATH to the pinned toolchain. This private archive avoids adding the much larger existing Cargo staticlib to a small shared C wrapper.

`configure.ac`, `configure`, and `Modules/Setup.stdlib.in` gate and select the module with the existing `HAVE_CARGO` condition. The pinned generated `configure` says Autoconf 2.72; the host has 2.73. Its minimal new stanza mirrors the neighboring `_base64` module, preserving the generator version and unrelated output. `sh -n configure` passed. A full configure run remains part of serial qualification.

## Focused evidence and limits

An isolated `Modules/makesetup` probe used the previously configured release `Makefile.pre` as a fixture with the patched archive rule and setup line. It generated a shared-module rule with `module.o $(MODULE__RUST_URL_QUOTE_LDEPS)` as prerequisites and `module.o $(MODULE__RUST_URL_QUOTE_LDFLAGS) $(LIBPYTHON)` in that order at link. This verifies `makesetup` ordering, not the new `configure` substitutions in a complete build. A subsequent `make -n` traversed broader fixture prerequisites and was interrupted after about 15 seconds without compiling; it supplied no further evidence.

The pinned nightly compiled the archive; locked LLVM 23.1.2 Clang and the Xcode macOS SDK compiled the C object and linked a bundle against the archive. The bundle was arm64; `otool -L` listed only `/usr/lib/libSystem.B.dylib`. `nm -gU` found one defined `_PyInit__rust_url_quote` and one defined `_quote_ascii`, without a duplicate kernel symbol. A small overlay on the existing pinned interpreter showed `urllib.parse.quote(b'a b', safe='') == 'a%20b'` and observed the call through the native wrapper. Bytearray and already-safe examples made no native call. A separate overlay without the extension raised `ModuleNotFoundError` naming `_rust_url_quote` at parser import.

| `/usr/bin/time -l` command | User CPU | System CPU | Peak RSS | Swaps |
| --- | ---: | ---: | ---: | ---: |
| Download locked archive | 0.22 s | 0.16 s | 7,798,784 B | 0 |
| First extraction | 0.22 s | 1.61 s | 3,948,544 B | 0 |
| Fresh application-check extraction | 0.23 s | 1.63 s | 3,948,544 B | 0 |
| Pinned Rust archive compile | 0.05 s | 0.13 s | 101,531,648 B | 0 |
| SDK-correct C compile | 0.05 s | 0.05 s | 54,083,584 B | 0 |
| Bundle link | 0.08 s | 0.10 s | 35,602,432 B | 0 |
| Public-call overlay check | 0.02 s | 0.01 s | 22,757,376 B | 0 |

These timed commands used 4.56 user plus system CPU seconds, with a largest reported per-process maximum RSS of 101,531,648 bytes. The first attempted C compile omitted the SDK and failed finding `assert.h`; it consumed 0.03 user plus 0.05 system CPU seconds, peaked at 32,800,768 bytes, and was corrected before linking. Small manifest and `makesetup` checks were not separately timed; the interrupted `make -n` probe has no CPU or RSS measurement and is excluded from that total. No full CPython build, PGO, end-to-end test suite, or performance comparison was run.

The next serial gate is a fresh full configure/build/install using the manifest, followed by installed-extension inspection, the 2,177 public differential cases, unchanged URL tests, a subinterpreter import/call, and the agreed matched workload/resource comparison with valid parser caches. This patch is a reproducible source candidate, not an installed-build or upstream-resource verdict.
