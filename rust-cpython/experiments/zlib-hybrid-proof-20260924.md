# Prefixed zlib-rs inflate with platform zlib compression

**Verdict: keep as a correctness candidate; do not promote yet.** The pinned
CPython 3.16 hybrid preserved all 876 checked compression byte streams and
passed its focused stdlib tests. No paired workload timing, allocation, or
process memory parity study has run for this hybrid. The full build installed
successfully but its first command returned failure at an erroneous
post-install symbol guard; the corrected guard passed against those exact
installed bytes without another expensive build.

## Boundary and source evidence

`build --zlib-hybrid` compiles the pinned `libz-rs-sys-cdylib` 0.6.7 archive
with `custom-prefix` and `LIBZ_RS_SYS_PREFIX=python_build_rs_`. The guarded
source patch reroutes `inflateInit2_`, `inflate`, `inflateEnd`, `inflateCopy`,
and `inflateSetDictionary` in `Modules/zlibmodule.c`. `deflate*`, `crc32*`,
`adler32*`, `zlibVersion`, and `binascii` use platform zlib. The module links
both `/usr/lib/libz.1.dylib` and the prefixed Rust archive; `binascii` links
only platform zlib. Other CPython builds receive the inert guarded source
patch, without the hybrid compile definition.

The verified CPython archive is 44,210,863 bytes, SHA-256
`965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`,
source commit `b812b4a7b9efaca46b98544a8633b7d7e454166b`, Cargo.lock
SHA-256 `55f5f3bf547d3b9e7896a5feb6d17aa3b607610c7c21d919164f0877a8d05023`.
The verified zlib-rs crate archive SHA-256 is
`09ab8373154ca2cd2ba61b44dcf28bcb91733f1f7652ce96a502c5ae3b7ca702`;
its Cargo.lock SHA-256 is
`52a4ebe3f39273d7e27f3a2cb4a8a216877be6c1fc0394e18f26f7ec98b28a82`.
The authored patch SHA-256 is
`8882e0b3e1704e4d7c1d5479af37c8fe1d774dcb6a31b61359947f5f87be3528`.

Fresh extraction into `rust-cpython/work/hybrid-preflight-source` applied
both manifest patches with forward and reverse checks. The intended
`Modules/zlibmodule.c` changed SHA-256 from
`36390fc1b0bdaf7da332d732c67cbe9669bd3f6e923a3e5810b4662159a0e20c`
to `4a73284a91b02034554c0953451943ad3fe2d742050355a4b6b3aa70fba9960b`.
The first preflight edit had an incorrect patch hunk count and stopped at
`corrupt patch at line 26`; it was corrected before any archive or full build.
That untimed attempt has no resource measurement, so the timed records below
are not a complete total for every command in the lane.

The offline prefixed archive SHA-256 is
`e81f24921a86c072a0dcc5ee880dbd9c2ac0f51151e8f5e7e79bda92c9ec90ed`.
`llvm-nm -g --defined-only` showed all five required
`_python_build_rs_inflate*` definitions and no unprefixed `inflate`,
`deflate`, or `zlibVersion` definitions. The installed `zlib` extension
SHA-256 is `34e0cce48e60c1ba6622b98615a0d239a5e48cbe3cb36a428e65c623b7ba970c`;
the installed `binascii` SHA-256 is
`6a20ea45f176c13080094e5620259485e0958b171fd6085d8cbcb88a7750e38a`.
The installed module has all five prefixed inflate definitions, no
unprefixed zlib definitions, loads `/usr/lib/libz.1.dylib`, and reports
header and runtime version `1.2.12`. Exact defined-symbol checks exclude the
unprefixed `inflate*`, `deflate*`, and `zlibVersion` namespaces. The installed
binary identity is in the ignored
`rust-cpython/results/hybrid-postinstall-validation-exact-20260924.json`.

Default and `--zlib-rs` modes omit `PYTHON_BUILD_ZLIB_HYBRID`; the latter
retains its original archive-only `ZLIB_LIBS` recipe. With that definition
removed from the actual module compile command, the original and patched
`zlibmodule.c` preprocessed to identical bytes, SHA-256
`edf2eb0b69a0714a75fd1e87dadc14e523d52d8a57f71de16dffba55d3547e63`.
This checks the guarded source's inactive semantics. Those two modes were
not rebuilt here; their source application succeeded in the fresh preflight.

