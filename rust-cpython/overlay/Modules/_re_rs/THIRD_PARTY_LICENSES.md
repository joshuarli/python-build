# Rust regular expression dependency licenses

The `_re_rs` bridge uses the locked `regex` crate with its standard-library and
performance features except forced dispatch inlining, and no Unicode features (patterns and subjects are ASCII,
so it builds byte-mode ASCII expressions), and `regex-syntax` directly to
parse patterns at compile time. The complete dependency closure is pinned in
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

The omitted `perf-inline` feature only requests forced inlining inside the
matching engine. All original matching representations and admission paths
remain enabled: one-pass DFA, lazy DFA, bounded backtracker, PikeVM and literal
strategies. The byte `RegexBuilder`, capture policy, parser and NFA limits,
hybrid capacity, compiled-expression cache and allocator are unchanged. Allowing
dispatch functions to remain shared may reduce executable code duplication;
source inspection alone establishes no physical memory reduction.
