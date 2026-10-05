# Aggregate helper license evidence

The local `cpython-rust-source-aggregate356` crate is licensed under PSF-2.0.
It adds no registry dependency. Its eleven path dependencies reuse the original
CSV, JSON, typing, tokenize, datetime, threading, UUID, collections, SQLite,
warnings and socket helper crates without
copying their source or changing their dependency features.

The existing workspace `Cargo.lock` remains the version/checksum authority for
all inherited third-party packages. Only the aggregate local package dependency roster changes; existing
registry records and checksum identities are unchanged. CSV dependency license evidence remains in
`../_csv_rs/THIRD_PARTY_LICENSES.md`; JSON dependency evidence remains in
`../_json_rs/THIRD_PARTY_LICENSES.md`. The inherited UUID dependency is
`uuid` 1.26.1 (MIT OR Apache-2.0), with its existing `std`, `v3`, `v4`, `v5`
features and their original locked dependency closure. The aggregate root also calls the existing local `cpython-build-helper` from
its build script so the root cdylib receives the original platform linker
policy. The existing CPython binding/build helper dependency closure is
retained unchanged.

The source-built Rust standard library retains its original MIT OR Apache-2.0
license and notices. This crate does not supply a replacement allocator,
panic runtime or standard-library implementation.
