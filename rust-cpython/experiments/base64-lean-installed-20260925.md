# Installed lean Base64 route on macOS arm64

**Verdict: keep the route optional.** The pinned Rust-for-CPython 3.16 build
installed a `binascii` extension containing the lean AArch64 Rust encoder.
Fresh patched source identities, the installed import path, linked symbol,
and exact public Base64 output all passed. The host was busy, so this result
does not establish an installed workload speed or memory gain.

## Reproduction

The source archive is pinned to commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b`, SHA-256
`965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`.
The [optional patch](../patches/0012-base64-lean.patch) has SHA-256
`5adfdd86fc1491be2d56b3ffb466d6bfc5687bbdf30a22cfd69277be044de7c0`.
It combines the checked C route and lean kernel from the earlier
[standalone result](base64-lean-route-20260925.md). The Rust file omits one
trailing blank line; the C hunk retains two whitespace-only blank lines so
its built source hash remains identical to the measured standalone route.
The resulting
`Modules/binascii.c` and `Modules/_base64/src/lean_route.rs` SHA-256 values
are `e2653c0d14867d5e6340f1845e59f7d9a072e0a3b00c8a9e02aaa2f0b3a4dae1`
and `0a9b3b5e7a823b8a2df94025fe91ef6f7cbfd8ab808b3921b744aa32213e1355`.
`Cargo.lock` stayed at its pinned digest.

From the repository root, with the locked source, LLVM and Cargo inputs
already cached:

```sh
python3 rust-cpython/build.py doctor
python3 rust-cpython/build.py build --variant base64-lean --base64-lean
rust-cpython/stage-base64-lean/bin/python3.16 -I -S \
  rust-cpython/experiments/base64-lean-installed-20260925.py
```

The build uses pinned `rustc +nightly-2026-09-15` to compile the `no_std`
kernel as a static archive with `-O -C target-cpu=apple-m1 -C panic=abort`.
The archive lives at `work/variants/base64-lean/base64-lean/liblean_route.a`
so CPython's PGO clean cannot remove it. An exact-match rewrite of the
generated Makefile adds that archive only to the `binascii` shared-module
rule, with `-dead_strip` and only `PyInit_binascii` exported. The before and
after Makefile digests and archive digest are in the
[compact evidence](data/base64-lean-installed-20260925.json); the full recipe is
also in `results/build-base64-lean.json` after a build. The default build and
Linux x86-64 select neither this patch nor the link rule.

## Installed evidence

The installed `binascii.cpython-316-darwin.so` is 95,024 bytes, SHA-256
`4bf30e7a92d2227b8c80efdd06bdeb69081120130125b1618699b9fea377411b`.
`llvm-nm` shows `PyInit_binascii` as its sole defined global and
`rust_base64_encode_into` as a local linked symbol. Its dynamic libraries
are platform `libz` and `libSystem`. The installed interpreter imported that
exact extension from `stage-base64-lean`.

The focused checker compared public `base64.b64encode` and
`binascii.b2a_base64` against an independent Python Base64 encoder for 18
lengths from 0 through 1,048,578 bytes, including all three padding tails
above the 4,096-byte route threshold. It also checked bytes, bytearray,
memoryview, newline, unpadded output, and alternate alphabet. Every output
matched. The concatenated expected-output digest was
`22d307822213140dcd2c97b88f4d237fcc79bdaf6ba0a929b5875103b49eb633`;
the existing default installed interpreter yielded the same digest. Its
`binascii` file is 93,152 bytes, so the observed installed file delta is
1,872 bytes. That default install predates this variant build and has its
own PGO profile, so the file-size delta is diagnostic rather than a matched
binary comparison.

The first build failed after 114.43 s because the Rust archive was placed
inside the PGO-cleaned build directory. Moving it to the variant work root
resolved the failure; the second build completed in 363.75 s. Darwin
`/usr/bin/time -l` reported 679.09 user and 105.31 system CPU seconds and
1,833,844,736 bytes maximum resident size for the successful command. It
reported zero process swaps; system swap usage after the build was 235.88
MiB. Short-lived child memory and process-count peaks were not separately
sampled. The first failed command and preliminary fetch, patch, and doctor
failures are retained compactly in the evidence JSON.

No CPython test suite, formatter, linter, hook, comparative timing pair,
commit, or push ran. Broader semantic and workload qualification, and Linux
arm64 support for this route, remain open.
