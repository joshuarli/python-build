# Rust regular expression dependency licenses

The `_re_rs` bridge uses `regex-automata` directly with the same standard-library,
meta, PikeVM, hybrid, one-pass, backtracking, inlining and literal-search features
selected by the locked `regex` byte builder. Unicode features remain disabled
(patterns and subjects are ASCII). The `regex` crate remains a development-only
reference for constructor and search parity tests. `regex-syntax` still parses
patterns at compile time. The complete dependency closure is pinned in
the overlay `Cargo.lock`:

| Crate | Version | Declared license |
| --- | --- | --- |
| `regex` | 1.13.1 | MIT OR Apache-2.0 |
| `regex-automata` | 0.4.18 | MIT OR Apache-2.0 |
| `regex-syntax` | 0.8.11 | MIT OR Apache-2.0 |
| `aho-corasick` | 1.1.5 | MIT OR Unlicense |
| `memchr` | 2.8.3 | MIT OR Unlicense |

Every version and registry checksum is recorded in that lockfile. The selected
licenses are compatible with the lane's PSF-2.0 CPython base.
