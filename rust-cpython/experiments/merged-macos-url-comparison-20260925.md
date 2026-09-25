# Matched merged macOS URL builds, 2026-09-25

**Keep the optional unquote route as a promising macOS speed candidate; public behavior and upstream memory acceptance remain open.** The merged builder produced a quote-only control with `build --variant quote-only` and an opt-in candidate with `build --url-unquote`. Both used the same pinned CPython 3.16 source, source patch manifest, LLVM 23.1.2, nightly Rust, ThinLTO, `-O3`, and nine-worker PGO. The independent PGO runs produced different profiles and interpreter bytes, so this matched-build comparison does not isolate the decoder as cleanly as the earlier same-executable proof.

Both fresh source trees had 6,035 non-generated files; only `Lib/urllib/parse.py`, `Modules/_rust_url_quote/module.c`, and `Modules/_rust_url_quote/quote.rs` differed. The installed parser files had valid checked-hash `.pyc` caches matched to their own source. Each side imported the private extension; only the candidate selected the guarded public `unquote` route. The builds and their exact hashes are in the [compact observations](data/merged-macos-url-comparison-20260925.json) and the [candidate build record](merged-macos-url-build-20260925.md).

The repository benchmark harness ran five alternating-order timing pairs without a memory sampler, then three separate alternating-order memory pairs per workload. `catalog_search_form` performed 500 complete 48-request batches per process, with output digest `a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22` in every run. A quote-only self-comparison preceded the candidate comparison on the same quiet host.

| Workload | Paired complete-process wall change | Paired kernel CPU change | Interpretation |
| --- | ---: | ---: | --- |
| Quote-only self-comparison, search form | −0.90% (−1.60% to +2.63%) | −1.02% (−1.53% to +2.67%) | Local noise bound |
| Opt-in unquote, search form | **−42.29%** (−43.32% to −41.25%) | **−42.84%** (−43.83% to −42.79%) | Clear targeted gain |
| Opt-in unquote, URL normalization | −2.27% (−4.05% to −0.88%) | −2.55% (−4.46% to −1.26%) | Directional; no workload-specific self-noise pass |
| Opt-in unquote, request paths | −0.35% (−1.26% to +3.75%) | +0.74% (−0.85% to +1.23%) | No established change |

Wall time is external spawn-to-exit duration. CPU is `wait4` user plus system time for the workload root; these particular tasks have no child processes. The harness also retains internal operation time per attempt in the compact data. Each normalization process completed 1,500 batches and each request-path process 1,000 batches; their output digests matched across sides.

In the search-form memory pass, candidate-minus-control paired peak RSS was −212,992, −442,368, and +196,608 bytes. Sampled physical footprint differences were −131,072, −360,448, and +294,912 bytes. Self-pair memory differences also changed sign. Neither this pass nor the neighboring workloads establish a persistent memory increase. macOS still lacks qualified USS/PSS and allocation measurement, and the benchmark report therefore marks memory acceptance incomplete. The URL patch's private parser-state differences and broad public semantics also remain unresolved; no separate CPython suite was run after the merge.

The two build commands and four benchmark controllers consumed **1,673.79 kernel user plus system CPU seconds** in total, with a maximum reported process RSS of **1,821,687,808 bytes** and zero reported swaps. These parent command totals include their children; per-workload CPU records are not added again. Cache provisioning, source inventories, identity inspection, and report preparation were short unmetered work. No production build, dependency, formatter, linter, hook, or remote was changed.
