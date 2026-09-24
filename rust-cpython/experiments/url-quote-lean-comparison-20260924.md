# Lean Rust URL quotation: calibration-limited comparison

## Decision

**Inconclusive.** The intended matched control/candidate comparison did not
run. The control self-comparison had a 1.35% timing-noise allowance, below the
3% gate, but two serial candidate self-comparisons had 5.81% and 6.19%.
The second was the bounded retry. These rounds cannot support a speed or
memory verdict for the lean overlay. Keep it as an isolated proof; do not
promote it as a qualifying public-path improvement.

## Inputs and boundary

I APFS-cloned `/Users/josh/d/python-build/rust-cpython/stage-no-rust` with
`cp -cR` into ignored `rust-cpython/work/url-quote-lean-comparison-20260924/`
control and candidate trees. The real source path resolved to that path. I
copied only `urllib/parse.py` and `_rust_url_quote.cpython-316-darwin.so` from
the lean proof's `.work/overlay` into the candidate's installed tree. The
original stage and proof overlay were read-only inputs; I verified the
original stage hashes again after the runs. The hashes were:

| File | SHA-256 |
| --- | --- |
| Original and both cloned `bin/python3.16` | `ecbc7340ff2ffce477c43ac8cf10465b896708c9599112f6adcbde105418da5f` |
| Original and control `urllib/parse.py` | `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825` |
| Lean proof and candidate `urllib/parse.py` | `8e29cff7399e7bae9e243bcc022afa43d73ad85912b9468b1e3cc73875079576` |
| Lean proof and candidate extension | `74feaae8a1f52c735a61b94a4abe82daf2f65c4896434aca2b874200ce93a344` |

Each cloned executable resolved its own `sys.prefix` and `urllib.parse.__file__`.
The candidate imported the extension from its own `lib-dynload` and returned
`a%20b` for `quote('a b', safe='')`. Both clones report CPython 3.16.0a0,
`Py_GIL_DISABLED=0`, clang 23.1.2, `-O3`, ThinLTO, and the nine-worker PGO
task. No compilation or new correctness suite ran in this lane. The
[lean proof](url-quote-lean-proof-20260924.md) reports the differential and
CPython URL tests. Its unstripped extension is 50,712 bytes. The source
stage's current executable hash differs from the executable hash in the
[earlier quote comparison](url-quote-comparison-20260924.md), so its
measurements are context, not a matched historical control.

## Calibration and resource accounting

Each local `standard` self-comparison used the registered
`catalog_url_normalize` workload: five counterbalanced serial timing pairs
and three separate memory pairs, with 1,500 operations per workload process.
An operation performs 48 URL normalizations and 48 stable keys. All 48
workload rounds returned 1,500 operations, input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`,
and complete output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
The harness's internal `_run` command avoided writing a baseline snapshot
outside this lane. Full generated results and `time -l` logs remain ignored
under `rust-cpython/results/url-quote-lean-comparison-20260924/`; compact
per-process observations are in
[`data/url-quote-lean-comparison-20260924.json`](data/url-quote-lean-comparison-20260924.json).

| Self-comparison | One-minute load at harness probe | Paired median wall ratio | Timing-noise allowance | RSS self difference | RSS noise allowance |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control/control | 5.22 | 0.99781 | 1.35% | +98,304 B | 291,491 B |
| Candidate/candidate | 5.09 | 1.00189 | 5.81% | +131,072 B | 437,237 B |
| Candidate/candidate retry | 4.37 | 0.99242 | 6.19% | −49,152 B | 255,055 B |

The first candidate calibration was followed by an unrelated
`target/release/xsh` process observed at 54.5% CPU. During the wait for the
retry, OrbStack and WebKit processes were observed at roughly 100% and 83%
CPU in one host sample. I started the bounded retry after the competing
processes subsided, but its timing noise still exceeded the gate. No compiler
or other benchmark process was observed at the start of any calibration.
The load averages and process snapshots show interference risk; they do not
identify a single cause for each timing outlier.

The control self-run's two sides had median external wall times 0.71010 and
0.70947 seconds per 1,500 batches; root kernel CPU medians were 0.46368 and
0.46215 milliseconds per batch. The first candidate self-run's two sides had
median external wall times 0.58878 and 0.58166 seconds, and root CPU medians
0.38317 and 0.37886 milliseconds per batch. The retry sides had median
external wall times 0.58215 and 0.57989 seconds, and root CPU medians
0.37780 and 0.37598 milliseconds per batch. These describe calibration
repeatability only; they are not paired control/candidate effects.

The same self-runs had median peak RSS of 25,575,424/25,673,728 bytes for
control/control, 28,393,472/28,524,544 bytes for candidate/candidate, and
28,704,768/28,655,616 bytes on the candidate retry. Corresponding median
sampled physical footprints were 12,599,776/12,681,672,
15,385,056/15,516,128, and 15,712,760/15,647,200 bytes. The roughly 3 MB
gap between separately timed control and candidate self-runs resembles the
earlier overlay's +3.19 MB result, but it is unpaired and cannot establish a
new regression or a memory allowance for this implementation.

`/usr/bin/time -l` recorded 14.17, 11.98, and 12.05 seconds elapsed for the
three controller commands. Their combined user plus system CPU was 37.19
seconds, below the 120-second budget; the largest controller maximum RSS was
45,809,664 bytes, below 1 GiB, and all reported zero swaps. Controller CPU
includes waited workload children; its RSS maximum is per process. The
timing-pass `wait4` CPU covers each workload root, including startup and
imports. Memory rounds saw one process. The macOS memory pass combines
kernel root peak RSS with external sampled tree RSS and samples physical
footprint separately; transient footprint peaks can be missed. Unique or
proportional memory and a compatible allocation pass were unavailable. The
workload has no marked steady boundary, so retained memory was unavailable.

## Next measurement

Repeat both self-calibrations in a quieter host window and require each to
fall below 3% before a serial matched `standard` control/candidate run.
The registered workload currently fixes 1,500 iterations in
`benchmarks/workloads/registry.py`; increasing that count to lengthen the
timed interval requires a coordinated harness change in a separate lane.
If the host stays busy, retain the inconclusive result rather than treating
separately timed self-runs as a paired comparison.
