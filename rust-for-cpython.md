# Remaining Rust-for-CPython work

The initial isolated CPython 3.16 build-lane task is complete. Its build
commands, locked source/toolchains, validation evidence, and ranked migration
candidates are maintained in [`rust-cpython/README.md`](rust-cpython/README.md).
This file now records only the remaining stdlib work and the current proof
boundaries.

## Current evidence

- The isolated lane builds and tests Rust-for-CPython CPython 3.16.0a0.
- The Rust `_base64` extension builds, imports, and passes byte-for-byte checks
  against `binascii` for representative bytes, `bytearray`, and `memoryview`
  inputs. Its measured performance is in
  [`rust-cpython/PERFORMANCE.md`](rust-cpython/PERFORMANCE.md).
- `_base64` is an integration proof, not a public stdlib optimization:
  `Lib/base64.py` still routes through `binascii`. The Rust path is faster for
  64-byte inputs but 42–48% slower at 4 KiB and above in the measured cases.
- A separate [`zlib-proof`](rust-cpython/zlib-proof/README.md) links the pinned
  `zlib-rs` 0.6.7 C ABI beneath the unchanged CPython `Modules/zlibmodule.c`.
  `test_zlib` passed 85 tests (2 skipped); `test_gzip`, `test_tarfile`,
  `test_zipfile`, `test_zipimport`, and `test_binascii` passed 1,807 tests
  (37 skipped). The extension had no dynamic `libz` dependency.

## Work still open

- **The zlib proof is not a production migration.** The ordinary lane build
  still links `Modules/zlibmodule.c` to platform zlib; the Rust backend exists
  only in the separate proof overlay. Performance and compressed-byte
  comparisons remain open.
- No stdlib module has been migrated into the public product or broadly
  optimized in Rust. Beyond the isolated `_base64` extension and the zlib
  backend proof, ranked entries in `rust-cpython/README.md` are candidates,
  not completed work.
- A user-visible stdlib migration has not started. Choose a target from the
  ranked map before implementation.

For the first real migration, preserve the existing Python API and semantics,
keep a Python/C fallback where it helps compatibility, run the relevant
unchanged CPython tests on both builds, add differential tests for edge cases,
and compare realistic workloads with the current C or Python implementation.
Keep the production CPython 3.14.6 build and frozen Linux targets unchanged
unless a separate scope decision says otherwise.
