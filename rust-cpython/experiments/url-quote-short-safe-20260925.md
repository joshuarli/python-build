# Short `safe=b'/'` quote route diagnostic, 2026-09-25

## Verdict

**Reject as a default guard change for now.** A source overlay that sends exact
`safe=b'/'`, 2–31-byte inputs through the existing Python route reduced the
complete `catalog_request_path` kernel CPU cost by 6.4% relative to the
current revised guard in two serial pairs. It retained the current guard's
search-form gain and was neutral on URL normalization in this bounded run.
The host's one-minute load ranged from 2.56 initially to 3.11 finally;
OrbStack Helper used about 18% and 12% CPU in those snapshots, with no
above-50% top process at pair boundaries. The comparison remains a narrow
source-overlay diagnostic. It also targets one
safe value and one size threshold drawn from the observed workload, so it is
an overfit rule until broader safe/length distributions and semantics are
examined. The current revised `0001` patch and manifest were not changed.

The proposed route still cost 3.0% more median CPU than the pure parser on
request path in its two direct pairs. The current revised guard had cost 8.3%
more in the earlier loaded-host diagnostic. These distinct runs must not be
subtracted as a precise causal estimate; this run's direct current/proposed
pairs are the cleaner attribution. Search-form proposed/pure median CPU ratio
was 0.971, a 2.9% improvement. Normalization proposed/pure was 1.039, but
proposed/current was 0.999, within same-side noise; the short-path condition
did not introduce a measurable normalization loss.

## Source and compiler identity

The same read-only CPython 3.16 stage executable was used for all arms:
SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`.
Its pure parser is `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`.
The exact current `0001-rust-url-quote.patch` is
`8117e87d51a91dd362d5c315f3eae552ac1144b83f43dae1980423c320b618ad`;
its parser hunk applied with zero fuzz and yielded
`f2949f2bfd61891f33a9e79168f1c188587b374985ebb3faa04a476202b280f2`.
The only proposed parser edit is the extra guard
`not (safe == b'/' and bs_len < 32)` after the existing public fast exit and
exact bytes type checks; this prevents bytes subclasses from invoking a new
comparison method;
that overlay hashes to
`5e4a28df5e7c8bf1f2f4571c98bf092296e9604db34e9e66f635a6ef5e74488e`.
The standalone experimental patch is
`url-quote-short-safe-20260925.patch`, SHA-256
`6e6e9d224849eeb8cb33b12bca627f1798fc43f9d432fc9a5726f343b4c2b7e7`.
The exact patch's C and Rust new-file hunks hash to
`727e5b12a8a2e0b8a81be59b86ccb5252f88b1f66c64ca1cbc05ec71448f44df`
and `bb9156522ea47140e52e309b501ee3222ed5466fb8b33a779a31566e184fad8c`.
The locally built shared extension is
`b1ab627f758d778087fb2c8e8e8df0835396e9b9c8d3db45550c7ca74710d617`,
the same bytes as the previous revised-guard diagnostic.

The runner and raw data record the exact compiler commands and all three
successful build attempts. The Rust archive used pinned nightly 2026-09-15,
`--edition=2024`, `no_std`, `-C opt-level=3`, `-C panic=abort`, and native
`aarch64-apple-darwin`. The C module used locked LLVM 23.1.2 Clang with
`-O3 -fPIC -mcpu=apple-m1 -mmacosx-version-min=26.0`, the Xcode 26.5 SDK,
and stage Python 3.16 headers. The same Clang linked a bundle with dynamic
Python symbol lookup. The `rustup` process may spawn `rustc`, so its direct
`wait4` CPU observation does not cover the compiler child; the command and
wall/RSS record remain in the raw data. A follow-up invoked the resolved
`/Users/josh/.rustup/toolchains/nightly-2026-09-15-aarch64-apple-darwin/bin/rustc`
directly with the identical compiler arguments and output path. Its `wait4`
measurement covers the compiler process: wall 0.072457 s, user CPU 0.043241 s,
system CPU 0.018665 s, peak RSS 101,531,648 bytes, zero swaps. The archive
SHA-256 was `4dd9aad19125f08be4454efd183e6a742e371378038bf14ca6f1ea0cbc89f051`
both before and after. No workload was rerun for this correction. There was
no full PGO build.

## Measurement

The runner is `url-quote-short-safe-20260925.py`; compact attempt records are
in `data/url-quote-short-safe-20260925.json`. Every arm copied the stage's
`urllib/*.py` into an isolated overlay, with no overlay bytecode cache. Each
fresh process used `-B`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=1`, and
`PYTHONPATH=SIDE:NATIVE:ROOT`; the pure parser did not import the extension.
The complete workload command was `stage/bin/python3.16 -B -m
benchmarks.workloads.catalog_url_breadth TASK --iterations N` for search and
path, or `benchmarks.workloads.catalog_url` for normalization. Search used 500
iterations, path 1,000, and normalization 2,000. All 36 workload calls had the
registered input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and their exact task output digests; all exited successfully. The JSON records
the digests, process identities, order, and each wall, user CPU, system CPU,
peak RSS, and swap observation.

`os.wait4` measured direct-child kernel user and system CPU and lifetime peak
RSS; monotonic external wall included startup and output. Workloads spawned
no children. Kernel `ru_nswap` was zero in every workload attempt. Peak RSS
was about 28–35 MB across the tasks, with pair differences below 1 MB and no
consistent direction. Physical or unique memory was not available from this
measurement. Host load, top CPU processes, swap, and memory pages were sampled
outside the timed child. The complete pairs alternated order; one same-side
pair for each arm/task estimated local noise.

| Task | Proposed/current CPU ratios | Proposed/current wall ratios | Proposed/pure CPU ratios | Same-side CPU ratios, current; proposed |
| --- | --- | --- | --- | --- |
| Search form | 0.987, 0.997 (median 0.992) | 0.981, 0.995 | 0.983, 0.959 | 0.984; 1.012 |
| Request path | 0.939, 0.934 (median 0.936) | 0.959, 0.934 | 1.037, 1.023 | 1.006; 1.004 |
| URL normalize | 0.999, 0.999 (median 0.999) | 1.000, 0.996 | 1.033, 1.046 | 0.991; 0.987 |

The request-path current/proposed CPU reduction exceeded same-side CPU noise
in both pairs. Wall differences were less stable than CPU. Search's
0.8% median CPU difference and normalization's 0.1% difference were within
local same-side variation. The proposed rule therefore did not lose either
important task beyond observed self-noise in this run.

Two setup attempts are retained in the data: the first source extractor did
not materialize the new C/Rust files and stopped before build; the second
completed a valid search workload but truncated its JSON output before digest
parsing, then stopped. An initial full run with the equality check before the
exact bytes type check was superseded after a static review. Its raw 36 calls
were overwritten by the corrected run; only its summary ratios survive in
the work session. Exactly **36 raw attempt records are missing**, so total
lane CPU is incomplete. The corrected final runner completed all checks and
now refuses to start when its evidence JSON already exists; a new run requires
archiving that file first. No tests, formatters, linters, hooks, dependencies,
commits, or remote operations were run or added.
