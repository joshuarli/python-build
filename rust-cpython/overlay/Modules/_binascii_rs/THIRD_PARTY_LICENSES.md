# Binascii Rust dependency licenses

The Rust checksum path uses `crc32fast` for CRC-32. The extension also serves
the public `base64` module through the in-tree `_base64` crate, so one image
loads for both; that crate's `base64` and `data-encoding` dependencies are
linked in. Exact versions and registry checksums are pinned in the overlay
`Cargo.lock`.

| Crate | Version | Declared license |
| --- | --- | --- |
| `crc32fast` | 1.5.2 | MIT OR Apache-2.0 |
| `base64` | 0.23.1 | MIT OR Apache-2.0 |
| `data-encoding` | 2.9.0 | MIT |

The crate offers permissive MIT and Apache-2.0 license choices.
