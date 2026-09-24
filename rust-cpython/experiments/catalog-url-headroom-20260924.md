# Catalog URL quotation headroom

## Decision

**Proceed to a reversible, guarded `quote_from_bytes` helper trial.** In the
registered complete `catalog_url_normalize` batch, quotation is a meaningful
diagnostic target: `quote_from_bytes` consumed 18.5% of the profiled command's
function time cumulatively. All 150 calls per 48-record batch have exact
`bytes` input and exact `bytes` `safe` after normalization, but 54 calls take
the existing already-safe exit. The proposed helper after that exit would
receive **96/150 calls (64%) per batch**. This is reachability and profile
evidence, not a speed result. The prior control self-comparison had 6.62%
timing noise on a busy host, so the value of a native crossing remains open.

The exact next step is to create an isolated candidate patch that preserves
`quote_from_bytes` validation, `safe` normalization, empty and already-safe
exits in Python, and calls one helper only for exact `bytes` input plus exact
normalized `bytes` `safe` after those exits. Keep the original mapping path
as fallback. First exercise unchanged `test_urlparse` and `test_urllib` plus
differential byte/`safe` edge cases against the no-Rust control; measure the
complete catalog batch only after a quieter self-comparison establishes a
useful noise bound. Revert the helper if full-task wall and kernel CPU gains
do not clear that bound or resource checks regress. No helper was built here.

## Complete-batch diagnostic

I used the read-only no-Rust fork at
`/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`, SHA-256
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`,
from this worktree's base `57a7a54bbae82c388368b5d0d96bf3693d72719e`.
The reproducible diagnostic is
[`catalog-url-headroom-probe-20260924.py`](catalog-url-headroom-probe-20260924.py).
Each pass called the registered function with 100 complete batches: 4,800
`normalize_url`, 4,800 `stable_key`, and all 48 URL/key outputs length-framed,
SHA-256 hashed, and checked on every batch. Both passes returned input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.

Run from the worktree root with `PYTHONPATH=.`:

```sh
/usr/bin/time -l env PYTHONPATH=. /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/catalog-url-headroom-probe-20260924.py profile
/usr/bin/time -l env PYTHONPATH=. /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/catalog-url-headroom-probe-20260924.py count
```

`cProfile` recorded 581,376 calls and 0.16536 s total function time.
The registered workload returned 0.16125 s for its internal loop, which
includes output hashing and checks, but excludes one-time batch construction,
fixture loading, and input checking. Profile totals below overlap when a
caller includes a callee. Self time is exclusive to the named function's
Python frame; built-in calls and nested Python calls contribute to cumulative
time.

| Function | Calls | Self s | Cumulative s | Cumulative share of profile |
| --- | ---: | ---: | ---: | ---: |
| `quote_from_bytes` | 15,000 | 0.01377 | 0.03063 | 18.5% |
| `quote` | 15,200 | 0.00680 | 0.04062 | 24.6% |
| `normalize_url` | 4,800 | 0.01191 | 0.07503 | 45.4% |
| `stable_key` | 4,800 | 0.00155 | 0.06905 | 41.8% |
| `_digest` | 101 | 0.00691 | 0.01403 | 8.5% |

`quote_from_bytes` self time is 8.3% of profile time. Its cumulative figure
also includes work such as `str.join`, dictionary lookup, and `_Quoter`
cache misses. It is an optimistic ceiling for replacing the whole function,
not the expected benefit of the guarded scan. `_digest` includes one input
digest outside the steady loop and 100 complete output digests inside it;
its 8.5% cumulative share shows the check and hashing overhead. The
instrumented 0.16125 s internal loop is much slower than the earlier
uninstrumented 0.0429–0.0447 s control runs; none of these profile seconds
is a wall-time performance estimate.

The separate counting wrapper passed through to the original function and
preserved the complete digest. It observed 15,000 `quote_from_bytes` calls:
15,000 exact `bytes` inputs, 15,000 exact normalized `bytes` safe values,
zero empty inputs, 5,400 already-safe fast exits, and 9,600 calls reaching
the mapping scan. Of those scan calls, 9,200 have input length at most 17
bytes, 200 have length 448, and 200 have length 1,024. Thus 95.8% of scan
calls are very short, making native call overhead a real concern. No input
approaches the 200,000-byte chunk threshold. The wrapper's elapsed value
is diagnostic only.

The profile command's `/usr/bin/time -l` ledger was 0.19 user + 0.03 system
CPU seconds, 26,034,176 bytes maximum RSS, zero swaps; the counting command
was 0.08 user + 0.01 system CPU seconds, 25,165,824 bytes maximum RSS, zero
swaps. These kernel process totals cover interpreter startup, imports, and
profiling/counting; there were no workload children. Together they used
0.31 CPU seconds, below the 30 CPU-second and 512 MB RSS lane budgets.

## Semantic boundary

The pinned installed `Lib/urllib/parse.py` validates `bytes`/`bytearray`,
returns `''` for empty input, strips non-ASCII characters from `safe`, and
returns the ASCII input directly when all bytes are unreserved or safe.
Otherwise `_byte_quoter_factory(safe)` supplies cached `_Quoter.__getitem__`
for the byte map; at 200,000 bytes it switches to square-root-sized chunks
to bound temporary memory. `quote(str)` encodes first (UTF-8/strict by
default); the catalog's `safe=''` calls therefore reach `quote_from_bytes`
with exact bytes. The `_ALWAYS_SAFE` set includes ASCII letters, digits,
`_.-~`; other bytes receive uppercase `%HH` unless in `safe`. A helper must
preserve those rules and leave subclass, iterable `safe`, `bytearray`, and
long-input behavior on the existing path until tested independently.

The earlier single-record profile in `next-target-after-zlib-20260924.md`
located quote calls but did not measure the mixed registered batch. The
existing `catalog-url-baseline-20260924.md` records the busy-host 6.62%
self-noise and incomplete unique-memory/allocation coverage. This diagnostic
passes the target-selection gate only; it cannot qualify an implementation.
