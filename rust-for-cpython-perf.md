# Rust-for-CPython performance phase

**Deferred. Do not start this phase until every module in
[rust-for-cpython.md](rust-for-cpython.md) is complete under its strict
Python-suite coverage rule.** The old experiment archive was removed from
the active tree; its detailed reports and raw data remain recoverable from
Git history at commit `f0f8690`.

## Objective after coverage

Make the covered stdlib faster and more resource efficient on representative
application workloads without sacrificing Python-level correctness. Compare
against matched upstream CPython 3.16 and the preceding accepted fork. Keep
wall latency, actual process-tree user/system CPU, peak and retained memory,
allocation activity, installed native size, and build complexity separate.
Use quiet, paired runs and self-comparison noise bounds. A microbenchmark
alone does not establish a practical gain. A coverage port may remain even
when a later performance result is negative; record that debt plainly.

## Fast-iteration harness (no PGO, no ThinLTO)

Coverage is complete under the strict suite rule in
[rust-for-cpython.md](rust-for-cpython.md), so this phase opens with a
fast-iteration harness. Both interpreters are built with the same locked
LLVM 23.1.2 compiler, the same `-O2` target flags, and the same macOS SDK;
GIL-enabled; no `--enable-optimizations` (no PGO profile task), no
`--with-lto`, no debug info, and test modules left enabled. `-O2` compiles
markedly faster than `-O3` while staying a fair matched comparison; the
checked-in standard stays there. Anything leaner (notably a Cargo `dev`
profile) is explicitly not comparable. The only deliberate difference
between the two interpreters is the source overlay. The builder is
`rust-cpython/perf.py`; it installs into
`rust-cpython/stage-perf-<name>/` with build trees under
`rust-cpython/work/perf/<name>/`, leaving the coverage `work/build` and
`stage` trees untouched. Timing baselines require an otherwise quiet host:
do not run perf builds or benchmark passes while a coverage build or suite
is active.

- Control `perf-upstream`: the pinned fork source with an empty overlay
  (pristine fork, no Rust overlay crates). The fork source still carries its
  built-in `Modules/_base64` Rust extension and Cargo scaffolding, which
  public `base64` never reached during coverage; that residue is disclosed,
  not hidden. A byte-exact CPython-upstream control at the fork base is a
  later follow-up, not this baseline.
- Candidate `perf-rust`: the same source with the full committed overlay
  applied (all 71 coverage routes).
- Both use Cargo `release` for the compiled Rust members. A `dev` profile
  would punish the Rust routes artificially and is not a performance result.

Run repository-owned application workloads first; targeted kernels explain
mechanisms only. The first baseline set on native macOS arm64
(`--local`, `--profile standard`) is `python_startup`,
`serialization_roundtrip`, `zlib_decode_1m`, `gzip_extract_1m`,
`django_wsgi_request`, `django_template_realistic`, and `import_django`:
stdlib-only workloads need no wheelhouse, and the Django workloads use the
committed `benchmarks/inputs.macos-cp316.lock.json` closure. Each run pairs
baseline and candidate invocations on the same host with the controller's
alternating order, keeps wall latency and kernel process-tree CPU from the
uninstrumented timing pass separate from the sampled RSS/physical-footprint
memory pass, and records per-workload noise from repeated rounds plus a
`self-compare` calibration of the control. Allocation tracing stays
unavailable on macOS (unknown, never zero); installed size comes from each
stage prefix. Baselines are checked in with explicit
`--record-baseline benchmarks/baselines/rust-cp316-perf-<workload>.json`
paths; raw run directories stay ignored. Broad pyperformance follows only
after these representative comparisons read clean.

Granularity runs both directions. For module focus, `perf.py test --name
perf-rust --suite test_zlib` runs one CPython suite on a perf build, and
`bench.py run --local --workload zlib_decode_1m` measures one workload;
substitute any workload or suite name. For the whole picture,
`perf.py test --name perf-rust --all` runs every default-resource CPython
suite, and `--suite realworld` runs the workload set. Note the 3.16
input closure covers Django plus package-free workloads only, so a bare
`--suite realworld` on 3.16 stops at four workloads needing other inputs
(`pylint_source`, `pycparser_source`, `import_app_stack`,
`pip_install_wheelhouse`); the 23-workload eligible subset is the entire
suite for this lane until those closures exist.
A focused win never overrides a full-suite regression: judge each workload
separately.

