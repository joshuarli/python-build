# Residual URL profile after quote and unquote, 2026-09-25

## Recommendation

**Defer another `urllib.parse` kernel.** The installed opt-in quote/unquote
candidate still has public URL work, but these complete-task profiles do not
locate a coarse, unaccelerated operation with convincing application headroom.
The largest remaining individual parser self-time row, `quote_from_bytes`, is
only 7.5% of instrumented search and 8.6% of instrumented normalization. It
includes type and `safe` checks plus already-safe returns; its eligible byte
scan already calls `_rust_url_quote.quote_bytes`. Deleting that entire row is
an impossible upper bound, not a predicted speedup. The other apparently
large URL rows mostly contain existing native calls or overlap one another.

The next *scouting* candidate is public `tomllib.load`/`loads` on a real
application metadata task. The [boundary audit](tomllib-boundary-20260925.md)
found a plausible whole-document exact-string/default-callback route, and the
ranked map places it ahead of URL. It also found no representative application
workload yet; the pinned metadata corpus is only 2,714 bytes. Find and profile
such a task before implementing a parser. This recommendation does not claim
that `tomllib` already has measured speed headroom.

## Boundary and identity

This diagnostic used the immutable fresh opt-in installation at
`/private/tmp/python-build-exp-url-unquote-build-20260925a/rust-cpython/stage`.
The interpreter SHA-256 was
`c529c0546766d9dd3757f0b38df3d4deb326d469678d604c64688ffdfce12187`.
The imported `urllib.parse` source was under that prefix with SHA-256
`ad11741ef88e9b7175ef0e1ffb311fdee865c073194743e08eb61adee828f4dd`;
its checked-hash `.pyc` had flags `3`, a valid source hash, and SHA-256
`a86b5075e71c2e73f65726b0a8bdb208bd508b3d0cbbce1f555900e4296eb24a`.
The imported private extension was under the same prefix with SHA-256
`dec52fdb6257198c112b0bf475ce5a414b055ad8daa7ea97f8e053c2a5ac5e71`.
It exposed `quote_bytes` and `unquote_ascii`. The first identity probe wrongly
asserted an exported `quote_ascii` name and exited after import; the corrected
probe verified actual source, cache, extension, and unquote identity. The
installation was read only, with `PYTHONDONTWRITEBYTECODE=1` in all attempts.

The existing `url-unquote-headroom-probe-20260925.py` profiled complete
registered tasks. Its SHA-256 was
`2f942e59c26db5f38d58ea4571b648bbffd3713c7b6925f26719d91d5898fa08`.
The registered workload sources `catalog_url.py`, `catalog_url_breadth.py`, and
the application `normalize.py` were SHA-256
`52c62e5fbdd1f322735ade604fd1d24330acb0eb7e0e35e2fe1dfc5bfa6f7995`,
`0c95c1b908db69e04d0e86149d57003c976659040a4bc8ffe2fd55a3f669378c`,
and `77e21cd6d5153654d69aa75f1bcb9abad17a03da3da5a49264d6a0de5067457a`.

