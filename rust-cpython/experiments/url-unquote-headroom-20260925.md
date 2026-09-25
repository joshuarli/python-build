# Public URL unquote headroom on the guarded quote installation

## Decision

**Pursue a bounded decoder prototype for `catalog_search_form`; defer one for `catalog_url_normalize` alone.** On the accepted installed guarded quote interpreter, the search task spends 0.555 s of 1.510 s instrumented complete-task time (36.7%) cumulatively inside public `unquote`. Its 182 eligible escaped calls per 48-record batch account for all 182 `_generate_unquoted_parts` entries. The normalization task spends only 0.0117 s of 0.7359 s (1.59%) cumulatively inside public `unquote`, below its earlier 1.83% installed candidate self-noise allowance even under an impossible zero-cost replacement. Search's 36.7% is an optimistic diagnostic ceiling, far above its earlier 1.78% candidate self-noise allowance; a native call, guard, UTF-8 decode, and output allocation would retain cost. `cProfile` cannot predict a speedup or compare its seconds to uninstrumented wall/CPU seconds.

This is a target-selection result only. The proposed boundary remains exact ASCII `str`, default `utf-8`/`replace`, and at least one percent sign after the existing public fast exits. No decoder was built or timed. `catalog_request_path` invokes `unquote_to_bytes`, not public `unquote`, for its 96 byte decodes per batch and remains outside this boundary.

## Workload and installed identities

The diagnostic [probe](url-unquote-headroom-probe-20260925.py) called the unchanged registered task functions in `benchmarks.workloads.catalog_url` and `benchmarks.workloads.catalog_url_breadth`. Every iteration checked the complete framed output digest; each invocation also checked input digest `7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`. Normalization's output digest was `a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`; search form's was `a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22` in both profile and count passes. The counter wrapped only diagnostic calls and preserved those digests.

| Installed item | Absolute path or SHA-256 |
| --- | --- |
| Interpreter | `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16` |
| Interpreter SHA-256 | `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6` |
| Imported `urllib.parse` | `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/lib/python3.16/urllib/parse.py` |
| Parser SHA-256 | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` |
| Imported `_rust_url_quote` | `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so` |
| Extension SHA-256 | `5f00a07bbcc282659e1258d0509c1e117f9db185cf94f867aeb809736f616916` |

The profile used 500 complete normalization batches and 250 complete search batches. Each batch processes 48 records. The count pass used one complete batch per task and instrumented `urllib.parse.unquote` plus the already imported `urllib.request.unquote` alias. The latter matters: `Request` calls the alias once per search record to inspect the host. An initial search counter that wrapped only `urllib.parse.unquote` saw 480 calls while the profile showed 528. Its raw attempt is retained; the corrected count of 528 reconciles exactly with the profile. The normalization fixture imports `unquote` after the wrapper is installed, so all eight direct credential calls were counted.

## Actual input distribution per complete batch

| Task and path | Public calls | Exact ASCII/default | Eligible with `%` | No-percent fast exit |
| --- | ---: | ---: | ---: | ---: |
| Normalization credentials | 8 | 8 | 4 | 4 |
| Search `parse_qsl` fields | 480 | 480 | 182 | 298 |
| Search `Request` host alias | 48 | 48 | 0 | 48 |
| Search total | 528 | 528 | 182 | 346 |

Every observed call used exact `str` and exact default codec/error strings, and every input was ASCII. The 182 eligible search calls are 37.9% of the 480 parsed fields. The other 62.1% of parsed fields return at the no-percent check. The extra 48 host calls also return there. The quoted search form preserves malformed source `%` text by encoding it as `%25`, so zero observed eligible search inputs have invalid percent escapes; the four eligible direct credential inputs also have zero invalid escapes.

For normalization, eligible string lengths were `6:2, 11:2` and each had one `%`. For search, exact eligible length frequencies were `5:6, 6:2, 7:2, 8:24, 9:6, 10:2, 13:26, 15:4, 18:4, 19:2, 20:48, 23:2, 27:2, 33:2, 54:2, 55:2, 64:2, 67:4, 82:2, 84:2, 87:10, 89:14, 91:2, 96:2, 104:2, 832:2, 2729:2, 3072:2` (length:count). Thus 176 of 182 are at most 104 characters; six are 832–3,072 characters. Exact counts of `%` per eligible search input were `1:40, 2:30, 3:50, 4:4, 5:4, 6:2, 9:4, 11:2, 12:2, 13:4, 14:26, 15:2, 16:2, 18:2, 27:2, 135:2, 192:2, 1024:2`. Every percent sign began a valid hex pair in this pass. The long tail warrants its own allocation and memory check if a prototype proceeds.

## Profile attribution

| Task and parser row | Calls | Self s | Cumulative s | Cumulative share of complete profile |
| --- | ---: | ---: | ---: | ---: |
| Normalize: `unquote` | 4,000 | 0.00145 | 0.01172 | 1.59% |
| Normalize: `_generate_unquoted_parts` | 8,000 generator resumes | 0.00285 | 0.00847 | 1.15% |
| Normalize: `_unquote_impl` | 2,000 | 0.00283 | 0.00432 | 0.59% |
| Search: `unquote` | 132,000 | 0.03560 | 0.55494 | 36.74% |
| Search: `_generate_unquoted_parts` | 182,000 generator resumes | 0.06478 | 0.48031 | 31.80% |
| Search: `_unquote_impl` | 45,500 | 0.24116 | 0.39193 | 25.95% |
| Search: `unquote_plus` | 120,000 | 0.03684 | 0.60154 | 39.83% |
| Search: `parse_qsl` | 12,000 | 0.04458 | 0.69336 | 45.91% |

The complete normalization profile recorded 2,890,801 calls and 0.735875 s; its registered result reported 0.733684 s for the internal loop. The complete search profile recorded 6,570,103 calls and 1.510282 s; its internal loop reported 1.509965 s. All task digests matched. The `unquote` row includes its own frame, generator work, `_unquote_impl`, built-ins, and no-percent calls. The generator row includes `_unquote_impl`; `_unquote_impl` includes its byte operations. `unquote_plus` includes `unquote`, and `parse_qsl` includes `unquote_plus`. These cumulative times overlap and must not be added. Even the 36.74% search ceiling includes 346 fast exits that the proposed helper cannot remove, plus public checks and the required UTF-8/output work. Its 31.80% generator share is a narrower location clue, not a measured achievable gain.

## Reproduction and resources

Commands ran serially from `/private/tmp/python-build-exp-url-unquote-headroom-20260925a`. The environment was cleared, then set to this worktree's `PYTHONPATH`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=1`. No `DYLD_*` variables were inherited. Ordinary host activity remained, including OrbStack; no competing compiler or benchmark was visible at preflight. `/usr/bin/time -l` covers each direct, single-process command including import, profiling or wrapper bookkeeping, and JSON output. Raw JSON, stderr, and time records are under ignored `rust-cpython/work/url-unquote-headroom-20260925a/`.

