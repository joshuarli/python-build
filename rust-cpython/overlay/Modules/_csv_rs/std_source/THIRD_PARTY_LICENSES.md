# Source-built Rust standard library

The compiler source is the official rust-src archive for nightly-2026-09-15,
version `1.100.0-nightly (574ff7d98 2026-09-14)`, revision
`574ff7d98bd6d037e5236a8453029173b32631fd`. The lane source lock pins its URL,
SHA256 `dee5c574fab79b4b45aa24f7260613977d820e62013a7923647c066c10bdaec5`
and 5,927,464-byte size. Archive verification and fresh safe extraction own the
integrity of compiler-source path crates. Their authentic Cargo versions,
including `std`, `core`, `alloc`, and `panic_abort` at `0.0.0`, have no registry
checksum. No checksum is invented for them.

`Cargo.lock` here is the byte-identical upstream library lock, SHA256
`75848db58a70444bfb62c649b103d19c5d92fede325eb0c8c0e5442848448669`.
It preserves 31 registry package version/checksum pins and 19 source-owned
path package identities. It is separate from the application overlay lock;
that lock and exact CSV 1.4.0 dependency remain unchanged. Cargo's vendored
source configuration and package/file checksums govern registry inputs;
the verified compiler-source archive governs path inputs.

The copied full texts and embedded notices are indexed in `NOTICES.json` with
archive-relative source paths, original hashes, excerpt ranges where applicable,
and hashes of distributed notice bytes. General Rust code uses MIT OR Apache-2.0.
Compiler-builtins 0.1.160 has mixed MIT AND Apache-2.0 WITH LLVM-exception AND
(MIT OR Apache-2.0) terms; its full notice is retained. The direct source
inclusions backtrace 0.3.76, core_arch 0.1.5, core_simd 0.1.0, std_float and
compiler-builtins/libm also retain their notices. The libm text includes
contributor, musl, Sun/FreeBSD math and Arm notices; embedded Crossbeam MIT
and rust-memchr copyright notices accompany the general license texts.

The included registry notice scope is addr2line 0.27.1, adler2 2.0.1,
cfg-if 1.0.4, gimli 0.34.0, hashbrown 0.17.1, libc 0.2.189, memchr 2.8.3,
miniz_oxide 0.9.1, object 0.39.1, rustc-demangle 0.1.28 and
rustc-literal-escaper 0.0.8. All available alternative license texts are
preserved conservatively. The inventory came from the public sysroot query;
it does not claim that every workspace lock package is compiled or linked.
Actual compiler units/includes must remain within this notice scope or extend
it explicitly. Redistributing the entire compiler-source archive requires its
broader license inventory, beyond these selected source notices.

These pins and notices establish source provenance, not ABI compatibility,
correct loading, Rust coverage, or a measured memory improvement. The normal
producer must compare actual rustc revision, preserve source locks, and record
new compiler-unit and staged artifact ownership before qualification.
