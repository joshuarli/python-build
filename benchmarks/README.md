# Head-to-head benchmarks: ours vs Astral PBS (linux x86-64 musl)

Methodology mirrors astral-sh/python-build-standalone PR #1192
(`BENCHMARKS.md`): pyperformance 1.14.0, full suite,
`pyperformance run --rigorous --warmups 2`, run at least twice.
Scope here is only the musl x86-64 pair: our packaged
`dist/x86_64-unknown-linux-musl` tarball against the `reference-pbs` pin in
`sources.lock.json` (release 20260610, CPython 3.14.6).

## Run

```
./benchmarks/run_benchmarks.sh            # parallel: 8 shards/side, 16 pinned cores
./benchmarks/run_benchmarks.sh --serial   # serial: slowest, strongest isolation
```

Parallel results land in `benchmarks/results/<stamp>/` per-shard files
plus one merged JSON per interpreter; serial results land directly in
`benchmarks/results/`. Repeat, then:

```
python3 benchmarks/compare.py benchmarks/results/pbs-314-musl-<t1>.json \
    benchmarks/results/ours-musl-<t2>.json
```

`compare.py` is stdlib-only. It prints per-benchmark mean ratios
(ours/pbs; < 1 means ours faster) and PASS/FAIL on the geometric mean
being within +-1%. `bench_mp_pool` is excluded from the verdict, as in
the upstream figure, but its ratio is still shown.

## Fairness model

Both interpreters run inside one container from `benchmarks/Dockerfile`
(pinned Alpine, PBS reference verified by sha256 at image build) on an
otherwise idle x86-64 host. The benchmark stack
(`benchmarks/vendor/`, hashes in `vendor/SHA256SUMS`) is installed into
each venv with `--no-index`: runs are fully offline and byte-pinned, no
PyPI at run time.

Parallel mode keeps every suite internally contention-free — one
single-threaded benchmark process per pinned real core — while the two
interpreters run concurrently on disjoint cores with byte-identical
shard contents (`benchmarks/shard.py` deals the sorted suite
round-robin). Default 8 shards/side uses CPUs 0-15, i.e. one thread per
physical core on 16-core hosts with (i, i+16) SMT siblings, so no two
workers share a core. CPU assignment interleaves even/odd so each side
spans both CCDs equally on dual-CCD hosts; contiguous halves would park
one interpreter on the better-binned CCD (observed as a systematic
few-% bias). For a published verdict, repeat with swapped halves and
average. Per-side shards merge with `pool.py` (value pooling) into
one JSON per interpreter for `compare.py`.

Two benchmarks bind fixed loopback ports (`asyncio_tcp` and
`asyncio_tcp_ssl` on 8882, `asyncio_websockets` on 8001) and cannot run
concurrently: they are excluded from sharding and run in a serial tail
phase, pbs then ours.

Provenance is two-tier. The caller venvs (which run pyperformance
itself) install fully offline from `benchmarks/vendor/` (`--no-index`,
hashes in `vendor/SHA256SUMS`, verified at image build). Benchmark
payload packages resolve from the package index under pyperformance's
own pinned per-benchmark requirements, identically on both sides; the
versions actually installed are snapshotted from the run's logs into
`payload-versions-<stamp>.txt` next to each merged pair.

Residual noise sources (shared L3/memory bandwidth, host frequency
scaling) affect both sides symmetrically by construction. For a
published verdict prefer `--serial` on an idle host, full suite at
least twice, and record host conditions alongside results.

## Measured results (x86-64 musl, Ryzen 9 9950X, shared host)

Three full rigorous pairs, both interpreters back-to-back in one
container per pair, compared with `compare.py` (geomean of ours/pbs mean
ratios, `bench_mp_pool` excluded as upstream):

| Run (UTC 2026-09-19) | Geomean | n | Method notes |
| --- | --- | --- | --- |
| 01:08 stamp | +6.80% | 119 | contiguous CPU halves (pbs 0-7, ours 8-15); `asyncio_tcp`, `asyncio_websockets` lost on ours (fixed-port race) |
| 01:52 stamp | +7.25% | 122 | interleaved CPUs (even/odd); `asyncio_tcp_ssl` lost on ours (same race, separate benchmark sharing port 8882) |
| 02:34 stamp | +5.76% | 123 | interleaved CPUs; fixed-port serial tail — symmetric coverage |

Stability control: same-interpreter pairs across runs 2/3 score −0.55%
(PBS) and −1.53% (ours), so run-to-run noise on this shared host is
~1–1.5pp — well below the ~6–7% gap.

Interpretation: the measured Linux musl gap is systematic, with
CPU-bound benchmarks running ~5–30% slower while IO-bound benchmarks
(`asyncio_tcp` 1.01x, `asyncio_websockets` 1.00x) sit at parity. It cannot
be attributed to PGO: the pinned PBS musl artifact is LTO-only, and the
presence of `PROFILE_TASK` in sysconfig does not prove training ran;
`--enable-optimizations` is the configure signal that activates CPython's
PGO build. Our Linux build remains LTO-only by policy. The ~6–7% gap needs
further investigation across compiler flags, generated code, dependency
versions, and benchmark noise. `2to3` dies intermittently on both sides
(lib2to3 is gone in 3.14; pyperformance still ships the bench) and is
correctly absent from whichever side it fails on.
