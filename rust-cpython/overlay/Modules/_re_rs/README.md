# Shared immutable regex cache keys

`RegexCache` keeps each supported expression in a lookup map and records its
insertion order in a FIFO. Both containers now own an `Arc<str>` pointing to
one immutable pattern allocation. Content lookup, the 512-entry limit, hit
ordering, the second lookup after compilation, and oldest-first eviction stay
unchanged. A held `Regex` clone remains usable after its cache entry is evicted.
Atomic shared ownership preserves the existing mutex-protected cache's
cross-thread transfer requirements; no interpreter capability or fork contract
is added.

The measured regex kernel has six default-flag expressions, five admitted by
the native portable filter. The expression ending in `$` uses the existing C
fallback. The separate warnings kernel's 200 IGNORECASE patterns already exit
the Python eligibility guard before native loading, so key sharing cannot
reduce their native cache ownership. Python's two pattern caches reference the
same public C pattern object; its identity, weak references, and ownership by
held matches remain unchanged.

For the five admitted expressions, this removes five duplicate string buffers
and narrows each pair of key handles from two `String`s to two `Arc<str>`s.
Each shared allocation adds two atomic reference counters. These are small
logical storage differences, not a physical-page or RSS saving claim. The
parser scratch arena, expression representation, allocator, engine clones,
admission checks, module metadata, Cargo dependencies, and public wrapper are
unchanged.

`tests/shared_cache_keys.rs` specifies the actual private map/FIFO buffer
identity, unchanged FIFO behavior across hits and bounded eviction, reinsertion,
unsupported syntax, and held-engine survival. Its buffer-identity assertions
would fail against the two independent key buffers. The Python fixture
`tests/test_shared_cache_keys.py` covers public cached identity and weakrefs,
held Match ownership, native cache churn, captures, flags, and fallback errors.
Both fixtures were specified before the production edit. They have not been
compiled or run; clean build, native/private fixture qualification, complete
affected suites, and the coordinator's memory gate remain required.
