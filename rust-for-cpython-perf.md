# Rust-for-CPython performance phase

**Active.** All 71 targets in [rust-for-cpython.md](rust-for-cpython.md)
are complete under its strict Python-suite coverage rule, and those rules
still bind every performance change. The old experiment archive was
removed from the active tree; its detailed reports and raw data remain
recoverable from Git history at commit `f0f8690`.

## Objective after coverage

Make the covered stdlib faster and more resource efficient on representative
application workloads without sacrificing Python-level correctness. Compare
against matched upstream CPython 3.16 and the preceding accepted fork. Keep
wall latency, actual process-tree user/system CPU, peak and retained memory,
allocation activity, installed native size, and build complexity separate.
Use quiet, paired runs and self-comparison noise bounds. A microbenchmark
alone does not establish a practical gain. A coverage port may remain even
when a later performance result is negative; record that debt plainly.

## Goals

Every one of the 71 checklist routes, judged on its own, must use **no
more CPU and no more memory than the pristine control, and should reach
0.9x of it**: each ratio (Rust candidate over control) belongs in the band
0.9x to 1.0x.

- **Measured per module.** `rust-cpython/perf_modules.py` holds one kernel
  per checklist route that exercises the public behavior the checklist says
  reaches Rust, with deterministic inputs and an output digest both
  interpreters must match. Each sample is a fresh process. The three
  metrics are kernel CPU per iteration (`time.process_time()`), fixed load
  footprint (imports, lazily loaded extensions, and first-call caches,
  estimated as a first setup-and-call's footprint growth minus a
  second's), and working peak footprint over the kernel loop (the kernel's
  `ri_interval_max_phys_footprint`, reset at loop start). Memory values
  below 64 KiB (load) or 256 KiB (working peak) are raised to that floor
  before a ratio is taken, so negligible memory compares as equal.
- **Status per module** from `python3 rust-cpython/perf.py goals`: two
  independent runs of five alternating-order rounds each. A metric is
  **OVER** when both runs' 95% intervals sit above 1.01x, **BEYOND** when
  both sit below 0.9x, **MET** when the pooled median is at most 1.01x,
  and **UNCLEAR** otherwise. A module takes its worst metric's status and
  is BEYOND only when every metric is. Output mismatches read MISMATCH.
- **Done for a module** means MET or BEYOND on all three metrics. OVER
  modules are the climb's targets, largest ratio first; UNCLEAR modules get
  more rounds before any lane. A MET module is climbed toward 0.9x only
  after no OVER module remains. Climbing stops on a metric once it is
  BEYOND.
- **Application workloads guard.** The seven baseline-set workloads run as
  guards on every gated step; a module win that regresses a guard is
  rejected. Kernel results are the goal; application results keep it
  honest.
- A route that cannot reach 1.0x after two failed lanes is recorded as
  debt in the ledger. Removing a Rust route to meet a goal needs the
  user's decision; coverage still holds.

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
`perf.py` builds, suites, and profiles share a repository-wide host lease
that its measurements hold exclusively, across every worktree. The
coverage `build.py` does not take the lease; do not run it during the
climb.

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
  Configure selects `dev` whenever `--enable-optimizations` is absent, and
  each Rust extension rule moves its artifact out of the Cargo target
  directory, so a `make install` without the override rebuilds and installs
  `dev` artifacts. `perf.py` passes `CARGO_PROFILE=release
  CARGO_TARGET_DIR=release` to both `make` and `make install`, fails if
  either log shows `--profile dev` or a `debug` Cargo tree exists, and
  proves every installed Rust extension byte-identical to a release
  artifact. Its report records the stage-tree digest, and `bench` refuses a
  stage that changed after its build.

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
`perf.py bench --baseline @control --candidate @incumbent --workload
zlib_decode_1m` measures one workload; substitute any workload or suite
name. For the whole picture, `perf.py test --name perf-rust --all` runs
every default-resource CPython suite, and `perf.py bench ... --gate
--all-workloads` runs every workload with locked 3.16 inputs. The 3.16
input closure covers Django plus package-free workloads only, so four
registered workloads (`pylint_source`, `pycparser_source`,
`import_app_stack`, `pip_install_wheelhouse`) are unavailable; the
23-workload eligible subset is the entire suite for this lane until those
closures exist. A focused win never overrides a full-suite regression:
judge each workload separately.

## Hill-climbing loop

A Sonnet 5.5 coordinator runs the climb with the repository skill
[`.claude/skills/rust-cpython-perf`](.claude/skills/rust-cpython-perf/SKILL.md);
climber subagents (`.claude/agents/rust-perf-climber*.md`, pinned to
`claude-sonnet-5-5` at `high` or `xhigh` effort, each in its own worktree)
follow [`.claude/skills/rust-cpython-perf-climber`](.claude/skills/rust-cpython-perf-climber/SKILL.md).
`perf.py goals` supplies the debt map (OVER modules first). One lane tests
one hypothesis about one module route: profile its kernel, edit,
incremental build, primary suite, and an exploratory bench against the
incumbent; then a clean build, every relevant suite, a gated verdict with
the application guards, and the route's goal row. The coordinator
integrates accepted lanes in batches, runs the full suite and a batch gate
against the incumbent, promotes the batch to `perf-rust`, and re-measures
goals and workloads against the control.

