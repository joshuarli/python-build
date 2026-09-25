# Guarded URL quote lazy-import experiment, 2026-09-24

## Decision

**Do not promote the lazy import overlay.** It preserved the checked public behavior, but the five-round fresh-process import run did not establish a wall-latency improvement above host noise. All three complete registered URL tasks remained close to their same-side timing variation. The separate request-path memory pass showed a small, consistent increase in root peak RSS. This is an inconclusive performance experiment, with the candidate retained only as [an optional diff](url-quote-lazy-import-20260924.patch); the active patch manifest and build sources were untouched.

The code changes when a missing required `_rust_url_quote` extension fails: eager import fails at `urllib.parse` import, whereas the lazy version fails at the first eligible exact-bytes quotation. That state transition is explicit and would need acceptance along with a demonstrated benefit.

## Candidate and correctness

Base commit `c05e74a20b1e29974121b278b117b261b401936c`, branch `exp/rust-cpython-url-lazy-import-20260924ab`, macOS 26.5.2 arm64. Two APFS clones of the fully patched installed stage at `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage` live in ignored `rust-cpython/work/url-quote-lazy-import-20260924/{eager,lazy}`. Only the lazy clone's `Lib/urllib/parse.py` source changed. Both use the identical installed interpreter SHA-256 `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6` and native extension SHA-256 `5f00a07bbcc282659e1258d0509c1e117f9db185cf94f867aeb809736f616916`.

The eager parser SHA-256 is `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee`; lazy is `324cbc13f19d3afe0708ede61e6061e17ba31ce967ad9764f5464e5be98649ec`. Each clone's own interpreter regenerated its checked-hash parser cache outside measurement. Both cache headers have CPython 3.16 magic `780e0d0a`, flags `3`, and source hashes matching their source (`fb86b91008046490` eager, `64b5dc772496878e` lazy). The full cache SHA-256 values and paths are in the raw record. Measured children used no bytecode writes, fixed hash seed 1, ordinary allocator, and no user site packages. Child code was byte-identical between import arms and checked the expected installed parser path and extension module state.

The lazy parser leaves the current fast exits and exact-bytes/length guard in place. The first eligible call imports `_rust_url_quote` and stores its module and `quote_bytes` callable in `urllib.parse` module globals, which are interpreter-local. Later calls use the stored callable; there is no Python fallback on an eligible call when the extension is unavailable. A fresh-process guard check confirmed that an all-safe value, bytearray, and length over 200,000 did not import the module, and that a blocked extension raised `ModuleNotFoundError` on the first eligible call.

The public differential harness matched eager behavior for **2,177** cases, including subclasses, invalid safe values, all byte values, and the 200,000-byte boundary. It also checked direct public native reach and the cached callable identity. The unchanged `test_urlparse` and `test_urllib` suites passed: **182 run, 7 skipped**. A subinterpreter started with the extension absent, quoted through the public API, and confirmed its own cached module/callable state before destruction. All complete workload children checked the registered full input and output digests.

## Paired observations

Timing used external monotonic wall time and kernel `wait4` user/system CPU for each fresh child, serially and without a sampler or profiler. The tasks launch no children. Import ran five counterbalanced rounds of 20 eager/lazy pairs, plus five rounds of 20 eager/eager and 20 lazy/lazy pairs. Each complete task ran five eager/lazy timing pairs and five self pairs per side, using the documented fixed counts: 1,500 normalization, 500 search-form, and 4,000 request-path batches per child. All timed work included startup and imports. The [raw JSON](data/url-quote-lazy-import-20260924.json) retains every observation and each kernel user/system value separately.

| Fresh-process task | Median eager/lazy paired wall ratio | Median paired root CPU ratio | Eager/lazy median child wall | Timing interpretation |
| --- | ---: | ---: | ---: | --- |
| `import urllib.parse` | 0.993 | 0.983 | 37.57 / 37.89 ms | No reliable wall improvement; self pairs ranged 0.457–1.609 eager and 0.436–1.273 lazy. Five eager/lazy round-median wall ratios were 1.000, 0.998, 0.970, 0.970, 1.036. |
| `catalog_url_normalize` | 1.003 | 1.004 | 569.42 / 564.87 ms | Within same-side variation (up to 2.62%). |
| `catalog_search_form` | 0.986 | 0.991 | 775.94 / 772.56 ms | Favorable direction, within lazy self variation of 2.98%. |
| `catalog_request_path` | 1.009 | 1.002 | 690.12 / 695.33 ms | Slight unfavorable wall direction, within eager self variation of 2.14%. |

The median-of-paired-ratios and median-child values summarize different statistics; their directions can differ when runs shift over time. The import CPU median direction is also below the observed CPU self spread and does not establish a startup improvement.

A separate external 10 ms memory pass ran ten eager/lazy import pairs and ten same-side pairs per side. Import lazy-minus-eager root lifetime peak RSS had median **−32,768 bytes** (range −425,984 to +147,456), within eager and lazy self-pair maximum absolute differences of 327,680 and 229,376 bytes. Sampled charged-dirty footprint had median −778,216 bytes but individual paired differences ranged about −4.06 to +3.05 MB, so it supplies no stable import-memory conclusion.

Each full task also had three eager/lazy memory pairs and three self pairs per side:

| Task | Lazy-minus-eager root peak RSS deltas | Median |
| --- | --- | ---: |
| Normalization | −180,224, −344,064, −180,224 B | −180,224 B |
| Search form | +245,760, −81,920, +65,536 B | +65,536 B |
| Request path | +131,072, +409,600, +294,912 B | +294,912 B |

Request path's two largest deltas exceed either side's maximum absolute three-pair self difference (278,528 B eager, 229,376 B lazy). The three-pair sample is too small for a firm regression magnitude, but the increase is visible and no task-level memory result was folded into an aggregate. macOS root RSS includes shared pages; sampled footprint is charged-dirty memory, not whole-tree USS/PSS. A compatible native/Python allocation comparison remains unavailable, so upstream resource parity is open.

## Resource record and next action

`/usr/bin/time -l` covered both clone commands, both cache-generation commands, correctness commands, and all four timing/memory controller commands. Across these 12 records, user plus system CPU totaled **137.67 seconds**; the largest per-command controller RSS was **61,128,704 bytes**, with zero swaps. The ignored `logs/` directory preserves their full output and resource logs, including no discarded measurement attempts. The raw JSON also retains the resource fields. Script authoring and summary generation were small untimed preparation steps; one summary-generation attempt failed before modifying the record and was corrected.

Keep the eager installed parser for now. A future lazy-import attempt needs a quieter startup comparison that shows a repeatable benefit and an expanded memory check for request path. No dependency, production file, active patch manifest, build source, benchmark harness, formatter, linter, hook, or remote was changed.
