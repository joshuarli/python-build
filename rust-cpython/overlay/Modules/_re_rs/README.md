# Regex compiled source ownership

The bridge returns match spans. It does not expose a Rust regex's original
source through `as_str`, `Debug`, or `Display`. The high-level
`regex::bytes::Regex` wrapper nevertheless retains that source in an `Arc<str>`.
`compile_expression` now constructs the same `regex_automata::meta::Regex`
without that diagnostic text owner.

The constructor reproduces the pinned byte builder configuration: a 10 MiB
NFA limit, 2 MiB hybrid-cache capacity, leftmost-first matching, byte-mode empty
matches, and syntax with Unicode and UTF-8 restrictions disabled. The default
All capture strategy, remaining defaults, and complete original engine-feature
closure remain enabled. This keeps reverse and one-pass engines, PikeVM,
backtracking, hybrid caches, and literal strategies. It does not repeat the
prior direct-PikeVM or optional-engine-removal experiments.

`RegexCache` retains its original two `String` keys, 512-entry FIFO order,
second lookup after compilation, and clone-per-search pools. Preparation,
portable syntax, flags, error fallback, CPython Pattern/Match ownership, and
module registration are unchanged. Cache hits do not refresh FIFO order;
held engine clones survive eviction. No parsing state or subject reference is
added to the cache. Module monkeypatching, own-GIL fallback and fork behavior
retain their existing boundaries.

`src/source_owner_tests.rs` compares the former byte builder with the new
constructor for compile errors, nesting and size limits, capture metadata,
kernel patterns and leftmost/empty/anchor/byte spans. It also checks FIFO hits,
eviction, reinsertion and a held engine after eviction.
`tests/test_source_owner.py` checks public cache identity, weakrefs, held
matches, native churn, supported routing, method reentry and fallback errors.
The existing flag-eligibility tests and complete CPython `test_re` remain
qualification requirements, including their interpreter and fork neighbors.

The five native kernel patterns contain only 118 source bytes in total, plus
five Arc allocation headers and allocator rounding. Removing those owners
does not establish a resident-page saving. This is a source-only candidate:
the new Rust and Python tests, compiler, and memory qualification have not run.