Each of 250 `catalog_search_form` batches built 48 requests, parsed 48
queries, checked 240 pairs and 480 fields, framed every result into SHA-256,
and checked its registered digest. Each of 500 `catalog_url_normalize`
batches normalized 48 URLs, built 48 stable keys, hashed every output, and
checked its digest. Both returned registered input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`.
The search output was
`a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22`;
normalization output was
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.

## Complete-task profile attribution

`cProfile` recorded 4,198,135 calls and 0.973835 s for search, and
2,861,833 calls and 0.718184 s for normalization. These are instrumented
times only. The earlier uninstrumented installed comparison reported about
0.88 ms/search batch and 0.37 ms/normalization batch; this diagnostic cost
about 3.90 and 1.44 ms/batch. Its shares cannot be applied to that latency or
used as a speed result. In the table, self times are disjoint; cumulative
times nest and overlap.

| Task / row | Calls | Self s | Cum s | Share of complete profile |
| --- | ---: | ---: | ---: | ---: |
| Search `urlencode` | 12,000 | 0.053427 | 0.306856 | 31.5% cumulative |
| Search `quote_plus` | 96,000 | 0.037534 | 0.230697 | 23.7% cumulative |
| Search `quote_from_bytes` | 95,500 | 0.072964 | 0.125122 | 7.5% self |
| Search native `quote_bytes` | 45,500 | 0.009042 | 0.009042 | 0.9% self |
| Search `parse_qsl` | 12,000 | 0.042541 | 0.191581 | 19.7% cumulative |
| Search nested `parse_qsl._unquote` | 120,000 | 0.023828 | 0.128187 | 13.2% cumulative |
| Search public `unquote` | 132,000 | 0.037810 | 0.059239 | 6.1% cumulative |
| Search native `unquote_ascii` | 45,500 | 0.011339 | 0.011339 | 1.2% self |
| Normalize `quote_from_bytes` | 75,000 | 0.061986 | 0.104208 | 8.6% self |
| Normalize native `quote_bytes` | 48,000 | 0.007857 | 0.007857 | 1.1% self |
| Normalize `_hostinfo` | 52,000 | 0.026270 | 0.043148 | 3.7% self |
| Normalize `urlunsplit` | 24,000 | 0.017901 | 0.053645 | 2.5% self |
| Normalize public `unquote` | 4,000 | 0.001581 | 0.002246 | 0.3% cumulative |
| Normalize native `unquote_ascii` | 2,000 | 0.000296 | 0.000296 | 0.04% self |

Across disjoint Python self-time categories, search spent 0.422047 s (43.3%)
in `urllib.parse`, 0.039434 s (4.0%) in `urllib.request`, and 0.199799 s
(20.5%) in catalog application/workload code. The remaining 0.312556 s was
built-ins/C plus other Python. Normalization spent 0.206420 s (28.7%) in
`urllib.parse`, 0.177953 s (24.8%) in the application/workload, 0.096007 s
(13.4%) in other Python including `PurePosixPath`, and 0.237805 s (33.1%)
in built-ins/C. Neither task entered `json` or `_json`; their framing and
SHA-256 costs are application validation work. Built-in/C rows mix native URL
helpers, hashlib, string operations, and object checks; they are not an
unaccelerated URL bucket.

Search's public `unquote` is already guarded and calls native decoding for
182 fields per batch; most other calls return at the no-percent check. Its
remaining cumulative 6.1% includes public checks and fast exits. The
`quote_from_bytes` count is 382 per search batch, with only 182 native helper
calls; the rest include already-safe and other exits. Normalization makes
only four native unquote calls per batch. The normalization profile had only
36 `urlsplit` calls over 24,000 URL records because repeat inputs hit its
existing cache; it is not a meaningful parser hotspot here.

`urlencode` has the largest URL cumulative share, but it contains the public
`quote_plus`/`quote`/`quote_from_bytes` chain and its existing native scan.
Its exclusive 5.5% includes `doseq` traversal and public `quote_via` dispatch.
`parse_qsl`'s 19.7% cumulative includes `_unquote`, `unquote_plus`, and native
decoding; its exclusive field-loop work is 4.4%. A new whole-query kernel
would have to preserve field limits, strict/blank behavior, bytes and string
paths, codec/error options, output allocation, and observable replaceable
parser globals. The existing unquote patch also bypasses `_hextobyte` lazy
state and private hooks, a semantic gate still unresolved. This profile does
not justify expanding that contract surface for a smaller residual gain.

The stop criterion for this URL pass is the absence of a coarse remaining
public operation with both substantial **exclusive** complete-task headroom
and a narrow behavior boundary. Reopen URL only if a new representative
complete workload puts a specific unaccelerated operation materially above
these single-digit self-time ceilings, then require an unchanged-output,
serial paired uninstrumented wall/CPU improvement beyond same-side noise and
no material memory regression. Complete the outstanding unquote semantic and
memory gates before treating the existing opt-in route as accepted.

## Resource ledger and reproduction

All four substantive commands ran serially from
`/private/tmp/python-build-exp-url-residual-profile-20260925a` at base
`6fe484d`, branch `exp/url-residual-profile-20260925a`. There was no visible
compiler or benchmark process at preflight. Every command used `/usr/bin/time
-l`; every attempt has a unique `.time`, `.json`, and `.stderr` under ignored
`rust-cpython/work/url-residual-profile-20260925a/`. The two identity commands
used the staged interpreter with `env -i`, this worktree's `PYTHONPATH`,
`PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=1`. The first exited 1 only
because it asserted the nonexistent `quote_ascii` export; the second printed
the corrected identity. The profile commands were:

```sh
/usr/bin/time -l -o rust-cpython/work/url-residual-profile-20260925a/search-profile-1.time env -i PYTHONPATH=/private/tmp/python-build-exp-url-residual-profile-20260925a PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1 /private/tmp/python-build-exp-url-unquote-build-20260925a/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/url-unquote-headroom-probe-20260925.py profile catalog_search_form --iterations 250 > rust-cpython/work/url-residual-profile-20260925a/search-profile-1.json 2> rust-cpython/work/url-residual-profile-20260925a/search-profile-1.stderr
/usr/bin/time -l -o rust-cpython/work/url-residual-profile-20260925a/normalize-profile-1.time env -i PYTHONPATH=/private/tmp/python-build-exp-url-residual-profile-20260925a PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1 /private/tmp/python-build-exp-url-unquote-build-20260925a/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/url-unquote-headroom-probe-20260925.py profile catalog_url_normalize --iterations 500 > rust-cpython/work/url-residual-profile-20260925a/normalize-profile-1.json 2> rust-cpython/work/url-residual-profile-20260925a/normalize-profile-1.stderr
```

| Attempt | Exit | User s | System s | CPU s | Peak RSS bytes | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `identity-1` | 1 | 0.03 | 0.01 | 0.04 | 26,099,712 | 0 |
| `identity-2` | 0 | 0.02 | 0.01 | 0.03 | 22,921,216 | 0 |
| `search-profile-1` | 0 | 1.02 | 0.02 | 1.04 | 31,653,888 | 0 |
| `normalize-profile-1` | 0 | 0.76 | 0.02 | 0.78 | 32,112,640 | 0 |
| **Total / maximum** |  | **1.83** | **0.06** | **1.89** | **32,112,640** | **0** |

`/usr/bin/time -l` covers the complete direct Python process, including
startup and profiling output. These tasks spawn no children, so the
kernel-accounted CPU records cover the command process tree. Peak RSS is a
lifetime process peak, not unique or retained memory. All attempts are below
the 30 CPU-second and 512 MiB per-process caps. No implementation patch,
test suite, formatter, linter, hook, or push was run.
