# Installed URL quotation candidate comparison

## Result

The patched, fully installed CPython 3.16 Rust-for-CPython candidate completed the public `catalog_url_normalize` task faster than the last accepted Rust fork installation in five serial, counterbalanced timing pairs. Median candidate/control external wall ratio was **0.82255** (17.7% less wall time); median root kernel user-plus-system CPU ratio was **0.82061** (17.9% less CPU). Control and candidate timing self-calibrations had 2.13% and 1.83% noise allowances, within the 3% gate. The complete input and output digests, operation count, and installed import paths were verified in every workload child.

The separate three-pair memory pass found candidate-minus-control root lifetime peak RSS differences of **−65,536, +294,912, and +442,368 bytes**. The +294,912-byte paired median is within both separate self-comparison allowances (control 510,109 bytes, candidate 327,927 bytes). The paired sampled-footprint median was +180,200 bytes. These are small, mixed memory observations, not a claim of upstream memory parity: unique/proportional memory, PSS, and a compatible allocation pass are unavailable in this macOS lane. The workload marks no steady boundary, so retained memory is unavailable.

This is an installed-build comparison, with different executable hashes. The candidate was rebuilt with PGO after the source patch, so build-profile variation can also affect this comparison. The earlier cache-matched, same-executable [fair overlay comparison](url-quote-fair-comparison-20260924.md) found a similar speed direction. Together they support keeping the URL patch for further qualification; they do not isolate the installed speed difference to the patch alone or establish a product/upstream resource verdict.

## Installed inputs and cache policy

The accepted control `/Users/josh/d/python-build/rust-cpython/stage` and patched candidate `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage` were APFS-cloned into this branch's ignored `rust-cpython/work/url-quote-installed-comparison-20260924/{control,candidate}`. Neither source stage nor a shared cache was changed. The control was the last accepted Rust fork build, including its existing `_base64` integration. The candidate is the successful [full patched build](url-quote-full-build-retry-20260924.md), built from the same pinned Rust fork source with the guarded URL quotation patch.

| Installed file | Control SHA-256 | Candidate SHA-256 |
| --- | --- | --- |
| `bin/python3.16` | `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd` | `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6` |
| `lib/python3.16/urllib/parse.py` | `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` |
| `_rust_url_quote.cpython-316-darwin.so` | Absent | `5f00a07bbcc282659e1258d0509c1e117f9db185cf94f867aeb809736f616916` (installed bytes in raw data) |
| `parse.cpython-316.pyc` | `bdd5f87f452031209a465c90bb39a2ee30e9549ce7894b2c97c7b4793ff9d600` | `5354fc1b112a2688bd2f8b796b3a0c37680437fe33b332846fe3644efe140c79` |

Each clone's own interpreter regenerated its parser cache **outside** measurement. Both caches had CPython 3.16 magic, checked-hash flags `3`, and header hashes matching `importlib.util.source_hash()` of their own parser (`fcbbd960190070b8` control; `fb86b91008046490` candidate). Measured children used `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=1`, default allocator, and the same repository `PYTHONPATH`. Each child asserted its own `sys.prefix`, `urllib.parse.__file__`, and candidate extension path. Each returned 1,500 full batches of 48 URL normalizations and 48 stable keys, with input SHA-256 `7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f` and complete output SHA-256 `a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.

## Timing and memory evidence

The existing benchmark process observer ran each child serially. Timing used no sampler or profiler; external monotonic wall time and `wait4` user/system CPU included startup and imports. The task launched no children: the memory observer saw one process with zero sampling errors in every memory run. The five timing pairs alternated control/candidate order.

| Metric, per 1,500-batch child unless noted | Control median | Candidate median | Paired result |
| --- | ---: | ---: | ---: |
| External wall | 0.69660 s | 0.57097 s | ratio 0.82255 |
| Root user CPU | 0.67085 s | 0.54283 s | ratio 0.81574 |
| Root system CPU | 0.01591 s | 0.01559 s | ratio 0.96819 |
| Root total CPU per batch | 0.45729 ms | 0.37178 ms | ratio 0.82061 |
| Root lifetime peak RSS, separate memory pass | 26,525,696 B | 26,771,456 B | +294,912 B paired median |
| Sampled peak physical footprint, separate pass | 13,615,584 B | 13,763,016 B | +180,200 B paired median |

The five external wall ratios were `0.80671, 0.82255, 0.83079, 0.80447, 0.82897`; total CPU ratios were `0.80148, 0.82061, 0.82061, 0.79992, 0.82221`. The first control self-calibration was discarded for timing because its noise allowance was 7.29% amid fluctuating desktop and indexing activity. A bounded retry produced 2.13%, though an unrelated `rustc` appeared immediately afterward, so overlap near its end cannot be excluded. No compiler or competing benchmark was observed at the preflights preceding the candidate calibration, timing, and separate memory passes; one-minute load was about 2.4–3.7 then. The candidate self-calibration gave 1.83% timing noise. OrbStack and ordinary desktop processes remained active.

The memory observer used a 10 ms external sampler. Root RSS is the kernel lifetime peak, while footprint is a sampled Apple charged-dirty-memory ledger that may miss brief peaks. Footprint is neither USS nor PSS. The compact [raw observations](data/url-quote-installed-comparison-20260924.json) retain every timing and memory row, path/digest validation, self-calibration, process counts, and command resources. Full controller results and logs are in the ignored clone work area.

`/usr/bin/time -l` covered all seven controller commands, including the discarded control calibration: **51.26 total user-plus-system CPU seconds**. Largest per-command maximum RSS was **30,949,376 bytes**; each command reported zero swaps. The observed totals are below the approximately 200 CPU-second and 1 GiB per-command RSS budgets. The controller's maximum RSS is a per-process peak, not simultaneous tree memory. No formatter, linter, or hook ran.
