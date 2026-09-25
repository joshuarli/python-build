# Rust ZIP codec dependency licenses

ZIP method 8 uses the locked `flate2` Rust backend. Its enabled dependency
closure is:

| Crate | Version | Declared license |
| --- | --- | --- |
| `flate2` | 1.1.9 | MIT OR Apache-2.0 |
| `crc32fast` | 1.5.2 | MIT OR Apache-2.0 |
| `cfg-if` | 1.0.4 | MIT OR Apache-2.0 |
| `miniz_oxide` | 0.8.9 | MIT OR Zlib OR Apache-2.0 |
| `adler2` | 2.0.1 | 0BSD OR MIT OR Apache-2.0 |
| `simd-adler32` | 0.3.10 | MIT |

Every crate version and registry checksum is pinned in the overlay
`Cargo.lock`. Each declared license set includes a permissive license.
