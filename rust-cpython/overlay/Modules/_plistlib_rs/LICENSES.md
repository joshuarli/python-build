# Rust dependency licenses

The `_plistlib_rs` dependency graph is pinned by `overlay/Cargo.lock`. Its
registry packages declare these license expressions:

| Package | Version | License |
| --- | --- | --- |
| aho-corasick | 1.1.5 | Unlicense OR MIT |
| base64 | 0.23.1 | MIT OR Apache-2.0 |
| bindgen | 0.72.1 | BSD-3-Clause |
| bitflags | 2.13.1 | MIT OR Apache-2.0 |
| cexpr | 0.6.0 | Apache-2.0/MIT |
| cfg-if | 1.0.4 | MIT OR Apache-2.0 |
| clang-sys | 1.9.1 | Apache-2.0 |
| deranged | 0.5.8 | MIT OR Apache-2.0 |
| either | 1.17.0 | MIT OR Apache-2.0 |
| equivalent | 1.0.2 | Apache-2.0 OR MIT |
| glob | 0.3.4 | MIT OR Apache-2.0 |
| hashbrown | 0.17.1 | MIT OR Apache-2.0 |
| indexmap | 2.14.2 | Apache-2.0 OR MIT |
| itertools | 0.13.0 | MIT OR Apache-2.0 |
| itoa | 1.0.18 | MIT OR Apache-2.0 |
| libc | 0.2.189 | MIT OR Apache-2.0 |
| libloading | 0.8.9 | ISC |
| log | 0.4.33 | MIT OR Apache-2.0 |
| memchr | 2.8.3 | Unlicense OR MIT |
| minimal-lexical | 0.2.1 | MIT/Apache-2.0 |
| nom | 7.1.3 | MIT |
| num-conv | 0.2.2 | MIT OR Apache-2.0 |
| plist | 1.10.1 | MIT |
| powerfmt | 0.2.0 | MIT OR Apache-2.0 |
| prettyplease | 0.2.37 | MIT OR Apache-2.0 |
| proc-macro2 | 1.0.107 | MIT OR Apache-2.0 |
| quick-xml | 0.42.0 | MIT |
| quote | 1.0.47 | MIT OR Apache-2.0 |
| regex | 1.13.1 | MIT OR Apache-2.0 |
| regex-automata | 0.4.18 | MIT OR Apache-2.0 |
| regex-syntax | 0.8.11 | MIT OR Apache-2.0 |
| rustc-hash | 2.1.3 | Apache-2.0 OR MIT |
| serde | 1.0.229 | MIT OR Apache-2.0 |
| serde_core | 1.0.229 | MIT OR Apache-2.0 |
| serde_derive | 1.0.229 | MIT OR Apache-2.0 |
| serde_json | 1.0.151 | MIT OR Apache-2.0 |
| shlex | 1.3.0 | MIT OR Apache-2.0 |
| syn | 2.0.119 | MIT OR Apache-2.0 |
| syn | 3.0.6 | MIT OR Apache-2.0 |
| time | 0.3.55 | MIT OR Apache-2.0 |
| time-core | 0.1.9 | MIT OR Apache-2.0 |
| time-macros | 0.2.32 | MIT OR Apache-2.0 |
| unicode-ident | 1.0.24 | (MIT OR Apache-2.0) AND Unicode-3.0 |
| windows-link | 0.2.1 | MIT OR Apache-2.0 |
| zmij | 1.0.23 | MIT |

The direct `plist` dependency is MIT licensed. The direct `serde_json`
dependency permits either MIT or Apache-2.0. All declared licenses in the
locked dependency graph are permissive and compatible with this coverage
overlay.