`perf.py bench` decides each attempt in code (`rust-cpython/perf_verdict.py`).
Per module kernel it classifies CPU, load footprint, and working peak, and
per workload wall time and kernel CPU per operation, from the bootstrap
95% interval of the paired candidate/baseline median; workload peak memory
uses the controller's repeatability bound. Each is held to a 1% practical
floor. Outputs that differ from the baseline reject the attempt
(`compileall_source` against the control is the documented marshal byte
difference and is reported instead). A metric is `improved` or `regressed` only when every
independent run agrees, and `unstable` when runs disagree. The decision is
REJECT on any replicated regression, INCONCLUSIVE on an unquiet host
(below 80% CPU idle around the runs, or on battery; `calibrate` proves the threshold on a given host), unstable metrics, or a
gate with one run, ACCEPT on a replicated target improvement, and NEUTRAL
otherwise. `--gate` also requires clean builds of committed overlays, a
challenger containing the incumbent commit, the memory pass, two runs, and
the seven baseline-set workloads as guards. `perf.py calibrate` applies the
same rules to one build against itself; every workload must read neutral
before a session climbs.

### Ledger

One row per integration, maintained by the coordinator. Ratios are
candidate over baseline for the batch targets.

| Date | Commit | Lanes | vs previous incumbent | Goal status vs control |
| --- | --- | --- | --- | --- |

## Release-grade confirmation (later)

The fast-iteration harness is the climbing standard. Before claiming a
release-grade result, repeat the key comparisons on matched `-O3` PGO and
ThinLTO builds of both sides, and keep these rules throughout:

- Build matched optimized GIL-enabled interpreters with the same compiler,
  PGO task, ThinLTO, target flags, source revision, and Python dependencies.
  Restore the historical optimized recipe from Git history for that step;
  the coverage builder deliberately exposes only debug builds.
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

## Baseline (2026-09-29, macOS arm64, provisional)

**Correction.** The numbers first recorded here (`d41b580`) measured a
candidate whose installed Rust extensions were Cargo `dev` artifacts:
`make install` ran without the release override, rebuilt every Rust member
in `dev`, and installed those (the installed `_json_rs` was byte-identical
to the 1,158,912-byte `dev` artifact, not the 570,096-byte release one).
Its decompression headline (8.7x, "9x to 24x against system zlib") and its
338 MB size figure described unoptimized Rust. Those results and the
`benchmarks/baselines/rust-cp316-perf-*.json` files recorded with them are
superseded; refresh the baselines with the coordinator's gated
`--record-baselines` run.

Verified pair: `perf-upstream` (1 release Rust extension, `_base64`) and
`perf-rust` (70 release Rust extensions, each byte-identical to its release
artifact), both at `d41b580`, -O2, no PGO, no LTO. Installed size: 278.1 MB
to 306.7 MB (+10.3%).

Per-module goals (`perf.py goals`, two runs of five rounds, 833 s): **63
OVER, 6 UNCLEAR, 2 MET** of 71 routes. The host was in interactive use
(67% to 74% CPU idle), so the run is flagged not quiet; rerun on a quiet
host before recording statuses in the ledger.

- CPU: 16 routes are at or under 1.0x. Nine are already BEYOND (below 0.9x):
  `statistics` 0.13x, `shlex` 0.32x, `urllib.parse` 0.37x, `ipaddress`
  0.48x, `tomllib` 0.60x, `tarfile` 0.68x, `codecs` 0.77x, `textwrap`
  0.78x, `importlib.metadata` 0.85x. The largest CPU debts: `decimal`
  5.9x, `functools` 5.0x, `json` 4.7x, `os.path` 4.7x, `sqlite3` 3.9x,
  `bisect` 3.9x, `fractions` 3.3x, `datetime` 3.3x, `base64` 3.2x, `csv`
  3.1x.
- Load footprint: only 6 routes are at or under 1.0x. The largest absolute
  debts: `lzma` +59 MiB (100 MB against 40 MB), `compression.zstd` +12 MiB,
  `plistlib` +5.1 MiB, `bz2` +3.0 MiB, `tomllib` +2.8 MiB, `zlib` +2.4
  MiB, `re` +1.9 MiB, `gzip` +1.3 MiB, `configparser` +1.2 MiB, `json`
  +1.1 MiB; about 107 MiB across all routes.
- Working peak is OVER for `asyncio`, `glob`, `plistlib`, and
  `xml.etree.ElementTree`.

Application workloads: a single exploratory run puts `zlib_decode_1m` at
1.96x wall and 1.37x CPU against the control (not 8.7x). The seven-workload
self-calibration read neutral on every workload and metric. The full gated
workload comparison is pending a quiet host. `compileall_source` output
differs from the control by design (the checklist's marshal note), so it
is reported, not timed, against the control.

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
