# Catalog URL workload sizing and quiet control

## Decision

`benchmarks/workloads/registry.py` now runs 1,500 complete `catalog_url_normalize`
batches per workload process. A bounded run on the pinned no-Rust fork measured
0.64081 seconds inside the loop, within the target 0.5–1.0 second interval.
One batch still contains 48 URL normalizations and 48 stable keys; all 1,500
iterations check the same complete-output digest. The input digest is
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and the output digest is
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.

The standard no-Rust-fork self comparison gave a 2.61% timing allowance, below
the lane's 3% gate. The subsequent serial upstream-versus-no-Rust-fork control
gave a 0.99995 paired median wall ratio, within its 2.20% allowance. It found
0.39% more root kernel CPU per complete batch on the fork. These data do not
show a repeatable URL speed difference, and no Rust URL implementation was
built or measured. The RSS comparison remains diagnostic because macOS unique
or proportional process memory and allocation measurements are unavailable.

## Inputs and measurement

The no-Rust fork executable was
`/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`, SHA-256
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`.
The vanilla upstream control was
`/private/tmp/python-build-exp-upstream-20260924/rust-cpython/work/upstream-control/stage/bin/python3.16`,
SHA-256 `58743ba42394c18b59d54ca4bfe7360971e3d98da7feabbdadf9e85214d15de8`.
Both report CPython 3.16.0a0, GIL-enabled release ABI, LLVM 23.1.2,
ThinLTO, and a nine-worker PGO task. The installed `urllib/parse.py` files
have identical SHA-256
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`.
The fork and upstream have different source ancestry and build integration;
their independent PGO passes do not have identical profile data. Those
differences limit attribution even though the public URL source here matches.

First, from this worktree root, I sized 1,500 batches with
`/usr/bin/time -l env PYTHONPATH=. <no-Rust Python> -m benchmarks.workloads.catalog_url catalog_url_normalize --iterations 1500`.
That process took 0.70 seconds elapsed, 0.67 user plus 0.02 system CPU seconds,
25,313,280 bytes maximum RSS, and zero swaps. The timed loop was 0.64081
seconds, or 0.427 ms per batch. The old 100-batch baseline was 0.0429–0.0447
seconds internally. Only the registry loop count changed; fixture and digest
definitions remain as described in `catalog-url-workload-20260924.md`.

I then ran the standard local `benchmarks/bench.py self-compare` with
`--suite realworld --workload catalog_url_normalize --profile standard` and
the no-Rust executable on both sides. It ran five alternating timing pairs
and three separate memory pairs. An initial run produced complete raw data
but exited 2 at snapshot publication because I placed `--record-baseline`
outside `benchmarks/baselines/`; its measured 3.18% allowance is retained as
a diagnostic. The corrected run exited 0 and measured 2.61% timing noise,
paired median ratio 1.00368, and −0.32% root CPU seconds per batch for the
arbitrary candidate label. Its timing process loop intervals were
0.6387–0.6630 seconds on baseline and 0.6437–0.6547 seconds on candidate.
The self RSS medians were 24,526,848 and 24,903,680 bytes; the 376,832-byte
difference was below the 765,164-byte self-noise allowance. Each memory
observation had one process. `/usr/bin/time -l` for the corrected controller
reported 13.99 seconds elapsed, 12.74 user plus 0.92 system CPU seconds,
43,941,888 bytes maximum RSS, and zero swaps. Kernel `wait4` CPU covers the
single workload process, including startup and imports; per-operation values
use the 1,500 batch count. The separate internal wall interval excludes
startup and imports.

The matched control used `benchmarks/bench.py run` with upstream as baseline,
the no-Rust fork as candidate, the same selected workload, standard profile,
and local execution. All 16 timing and memory processes in that run returned
the fixed digests and 1,500 operations. The paired wall ratios were
0.99995, 1.00447, 1.02946, 0.97119, and 0.99782; median 0.99995. Root
kernel CPU medians were 0.45763 ms/batch upstream and 0.45941 ms/batch fork.
Peak RSS medians were 24,838,144 bytes upstream and 24,641,536 bytes fork;
the −196,608-byte direction was just within the 198,645-byte diagnostic
allowance. The controller took 14.20 seconds elapsed, 12.79 user plus 1.00
system CPU seconds, 43,974,656 bytes maximum RSS, and zero swaps. This is a
control comparison, not evidence of a Rust URL improvement.

The host was Apple M1 Pro, macOS 26.5.2, with 10 logical CPUs. Load averages
at the corrected self and matched harness probes were respectively 4.33 and
4.50 for one minute; before sizing they were 2.31, and no compiler, PGO job,
or competing benchmark appeared in the process check. The final matched run
ended at one-minute load 4.40. The local mode had no network boundary or CPU
affinity. The controller's `time -l` CPU sums include waited children; the
maximum RSS is a per-process maximum rather than a simultaneous tree sum.
Across sizing, two self runs, and the matched run, the recorded user plus
system CPU was about 41.8 seconds, below the 120-second budget; maximum
reported RSS was 45,416,448 bytes, below 1 GiB. No run reported a swap.

Compact per-process wall, kernel CPU, RSS, physical-footprint, digest, host
load, identity, and noise observations are in
[`data/catalog-url-quiet-baseline-20260924.json`](data/catalog-url-quiet-baseline-20260924.json).
Full harness outputs remain uncommitted under
`rust-cpython/results/catalog-url-sizing-20260924h/` in this worktree.