## Correctness results

The platform control at `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`
reports the same CPython commit and source archive. The existing
`zlib-byte-compat.py` child encoder ran separately under control and hybrid.
Both generated and decoded 876 cases spanning zlib, streaming zlib, gzip,
and ZIP. The outputs matched **876/876 byte for byte**; both reported runtime
zlib 1.2.12. Each interpreter then decoded the other side's 876 streams.
Raw encoded streams and cross-decode results are retained in ignored
`rust-cpython/results/hybrid-byte-*-20260924.json` and
`hybrid-crossdecode-*-20260924.json`.

Unchanged CPython `test_zlib`, `test_gzip`, `test_tarfile`, `test_zipfile`,
`test_zipimport`, and `test_binascii` passed: 1,892 tests run, 39 skipped,
six of six files, 24.7 seconds of suite time. `test_zlib` includes incomplete
and truncated input, stream copy, and dictionary cases. A direct six-case
control/hybrid comparison additionally matched malformed headers, damaged
checksums, truncated one-shot and streamed input, stream copy, and dictionary
decode. No semantic difference appeared. The focused test log is
`rust-cpython/logs/hybrid-cpython-focused-tests-20260924.log`; the direct
inputs and results are under ignored `rust-cpython/results/hybrid-edge-*`.

## Resource records and failed guard

All substantial commands used `/usr/bin/time -l`; the named ignored files
retain full kernel-accounted output, including swaps. Maximum RSS is the
largest process RSS reported for the waited command, not simultaneous tree
memory. USS/PSS and allocation counts were not measured.

| Command, raw `results/` record | User + system CPU s | Elapsed s | Max process RSS bytes | Swaps |
| --- | ---: | ---: | ---: | ---: |
| Prefixed archive, `hybrid-preflight-cargo-time-20260924.txt` | 3.27 + 0.28 | 2.45 | 230,899,712 | 0 |
| Full offline build/install, `hybrid-full-build-time-20260924.txt` | 702.46 + 105.98 | 262.74 | 1,820,459,008 | 0 |
| First post-install probe, `hybrid-postinstall-validation-time-20260924.txt` | 0.07 + 0.03 | 0.13 | 35,209,216 | 0 |
| First corrected probe, `hybrid-postinstall-validation-fixed-time-20260924.txt` | 0.13 + 0.05 | 0.25 | 35,995,648 | 0 |
| All-symbol probe, `hybrid-postinstall-validation-all-symbols-time-20260924.txt` | 0.15 + 0.07 | 0.28 | 36,126,720 | 0 |
| Exact-symbol probe, `hybrid-postinstall-validation-exact-time-20260924.txt` | 0.14 + 0.06 | 0.25 | 36,339,712 | 0 |
| Inactive-guard preprocessing, `hybrid-inactive-guard-preflight-time-20260924.txt` | 0.09 + 0.05 | 0.19 | 27,754,496 | 0 |
| Focused CPython tests, `hybrid-cpython-focused-tests-time-20260924.txt` | 15.53 + 7.06 | 24.78 | 170,524,672 | 0 |

The full build used 808.44 CPU seconds, below the 1,200 second lane cap, and
its largest process RSS was below 2.5 GiB. It exited 1 after install because
the first guard searched for `_deflateInit2_` as a substring and found it
inside `_python_build_rs_deflateInit2_`. Exact defined-symbol matching fixed
the guard. A subsequent read-only post-install validation passed on the
installed bytes. The first post-install probe also exited 1 because its
ad hoc command passed a relative interpreter path while setting stage as its
working directory; its raw traceback and resource record were retained.
No compiler was rerun after the guard correction. Therefore the corrected
builder's final exit status is not established by a fresh full build, while
the compiled and installed candidate's identity and behavior are checked.

This was a native macOS diagnostic with the sealed offline build recipe.
It is not a workload performance or memory parity result. Promotion still
requires paired quiet-host timing, external memory, and allocation evidence.