- Build matched optimized GIL-enabled interpreters with the same compiler,
  PGO task, ThinLTO, target flags, source revision, and Python dependencies.
  Restore the historical optimized recipe from Git history when this phase
  begins; the active coverage builder deliberately exposes only debug builds.
- Run repository-owned complete application workloads first: Django
  WSGI/ASGI/ORM, startup/import, tooling, packaging and archive operations,
  serialization, and multiprocessing. Use targeted kernels only to explain
  mechanisms. Run broad pyperformance only after the representative
  application comparisons.
- Measure wall latency and kernel-accounted process-tree CPU per logical
  unit in an uninstrumented timing pass. Measure peak/retained RSS and
  unique or proportional memory separately. Use a separate allocation pass
  where a suitable tool exists. Missing metrics are unknown, never zero.
- Calibrate control against itself. Pair equivalent control/candidate work
  on the same quiet host, counterbalance order, retain raw observations, and
  report noise intervals. Do not infer CPU use from wall time.
- Check installed Python source and bytecode-cache identity before measuring.
  `PYTHONDONTWRITEBYTECODE=1` blocks writes but still permits existing
  `.pyc` reads; stale caches can dominate startup memory.
- Judge each important workload separately. A global gain does not hide a
  clear regression. Compare native binary size and maintenance cost after
  correctness and resource results.

## First baseline (2026-09-29, macOS arm64)

Both sides built from the pinned fork source with locked LLVM 23.1.2,
`-O2 -mcpu=apple-m1`, macOS SDK 26.5, GIL-enabled, no PGO, no ThinLTO,
Cargo `release`: control `stage-perf-upstream` (empty overlay) versus
candidate `stage-perf-rust` (329 overlay files, all 71 routes). Seven
`--local --profile standard` paired runs plus control `self-compare`
calibration on Apple M1 Pro (MacBookPro18,3). Baselines checked in as
`benchmarks/baselines/rust-cp316-perf-<workload>.json`; the control
repeatability runs refreshed the `darwin-arm64-*-self-*.json` files.
Timing verdicts use the controller's paired noise bounds; allocation
tracing is unavailable on macOS.

| Workload | Wall vs control | Timing | Peak RSS vs control | Memory |
| --- | --- | --- | --- | --- |
| `python_startup` | +1.5% (noise bound 24.9%) | pass | +4.2% (+590 KB) | fail |
| `serialization_roundtrip` | +2.3% (bound 5.0%) | pass | +16.4% | fail |
| `zlib_decode_1m` | +773.6% | fail | +41.5% | fail |
| `gzip_extract_1m` | +59.9% (bound 18.8%) | fail | +25.3% | fail |
| `django_wsgi_request` | +8.3% (bound 9.8%) | pass | +12.6% | fail |
| `django_template_realistic` | +16.5% (bound 5.0%) | fail | +11.8% | fail |
| `import_django` | +33.6% (bound 53.8%) | pass | +17.9% | fail |

Control `self-compare` ratios sit at 1.00–1.03 with timing pass, so the
candidate gaps are real effects, not runner noise. Installed size grows
285 MB to 338 MB (+18.6%) with the 69 extra release-built extensions.

Two debts carry forward. First, decompression throughput: the port uses
`flate2` with its pure-Rust backend instead of system zlib, and the
one-shot wrapper loops over 64 KB chunks with an unreserved output vector
and an order-n input drain each round; scaling runs show 9x at 1 KB
widening to 24x at 1 MB against system zlib, so backend and growth
strategy stack. Second, resident memory grows on every workload (+4 to
+42%), consistent with dozens of additional mapped extensions plus larger
working buffers; the next step is attributing it per workload rather than
treating the single peak number as one cause. Neither debt revokes any
coverage item.

## Historical findings

The previous performance-first loop produced many narrow Rust kernels but
**zero fully qualified coverage modules**. The fork's private `_base64`
extension was not reached by public `base64`. Optional URL, TAR, IPv4,
timestamp, UUID, shlex, fraction, zlib, and Base64 routes were partial.
Several showed promising narrow timing results; others had regressions or
unresolved Python semantics. None establishes a practical interpreter-wide
gain. The prior benchmark system is retained under `benchmarks/` for the
production project and eventual performance phase, but it is not part of
the active Rust coverage loop.
