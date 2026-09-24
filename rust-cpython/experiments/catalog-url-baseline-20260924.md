# Catalog URL baseline calibration

## Result

The registered `catalog_url_normalize` workload ran against the same pinned
no-Rust fork interpreter on both sides. Its 48-record input and complete-output
digests matched in every timing and memory process. The standard-profile
self comparison gave a 1.0096 paired median wall ratio and a **6.62% timing
noise allowance**. That allowance is large relative to a narrow quotation
optimization, so this run does not support an upstream-versus-fork timing
claim. I stopped before that comparison as required by the lane's noise gate.
There is no Rust URL candidate or speed claim here.

The host was moderately occupied: load averages were 4.75/7.32/8.19 just
before the command, 5.19/7.32/8.19 at the harness probe, and
5.89/7.43/8.22 just after. The scheduling check found no compiler, PGO job,
or other benchmark process. The run was local, without an offline network
boundary or CPU affinity. These facts and the short 43–45 ms internal batch
times limit the precision of this calibration.

## Exact measurement

From `/private/tmp/python-build-exp-url-baseline-20260924f`:

```sh
/usr/bin/time -l python3 benchmarks/bench.py self-compare \
  --python /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 \
  --suite realworld --workload catalog_url_normalize --profile standard --local \
  --output /private/tmp/python-build-exp-url-baseline-20260924f/rust-cpython/results/url-baseline-20260924/self \
  --record-baseline /private/tmp/python-build-exp-url-baseline-20260924f/benchmarks/baselines/url-baseline-self-20260924.json
```

The executable SHA-256 was
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`.
It reported CPython 3.16.0a0, GIL-enabled release ABI, LLVM 23.1.2,
ThinLTO, and the nine-worker PGO profile task. Both sides used this exact
executable. The harness ran five alternating timing pairs and three separate
memory pairs, each with 100 complete 48-URL/48-key batches. No wheel site was
prepared. The fixed input digest was
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`;
every process returned output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.

`/usr/bin/time -l` reported 3.23 s elapsed, **1.94 user + 0.83 system CPU
seconds**, 45,301,760 bytes maximum resident set size, 33,030,648 bytes peak
memory footprint, and zero swaps for the controller command. These CPU
figures include its waited workload processes; its maximum RSS is a process
maximum, not a simultaneous tree sum. The 2.77 CPU seconds and 45.3 MB
observed maximum remained below the lane limits of 120 CPU seconds and
1 GiB RSS.

The raw per-process observations are in
[`data/catalog-url-self-baseline-20260924.json`](data/catalog-url-self-baseline-20260924.json).
Each timing process performed 100 operations. Internal batch wall times were
0.0429–0.0447 s, or 0.429–0.447 ms per complete batch; the separate external
process times include interpreter startup and imports. Kernel `wait4` CPU
medians were 0.878 ms and 0.886 ms per batch for the arbitrarily labeled
baseline and candidate sides, respectively. The paired wall ratios ranged
from 0.965 to 1.041; their median 1.0096 was within the harness's 6.62%
noise allowance. Peak RSS medians were 25,362,432 and 25,722,880 bytes,
a 360,448-byte difference within the 801,600-byte self-noise allowance.
Only one interpreter process ran per observation, so the root `wait4` CPU
covers the workload process; the macOS sampled RSS and physical footprint
can miss transient peaks. Unique/proportional memory and allocation data
remain unavailable. The harness labels its overall resource verdict
`INCOMPLETE` for that reason, despite the observed RSS difference passing
its diagnostic noise check.

## Next quote-headroom gate

Repeat this same self comparison when host load is quiet, with a longer
steady batch duration if the registered workload can be adjusted without
changing its 48-record fixture or digest. Only then run a serial matched
upstream-versus-fork comparison, using the built upstream control under
`rust-cpython/work/upstream-control/stage` and retaining the same workload
input, process counts, kernel CPU, and memory observations. Source ancestry,
build integration, and independent PGO profiles remain attribution limits
even when configure flags match. That comparison is a control check, not a
Rust URL result.

To test the actual quotation hypothesis, profile **complete**
`normalize_url` plus `stable_key` batches on the no-Rust fork and measure the
share spent in `urllib.parse.quote_from_bytes` as well as the share of calls
that meet the proposed exact-bytes guard. The earlier single-record
instrumented profile located quote calls but cannot establish headroom for
this mixed 48-record workload. A native helper merits an isolated trial only
if that complete-workload share is material, and any trial needs unchanged
public behavior plus gains beyond a quieter self-comparison bound.
