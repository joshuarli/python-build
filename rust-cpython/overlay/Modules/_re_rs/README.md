# Rust regular-expression cache

Supported ASCII searches retain up to 512 `regex::bytes::Regex` engines.
`RegexCache::expressions` owns each pattern string once. Each `CachedRegex`
stores a `u16` insertion rank, with exactly the dense ranks zero through
`len - 1`. A hit does not change insertion order. When full,
`RegexCache::insert_compiled` removes rank zero and decrements the remaining
ranks before inserting rank 511. No unbounded counter or separate FIFO
queue is retained.

Compilation still runs outside the original global mutex. After acquiring
that mutex, `portable_expression` checks the cache again and clones the
winning engine if another compiler published it first. Evicted engines stay
valid through existing held `Regex` clones. Engine features, syntax and flag
eligibility, CPython Pattern/Match ownership, module initialization, and
interpreter capabilities are unchanged.

Insertion preserves eviction-before-allocation order. It creates one owned
String and the same engine clone, using the original global allocator and
Rust allocation-failure behavior. It adds no fallible allocation API, Python
MemoryError fallback, dependency, or allocator hook. Scratch parsing and its
thread ownership, alignment, bounds, and lifetime rules are unchanged.

For five eligible kernel keys totalling 118 UTF-8 bytes, removing the queue
eliminates five duplicate String owners and their 118-byte payload, while
declaring ten bytes of rank metadata. With nominal 24-byte String handles,
the live key/rank model falls by 228 bytes before the removed queue header.
At 512 entries it removes 512 duplicate String owners plus their payloads,
while declaring 1024 rank bytes. Actual map bucket padding, unused capacity,
allocation rounding, compiled code, and resident memory remain unmeasured;
these declarations do not establish a physical saving.

`tests/fifo_rank.rs` checks FIFO against an independent queue oracle across
hits and churn, held-engine lifetime through eviction and reinsertion,
rejected/prepare-only patterns, and eight forced simultaneous compilers.
The compile barrier exists only under `cfg(test)`.
`tests/test_fifo_rank.py` checks public Pattern identity and weakrefs,
held Match ownership, eight-thread native call retention and public reentry,
captures, flags, errors, and genuine native-C fallback. Existing
`tests/test_flag_eligibility.py` retains own-GIL and route eligibility checks.
