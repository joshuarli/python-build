# URL quote safe and length crossover, 2026-09-25

## Verdict

**Inconclusive for integration.** The candidate sends 2–31-byte exact bytes
inputs with any nonempty exact bytes `safe` to the cached Python quoter. The
current guard retains the Rust route for those inputs. This general rule
improved the complete request-path workload in two direct pairs, while the
search-form and normalization workloads showed no loss beyond local same-side
variation. The host was busy throughout: OrbStack Helper ranged from roughly
one to two CPUs during the breadth run. The candidate still cost about 2% more
CPU than the pure parser on the request-path task, so the data do not justify
integrating another guard condition yet. The production patch was untouched.

## Hypothesis and source identity

The cached Python quoter can amortize its safe-set setup for short inputs with
a nonempty safe set. The Rust kernel normalizes the safe set on each call; its
two passes and Python-to-C transition dominate small inputs. Empty safe sets
remain on the current Rust route. The candidate condition is placed after the
existing fast exit and exact bytes type checks, so a bytes subclass cannot
introduce a new truth-value method call. The source-only overlay patch is
`url-quote-crossover-20260925.patch` (SHA-256
`20714dd6c54391b367f52120b16a5393efad81425114bdf6407d75f7defabe3e`).
The unchanged current patch is SHA-256
`8117e87d51a91dd362d5c315f3eae552ac1144b83f43dae1980423c320b618ad`.

All arms used the same read-only stage CPython 3.16 executable (SHA-256
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`).
The pure, current, and proposed parser overlays have SHA-256 digests
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`,
`f2949f2bfd61891f33a9e79168f1c188587b374985ebb3faa04a476202b280f2`,
and `0264651c499fc0fab167dde63a953e84facd55a4813bda044987555df5ac1835`.
The locally built extension was identical across the three preparation runs,
SHA-256 `b1ab627f758d778087fb2c8e8e8df0835396e9b9c8d3db45550c7ca74710d617`.
The runner records each compiler command and its wall, direct-child CPU, peak
RSS, and swaps. The Rust compiler command uses `rustup run`; its launcher may
spawn `rustc`, so the direct-child CPU value does not include that compiler
child. No full PGO build was performed.

## Calibration and breadth

The calibration calls `quote_from_bytes` 30,000 times per case with a repeating
mixed ASCII, punctuation, space, percent, and non-ASCII byte pattern. It covers
input lengths 8, 24, and 64 with safe values `b''`, `b'/'`, `b'+'`, and
`b'/:?'`. All 12 three-arm cases returned identical output strings and SHA-256
digests. At 8 bytes, candidate/current CPU ratios for the three nonempty safe
sets were 0.802, 0.749, and 0.796; at 24 bytes they were 0.884, 0.916, and
0.882. At 64 bytes, where the candidate keeps the current route, the ratios
were 0.982, 1.016, and 1.019. Empty-safe ratios were 1.005, 1.003, and 0.972
at 8, 24, and 64 bytes. Each case has one three-arm observation, so these
numbers locate a plausible crossover rather than a precise threshold.

The breadth runner invoked complete registered workloads with 500 search-form,
1,000 request-path, and 2,000 normalization iterations. Each task had two
alternating current/proposed pairs, two pure/proposed pairs, and one same-side
pair for each current and proposed arm. The input digest was
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`;
all 36 workload attempts matched the task's registered complete output digest
and exited successfully. The source overlays were copied without bytecode
caches and run with `-B`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=1`.

| Complete task | Proposed/current CPU ratios | Proposed/pure CPU ratios | Current self CPU ratio | Proposed self CPU ratio |
| --- | --- | --- | --- | --- |
| Search form | 0.977, 0.981 | 0.942, 0.940 | 1.003 | 1.016 |
| Request path | 0.936, 0.943 | 1.020, 1.020 | 1.010 | 1.008 |
| URL normalize | 0.997, 1.001 | 1.005, 1.029 | 1.012 | 0.995 |

Each raw record includes external wall time, kernel user and system CPU time,
lifetime peak RSS, and `ru_nswap`. All workload `ru_nswap` values were zero;
paired peak RSS differences were below 0.6 MiB and had no consistent direction.
The request-path proposed/current CPU reduction exceeded local same-side
variation in both pairs. The search-form gain is close to the largest observed
same-side change. Normalization was neutral against the current guard within
same-side variation. The candidate's request-path cost remained 2% above the
pure parser in both direct pairs. OrbStack Helper used about 104% CPU at the
breadth start and 203% at the end. Wall ratios were less stable than CPU ratios.

## Evidence and limits

The runner is `url-quote-crossover-20260925.py`; its calibration helper is
`url-quote-crossover-20260925-calibrate.py`. Every preparation, build, calibration,
and workload attempt was checkpointed immediately in a fresh JSON file:

- `data/url-quote-crossover-20260925-prepare.json`: three build attempts.
- `data/url-quote-crossover-20260925-calibration.json`: three builds and 36 calibration calls.
- `data/url-quote-crossover-20260925-breadth.json`: three builds and 36 complete workload calls.

The calibration used one byte pattern per length and one timing observation per
case. A quiet-host repeat and more input distributions would be needed to
qualify the exact threshold or integrate the candidate. No dependencies,
formatters, linters, hooks, commits, or remote operations were used.
