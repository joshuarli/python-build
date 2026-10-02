# Binascii Rust dependency licenses

The Rust checksum path uses `crc32fast` for CRC-32. The extension also serves
the public `base64` module directly, using the core-only configurations of
`base64` and `data-encoding`. No Rust standard library or allocation crate
is used by this extension. Exact versions and registry checksums are pinned in the overlay
`Cargo.lock`.

| Crate | Version | Declared license |
| --- | --- | --- |
| `crc32fast` | 1.5.2 | MIT OR Apache-2.0 |
| `base64` | 0.23.1 | MIT OR Apache-2.0 |
| `data-encoding` | 2.9.0 | MIT |

The crate offers permissive MIT and Apache-2.0 license choices.
