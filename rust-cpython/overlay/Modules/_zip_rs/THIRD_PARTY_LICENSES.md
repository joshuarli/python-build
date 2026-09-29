# Rust ZIP codec dependency licenses

ZIP method 8 and the ZIP CRC-32 use the locked `libz-rs-sys` Rust crate, the
C-API surface of the `zlib-rs` port of zlib. Its enabled dependency closure is:

| Crate | Version | Declared license |
| --- | --- | --- |
| `libz-rs-sys` | 0.6.7 | Zlib |
| `zlib-rs` | 0.6.7 | Zlib |

Every crate version and registry checksum is pinned in the overlay
`Cargo.lock`. The Zlib license is permissive and compatible with the
project's licensing.