The following exact commands produced the final four observations (the first two are the corrected alias-aware count passes):

```sh
/usr/bin/time -l -o rust-cpython/work/url-unquote-headroom-20260925a/count-normalize-alias.time env -i PYTHONPATH=/private/tmp/python-build-exp-url-unquote-headroom-20260925a PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1 /private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/url-unquote-headroom-probe-20260925.py count catalog_url_normalize > rust-cpython/work/url-unquote-headroom-20260925a/count-normalize-alias.json 2> rust-cpython/work/url-unquote-headroom-20260925a/count-normalize-alias.stderr
/usr/bin/time -l -o rust-cpython/work/url-unquote-headroom-20260925a/count-search-alias.time env -i PYTHONPATH=/private/tmp/python-build-exp-url-unquote-headroom-20260925a PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1 /private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/url-unquote-headroom-probe-20260925.py count catalog_search_form > rust-cpython/work/url-unquote-headroom-20260925a/count-search-alias.json 2> rust-cpython/work/url-unquote-headroom-20260925a/count-search-alias.stderr
/usr/bin/time -l -o rust-cpython/work/url-unquote-headroom-20260925a/profile-normalize.time env -i PYTHONPATH=/private/tmp/python-build-exp-url-unquote-headroom-20260925a PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1 /private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/url-unquote-headroom-probe-20260925.py profile catalog_url_normalize --iterations 500 > rust-cpython/work/url-unquote-headroom-20260925a/profile-normalize.json 2> rust-cpython/work/url-unquote-headroom-20260925a/profile-normalize.stderr
/usr/bin/time -l -o rust-cpython/work/url-unquote-headroom-20260925a/profile-search.time env -i PYTHONPATH=/private/tmp/python-build-exp-url-unquote-headroom-20260925a PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1 /private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16 rust-cpython/experiments/url-unquote-headroom-probe-20260925.py profile catalog_search_form --iterations 250 > rust-cpython/work/url-unquote-headroom-20260925a/profile-search.json 2> rust-cpython/work/url-unquote-headroom-20260925a/profile-search.stderr
```

The two earlier count attempts used the same command shape and wrote `count-normalize.{time,json,stderr}` and `count-search.{time,json,stderr}`; their probe revision had no `urllib.request.unquote` alias wrapper. Their user/system CPU was `0.05/0.02` s each. The corrected normalization and search counts were `0.05/0.02` s each. Profile normalization used `0.78/0.02` s and peak RSS 32,505,856 B; profile search used `1.55/0.02` s and peak RSS 31,588,352 B. The four count peak RSS values were 31,784,960, 31,834,112, 31,965,184, and 31,522,816 B in attempt order. All six commands reported zero swaps. Total ledger: **2.65 kernel CPU seconds** (`2.53` user + `0.12` system), highest process RSS **32,505,856 B**, within the 45 CPU-second and 512 MiB caps. Since these commands spawned no children, the per-process kernel report covers the diagnostic process tree. The raw JSON retains all profile function rows and exact observed distributions; this report retains the decision-relevant rows and distributions.
