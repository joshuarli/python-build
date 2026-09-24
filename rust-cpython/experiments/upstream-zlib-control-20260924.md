# First upstream control check: public zlib decode

The matched vanilla upstream 3.16.0a0 build and the existing Rust-enabled
fork both use platform zlib 1.2.12. The measured workload was public
`zlib.decompress` over the same fixed compressible and incompressible streams,
16 iterations per process (33,554,432 decoded bytes). The relevant
`Modules/zlibmodule.c` and Python gzip/ZIP/import source files are identical
between these two source pins. This check tests the control setup and whole
interpreter effects; it does not test the zlib-rs candidate.

One local macOS standard-profile run used five paired timing processes and
three paired memory processes. The fork/platform-zlib side had a 0.974 paired
median wall ratio and 0.990 paired median kernel CPU-per-byte ratio against
upstream. The memory report computed +14.20% peak RSS from the ratio of side
medians and marked a diagnostic FAIL. The individual paired peak-RSS ratios
were 1.056, 0.978, and 1.257. A separate upstream-versus-itself run gave
paired ratios 1.001 wall, 1.003 CPU, and 1.001 peak RSS; its three RSS pairs
ranged from 0.853 to 1.071. The baseline RSS samples themselves shifted from
38–42 MB in the cross run to 44–45 MB in the self run. Host load was above
five in the cross run. These small local samples do not establish whether the
fork has a real memory regression, but the high candidate memory round needs
follow-up.

The raw cross and self observations are in
`data/upstream-vs-fork-zlib-raw-20260924.json` and
`data/upstream-self-zlib-raw-20260924.json`, with corresponding `*-provenance-*`
files. The cross-run provenance mistakenly lists locked core wheels even
though no wheel site was prepared; that bookkeeping bug was fixed before the
self run, whose provenance correctly lists no packages. The raw workload
measurements are unaffected. The cross run's generated baseline snapshot was
discarded so its false input claim cannot become an active reference; the
self-calibration snapshot was retained under `benchmarks/baselines/`. Both
runs used the macOS `wait4` root peak plus
sampled process-tree RSS. These counters are diagnostic lower bounds, with
no whole-tree unique memory or allocation data. The full ignored result
directories remain in the upstream worktree.

**Verdict: control works; upstream resource parity remains open.** Repeat the
cross and self comparisons serially on a quiet host with more memory pairs,
then inspect the source/build integration or retained memory if the RSS gap
persists. Do not use this one workload to claim a general fork improvement.
