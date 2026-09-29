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
- **Sequencing.** The climb is memory-first. Only load footprint and working
  peak are targeted until every module reads MET or BEYOND on both (or is on
  the debt list); kernel CPU must not regress meanwhile. CPU lanes start
  after that. Up to 8 lanes run concurrently for memory, 4 for CPU.
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
| 2026-09-29 | `59ec0b8` | etree-mem, zstd-mem (memory phase) | Gate ACCEPT, quiet=yes, guards neutral. `xml.etree.ElementTree` cpu 0.313x, load 0.750x, peak 0.250x (all improved). `compression.zstd` cpu 0.934x improved, load 0.721x and peak 0.403x (neutral by interval, points below 1.0). | `xml.etree.ElementTree` OVER: cpu 0.92x MET, load 1.21x OVER (+176 KiB, from `_re_rs`/contextlib imports outside the lane; see `re-mem`), peak 1.34x UNCLEAR. `compression.zstd` OVER: cpu 1.94x OVER (CPU phase), load 1.45x UNCLEAR, peak 0.79x MET; open lead: `_zstd/*.c` runs C libzstd first and Rust on a copy. `goals --min-idle 0`, memory rows only. |
| 2026-09-29 | `3f5846f` | lzma-mem (memory phase) | Gate ACCEPT, quiet=yes, guards neutral. `lzma` load 0.049x (improved), cpu 0.973x and peak 1.000x (neutral). | `lzma` memory MET: load 0.12x BEYOND (4.9 MiB vs 39.8 MiB), peak 1.00x MET; cpu 1.36x OVER (CPU phase: lzma-rust2 match-finder speed). Known limit: decoding streams with an 8 MiB dictionary still touches 8 MiB (crate zero-fills the declared dictionary); the kernel does not exercise it. |
| 2026-09-29 | `b8d3c46` | re-mem, zstd-glue (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `re` load 0.035x improved (cpu, peak neutral). `compression.zstd` cpu 0.462x, load 0.501x improved, peak 0.204x neutral. | `re` MET (all three 1.00x). `compression.zstd` MET: cpu 0.90x, load 0.91x, peak 0.48x. `xml.etree.ElementTree` moved to UNCLEAR (load 1.27x, peak 1.19x): the `re` import cost went, a per-dylib floor remains. Lane gate of zstd-glue REJECTed on `import_django` 1.02-1.03x from a worktree build; the primary-path batch gate read neutral (worktree-path bias). |
| 2026-09-29 | `555de63` | bz2-mem, asyncio-mem, ospath-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `bz2` load 0.673x. `asyncio` cpu 0.776x, peak 0.516x. `os.path` cpu 0.373x, load 0.269x. | `bz2` UNCLEAR at parity (cpu 1.02x, load 0.99x MET, peak 1.00x MET). `asyncio` OVER: load 1.07x (13 other `_*_rs` dylibs on its import path), peak MET. `os.path` OVER: load 1.70x (136/80 KiB, about one page above control), peak MET. Review item: the bz2 fix serves large zeroed tables without memset (relies on libbz2-rs-sys not reading before writing; MallocScribble runs matched control). |
| 2026-09-29 | `050f06e` | json-mem, tomllib-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral (`gzip_extract_1m` cpu 0.994; the tomllib lane gate's +2.7% there was worktree-path bias). `json` cpu 0.153x, load 0.140x. `tomllib` cpu 0.121x, load 0.050x, peak 0.457x (neutral). | `json` MET: cpu 0.71x BEYOND, load 0.76x, peak 1.00x. `tomllib` UNCLEAR at the floor: cpu 0.07x BEYOND, load 1.24x (224/184 KiB), peak MET. Full `goals` at `050f06e`: OVER 56, UNCLEAR 10, MET 5 (was 63/6/2 at the first baseline). |
| 2026-09-29 | `d84fa9f` | plistlib-mem, zlib-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `plistlib` cpu 0.038x, load 0.082x, peak 0.401x (all improved). `zlib` cpu 0.481x, load 0.825x improved, peak 0.327x neutral; `zlib_decode_1m` wall 0.267x and `zlib_stream_4k` wall 0.321x improved. | At `6c153ab`: `plistlib` UNCLEAR at the floor (cpu 0.08x BEYOND, load 0.76x MET, peak 1.09x on 296/256 KiB). `zlib` UNCLEAR at the floor (cpu 0.60x BEYOND, load 1.02x, peak 0.86x MET). The plistlib lane gate REJECTed on `import_django` cpu 1.028 (worktree-path bias); the primary-path batch gate read 1.008 neutral. Intentional plistlib changes: equal XML dict keys share one str; `load()` reads a file object whole; module-level helper names `binascii`/`struct`/`re`/`itertools`/`ParserCreate` no longer exist on `plistlib` (private test helpers resolve via `__getattr__`). `_gzip_rs`, `_zip_rs`, `_zipimport_rs` still use flate2. |
| 2026-09-29 | `6c153ab` | binascii-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `binascii` cpu 0.894x, peak 0.414x improved, load 0.818x neutral. `base64` cpu 0.907x improved, load 0.684x and peak 0.309x neutral. | `base64` OVER on cpu only (2.90x; memory MET: load 0.94x, peak 1.00x). `binascii` OVER on cpu (1.67x); load 1.01x UNCLEAR, peak 0.95x MET. Full `goals` at `6c153ab`: OVER 54, UNCLEAR 12, MET 5. Row noise: control working peak swings 16 KiB to 1.7 MiB between runs on some kernels (`shutil`), so UNCLEAR rows get a rigorous rerun before a lane. |
| 2026-09-29 | `358d7cf` | statistics-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `statistics` cpu 0.605x improved, load 0.557x and peak 0.668x neutral (points below 1.0). Also confirms the workspace-wide `panic = "abort"` profile (needed for `no_std`): eight modules that import many dylibs read neutral on every metric. | `statistics` UNCLEAR at the floor: cpu 0.08x BEYOND, load 1.03x (744/696 KiB), peak MET. Residual load is `import statistics` loading `_fractions_rs`, `_itertools_rs`, `_bisect_rs`, `_re_rs` (per-dylib cost). Image 408 KiB -> 70 KiB. |
| 2026-09-29 | `a97f52a` | marshal-mem, configparser-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `marshal` cpu 0.345x improved, load 0.902x and peak 1.000x neutral. `configparser` cpu 0.175x, load 0.296x, peak 0.856x improved. Public `marshal.dumps` bytes now match pristine CPython (FLAG_REF only on shared/interned objects). | `marshal` UNCLEAR at the floor (cpu 0.88x BEYOND, load 1.05x, peak MET). `configparser` MET (cpu 0.22x BEYOND, load 0.88x, peak 0.87x BEYOND). Full `goals` at `a97f52a`: OVER 52, UNCLEAR 12, MET 7 (63/6/2 at the first baseline). Working peak is MET or near it on nearly every module; the remaining debt is mostly load footprint from other routes' dylibs on each import path. |

### Workload picture at `3f5846f` (quiet gate, `@control` vs `@incumbent`, all 23 workloads)

Recorded 2026-09-29 with `--record-baselines`; the baselines under
`benchmarks/baselines/rust-cp316-perf-*.json` now cover every eligible
workload. Peak RSS reads regressed on 21 of 23 workloads (+3% `python_startup`,
+9% to +17% on Django, catalog, and difflib, +32% `zip_read_wheel`), which is
interpreter-wide memory overhead the per-module kernels do not isolate:
imports of Rust routes at startup and first use. CPU/wall regressions to
schedule in the CPU phase: `difflib_unified_mostly_equal` 3.3x cpu,
`zlib_decode_1m` 1.4x cpu / 1.9x wall, `zlib_stream_4k` 1.4x / 2.0x,
`zip_read_wheel` 1.4x / 1.6x, `django_orm_10k` 1.2x cpu / 2.0x wall, `import_django`
1.3x, `zipimport_cold` 1.3x. Improved: `catalog_search_form` 0.42x wall,
`rust_base64_large` 0.61x wall, `catalog_request_path` 0.81x wall,
`gzip_extract_1m` 0.81x wall (but 1.34x cpu). `compileall_source` differs by
design.

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
