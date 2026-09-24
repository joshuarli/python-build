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

## Work still open

- **zlib has no Rust proof or integration here.** The pinned source still uses
  `Modules/zlibmodule.c` and the existing zlib backend. Rust zlib projects in
  the roadmap are references only.
- No stdlib implementation beyond the isolated `_base64` extension proof has
  been migrated or broadly optimized in Rust. The ranked entries in
  `rust-cpython/README.md` are candidates, not completed work.
- A user-visible stdlib migration has not started. Choose a target from the
  ranked map before implementation.

For the first real migration, preserve the existing Python API and semantics,
keep a Python/C fallback where it helps compatibility, run the relevant
unchanged CPython tests on both builds, add differential tests for edge cases,
and compare realistic workloads with the current C or Python implementation.
Keep the production CPython 3.14.6 build and frozen Linux targets unchanged
unless a separate scope decision says otherwise.
