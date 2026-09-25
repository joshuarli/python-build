# Installed URL unquote speed against upstream, 2026-09-25

## Result

The optional URL unquote installation completed the registered `catalog_search_form` workload in **49.6% less median external wall time** and **50.8% less kernel CPU** than vanilla upstream CPython 3.16.0a0. Five serial, counterbalanced upstream/unquote pairs all had the same direction. The corresponding quote-only fork was 15.9% faster by wall and 15.9% by CPU than upstream; unquote was 41.7% faster by wall and 43.0% by CPU than that quote-only fork. Every measured child checked the complete registered input and output digests. The largest same-side wall variation was 4.35%, on the quote-only side, well below the paired differences.

This qualifies speed for this complete catalog task. The upstream and fork have different source ancestry and independent PGO profiles, so the upstream differences cannot all be assigned to the decoder. The earlier [same-executable decoder proof](url-unquote-proof-20260925.md) isolates the parser and extension change more closely. The separate [three-way memory pass](url-unquote-upstream-memory-20260925.md) found no material peak-RSS regression on this task but left the full upstream memory and allocation gate open.

## Stages, cache, and workload

The immutable source stages were cloned with APFS copy-on-write into ignored `rust-cpython/work/url-unquote-upstream-speed-20260925a/{upstream,quote,unquote}`. The stage paths were `/private/tmp/python-build-exp-upstream-20260924/rust-cpython/work/upstream-control/stage`, `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage`, and `/private/tmp/python-build-exp-url-unquote-build-20260925a/rust-cpython/stage`. The cloned launchers, libpython libraries, parsers, and extensions where present were SHA-256 checked against their source stages. Full identities and sizes are in the [compact data](data/url-unquote-upstream-speed-20260925.json).

| Installed identity | Upstream | Quote-only fork | Optional unquote fork |
| --- | --- | --- | --- |
| `urllib/parse.py` SHA-256 | `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` | `ad11741ef88e9b7175ef0e1ffb311fdee865c073194743e08eb61adee828f4dd` |
| Checked-hash cache source hash | `fcbbd960190070b8` | `fb86b91008046490` | `0cbdbaed6fde156b` |
| `_rust_url_quote` | absent | 51,288 bytes; no `unquote_ascii` | 51,720 bytes; has `unquote_ascii` |

Each clone's own interpreter compiled `urllib/parse.py` to a checked-hash cache before timing. All three cache headers had flags `3` and a matching source hash. Separate verbose import logs confirmed that the parser cache matched and loaded on every side; only the forks imported their own `_rust_url_quote` extension. Every measured child rechecked prefix, actual parser/cache import paths, extension path and helper presence, parser and cache hashes, cache header, and task digests. The measured environment suppressed bytecode writes, kept ordinary per-process hash randomization and GC, and used the default allocator.

Each child ran **500 complete `catalog_search_form` batches**. A batch processes 48 records, 480 parsed fields, and 240 pairs. Every one of the 60 planned attempts returned input digest `7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f` and output digest `a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22`. The workload creates no child processes. No sampler, profiler, forced GC, or alternate allocator ran in the timed pass.

## Serial timing

Ten same-side attempts per installation formed five self pairs. Five further alternating-order pairs compared each of upstream/quote, upstream/unquote, and quote/unquote. Wall time is an external monotonic interval around each whole process; `wait4` supplies kernel user and system CPU plus lifetime root peak RSS and swaps. The workload's internal loop time is retained only as supporting detail. Because the workload is a single process, the root CPU covers the workload process tree; the outer `/usr/bin/time -l` controller includes orchestration and all waited children.

| Comparison | First-side median wall / CPU per 500 batches | Second-side median wall / CPU | Paired second/first wall ratios | Paired second/first CPU ratios |
| --- | ---: | ---: | --- | --- |
| Upstream → quote | 0.920 / 0.904 s | 0.785 / 0.768 s | 0.839, 0.862, 0.835, 0.855, 0.841 | 0.841, 0.861, 0.836, 0.854, 0.832 |
| Upstream → unquote | 0.912 / 0.889 s | 0.457 / 0.438 s | 0.504, 0.493, 0.512, 0.509, 0.498 | 0.497, 0.489, 0.500, 0.492, 0.491 |
| Quote → unquote | 0.784 / 0.765 s | 0.451 / 0.436 s | 0.583, 0.583, 0.558, 0.575, 0.597 | 0.577, 0.570, 0.553, 0.569, 0.582 |

Median paired wall/CPU ratios were **0.8411/0.8406** for upstream → quote, **0.5039/0.4920** for upstream → unquote, and **0.5832/0.5701** for quote → unquote. In the upstream/unquote paired samples, external wall was 1.824 ms versus 0.914 ms per 48-record batch; kernel CPU was 1.778 ms versus 0.877 ms per batch. Five self-pair maximum absolute wall deviations from 1.0 were 1.99% upstream, 4.35% quote, and 3.27% unquote; corresponding CPU deviations were 2.37%, 3.48%, and 2.44%. The raw ratios, order, individual CPU fields, full digests, and unique attempt tags are retained in the compact data and ignored raw logs.

## Attribution and resources

The upstream source is vanilla CPython 3.16.0a0 at merge base `0983642c966d9c536416101e99b7d2b085483847`. The quote-only and unquote installations are from the later Rust-for-CPython fork. The builds share LLVM 23.1.2, ThinLTO, and the nine-worker PGO task, but the fork has other intervening changes and all three native builds have separately generated PGO profiles. This three-way result is an installed-artifact speed comparison. The quote/unquote comparison narrows ancestry but still compares distinct native builds; the prior same-executable proof is the stronger decoder attribution.

The successful 60-child controller used **40.59 user + 1.59 system = 42.18 kernel CPU seconds**. Its children accounted for 42.05 seconds within that controller total. The separately timed cache and import audit used **2.25 + 0.20 = 2.45 seconds**. One initial controller attempt failed after its first child because the local wrapper referenced unsupported `rusage` child-CPU fields; its unique stdout, stderr, and resource logs were retained and its outer command used **0.91 + 0.03 = 0.94 seconds**. The three outer records therefore total **43.75 user + 1.82 system = 45.57 kernel CPU seconds**, below the 120-second cap. Clone preparation and report reduction were untimed and are outside that recorded total.

The largest measured child lifetime peak RSS was **33,849,344 bytes**; the largest recorded outer-process peak was **42,090,496 bytes** during audit, below the 1 GiB per-process cap. Every child and outer command reported zero swaps; host swap allocation was 243.88 MiB before and after. Peak RSS here is a resource guard, not a memory-parity or retention result. The raw files under the lane's ignored work directory include unique records for all 60 valid children and the failed controller attempt. No compiler, test suite, formatter, linter, hook, or push ran in this lane.
