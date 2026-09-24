# zlib-rs proof

This is an isolated backend proof for the Rust-for-CPython CPython 3.16 lane.
It leaves the pinned CPython `Modules/zlibmodule.c` unchanged and links that
module against the static C ABI from `libz-rs-sys-cdylib` 0.6.7. The resulting
extension exports Rust zlib symbols and has no dynamic `libz` dependency, so
the ordinary Python `zlib` API and its existing C wrapper exercise zlib-rs.

This does not change the production CPython 3.14.6 build or promote zlib-rs as
a production dependency. The backend archive and its Cargo dependencies are
locked in `sources.lock.json` and the archive's `Cargo.lock`. Build outputs
stay under the ignored `rust-cpython/work/` tree.

## Reproduce

On native Apple Silicon macOS, build the same-source no-Rust interpreter first:

```text
python3.14 rust-cpython/build.py fetch
python3.14 rust-cpython/build_no_rust.py
python3.14 rust-cpython/zlib-proof/build.py fetch
python3.14 rust-cpython/zlib-proof/build.py build
python3.14 rust-cpython/zlib-proof/build.py test
```

`fetch` verifies the exact 0.6.7 crate archive and retrieves its locked Cargo
dependencies. `build` uses the pinned Rust nightly and LLVM 23 linker, replaces
only the zlib library link for the existing CPython extension, and places the
result in a `PYTHONPATH` overlay. `test` runs the unchanged CPython tests for
zlib and its main consumers against that overlay.

The proof report is written to `rust-cpython/results/zlib-proof.json`; detailed
build and test logs are under `rust-cpython/logs/`.

## Scope and current result

The proof exercises the C zlib ABI beneath CPython's existing module. It
covers the public functions, streaming objects, flush modes, dictionaries,
checksums, gzip/tar/ZIP consumers, and compressed imports through CPython's
unchanged tests. The Rust engine's runtime version is reported separately from
the Xcode SDK zlib header version.

On 2026-09-24, CPython `test_zlib` passed 85 tests (2 skipped). The consumer
group `test_gzip`, `test_tarfile`, `test_zipfile`, `test_zipimport`, and
`test_binascii` passed 1,807 tests (37 skipped). The extension linked only
`libSystem` dynamically; the zlib symbols were defined in the extension from
the Rust static library.

This is compatibility evidence for the tested CPython 3.16 source pin and
platform. Compression bytes, performance, other platforms, and the complete
CPython suite still need separate evaluation before considering a production
backend change.

## Attribution

`libz-rs-sys-cdylib` and `zlib-rs` are distributed under the Zlib license.
The immutable crate archive and exact Cargo dependency lock are checked before
the proof build; no crate source or prebuilt library is copied into the product.
