# Rust CSV dependencies

The added Cargo lock closure records these package versions and checksums:

| Crate | Version | Declared license |
| --- | --- | --- |
| `csv` | `1.4.0` | MIT OR Unlicense |
| `csv-core` | `0.1.13` | MIT OR Unlicense |
| `itoa` | `1.0.18` | MIT OR Apache-2.0 |
| `memchr` | `2.8.3` | MIT OR Unlicense |
| `ryu` | `1.0.23` | Apache-2.0 OR BSL-1.0 |
| `serde_core` | `1.0.229` | MIT OR Apache-2.0 |
| `serde_derive` | `1.0.229` | MIT OR Apache-2.0 |
| `syn` | `3.0.6` | MIT OR Apache-2.0 |

The CSV crates are maintained in [BurntSushi/rust-csv](https://github.com/BurntSushi/rust-csv).
The remaining license declarations come from the corresponding crates.io
packages. These permissive licenses are compatible with the lane's PSF-2.0
CPython base. `serde_derive` and `syn` are present in the lock closure through
Serde's conditional dependency metadata; the CSV bridge does not invoke Serde.
