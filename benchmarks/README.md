# CPython benchmark laboratory

`benchmarks/` compares compatible CPython interpreters across standardized
benchmarks and repository-owned application workloads. The result is a set of
separate timing, resident-memory, and allocation measurements, plus a report
that shows which workloads improved and which resource gates passed.

The first supported environment is Linux amd64, including the
`x86_64-unknown-linux-musl` python-build artifact. The harness consumes built
interpreters; it does not alter the product build. It does not implement
macOS benchmarking.

## Three independent passes

The same workload is run separately for each measurement. Instrumentation can
change interpreter behavior, so measurements from one pass never stand in for
another.

| Pass | Measures | Instrumentation |
| --- | --- | --- |
| Timing | Wall time, throughput, latency, and repeatability | Minimal; no memory polling, Memray, allocator tracing, or `perf record` |
| Memory | Process-tree peak and steady resident footprint | External Linux `/proc` sampler; not used in timing runs |
| Allocations | Allocation count and bytes, heap high-water mark, allocator and native origins | Memray in a reduced, semantically equivalent run |

Allocation-pass elapsed time is diagnostic only. Do not compare it with normal
timing results. Memory and allocation profiles explain resource changes that a
timing score alone cannot show.

## Prepare and run

From the repository root, `make bench` is the end-to-end product comparison.
It checks the native target, fetches locked product and benchmark inputs,
prepares the offline benchmark image, builds and packages the product when its
archive is absent, then runs the full repository workload suite against the
pinned PBS baseline with all selected pyperformance benchmarks. The default
profile is `standard` (timing plus process-tree memory); override it with
`BENCH_PROFILE=rigorous` to add allocation tracing. The pyperformance
selection follows the profile by default: `fastapi` for `standard`, all
benchmarks for `rigorous`, and `python_startup` for `quick`. Set
`BENCH_PYPERFORMANCE_SELECTION` to a pyperformance group, benchmark name, or
`all` to override that selection.

The supported one-command comparison currently requires native Linux amd64.
Product input fetching and benchmark preparation may use the network; the
measurement container runs with networking disabled. The benchmark result and
runner-specific baseline snapshot are written under `benchmarks/results/` and
`benchmarks/baselines/` respectively.

To prepare or run the components separately, first check the host and fetch
the locked benchmark inputs. Fetching is the network-enabled preparation step;
measurements use the prepared inputs offline.

```sh
python3 benchmarks/bench.py doctor
python3 benchmarks/bench.py fetch
python3 benchmarks/bench.py prepare
```

The profiles trade run time for coverage. `quick` is for iteration, `standard`
is the regular real-world timing and process-memory comparison, and `rigorous`
adds repeated Memray allocation passes. Allocation verdicts are marked
`not_gated` in quick and standard results.

```sh
# Short smoke run
python3 benchmarks/bench.py run \
  --preset pbs --suite smoke --profile quick

# Real application workloads
python3 benchmarks/bench.py run \
  --preset pbs --suite realworld --profile standard

# Full pyperformance and real-world run
python3 benchmarks/bench.py run \
  --preset pbs --suite full --profile rigorous

# Limit a run while investigating one workload or category
python3 benchmarks/bench.py run \
  --preset pbs --suite realworld --profile quick \
  --workload django_wsgi_request
python3 benchmarks/bench.py run \
  --preset pbs --suite realworld --profile quick --category tooling
```

Use `--help` for the exact options available to a command. Runs execute inside
the pinned benchmark image with Docker networking disabled by default;
`--container` makes that choice explicit. `--local` is a diagnostic mode and
does not provide the offline network boundary. The same image accepts either
interpreter at run time; it does not contain a baked-in baseline.

## Compare interpreters

The runner has explicit baseline and candidate inputs. Each can be a Python
executable or a compatible packaged artifact such as a `.tar.gz`:

```sh
python3 benchmarks/bench.py run \
  --baseline /opt/cpython-upstream/bin/python3 \
  --candidate dist/x86_64-unknown-linux-musl/python.tar.gz \
  --baseline-label "upstream CPython" \
  --baseline-kind upstream \
  --candidate-label "python-build CPython 3.14.6" \
  --suite realworld --profile standard
```

This is how to supply an upstream CPython baseline: provide the executable or
artifact you built or obtained, built and configured comparably to the
candidate. Set both `--baseline-label "upstream CPython"` and
`--baseline-kind upstream` only for an upstream build; the kind is recorded in
the result and distinguishes this baseline from PBS. The harness does not
build upstream CPython. It checks interpreter compatibility and records both
identities. Use
`--allow-cross-version` only for an intentional cross-version investigation;
the report labels that research comparison. Cross-version runs import from
source on both sides, since a shared precompiled bytecode tree would favor
one interpreter's cache format.

The `pbs` preset resolves the pinned Astral PBS 20260610 artifact as the
baseline and the current x86-64 musl python-build artifact as the candidate.
Reports label it **Astral PBS**, never upstream CPython. A PBS comparison is
useful for parity research. The pair still receives a baseline-relative
memory verdict: a failure means the candidate regressed against PBS. Only a
comparable upstream CPython build, explicitly labeled `upstream CPython`, can
establish the upstream memory parity guarantee.

Use the same comparison machinery to calibrate a Python against itself:

```sh
python3 benchmarks/bench.py self-compare --python /path/to/python \
  --suite realworld --profile rigorous
```

Rigorous self-comparison characterizes timing, memory, and allocation
repeatability so noise allowances are based on observed variation. To
regenerate a report from an existing result directory, run:

```sh
python3 benchmarks/bench.py compare benchmarks/results/<run>/run
```

Every completed `run` or `self-compare` updates a compact baseline JSON file
under `benchmarks/baselines/`. Its stable path is keyed by runner hardware,
baseline interpreter kind/version, suite/profile, and selected workload names;
repeating the same comparison updates that file in place. `--record-baseline
PATH` selects a specific file under `benchmarks/baselines/` instead:

```sh
python3 benchmarks/bench.py self-compare --python image-python \
  --suite realworld --profile standard \
  --record-baseline benchmarks/baselines/linux-amd64-self-control.json
```

An existing result can refresh its automatically selected baseline without
repeating measurements:

```sh
python3 benchmarks/bench.py record-baseline benchmarks/results/<run>/run
```

The snapshot records per-workload timing, process-tree memory, allocation
rounds when collected, interpreter identity, input-lock and image identity,
and runner CPU, memory, kernel, affinity, and load details. It leaves raw
sampler data and Memray captures in the ignored run directory. Baseline files
are atomically refreshed after successful measurements. A self-comparison is
labeled `self_control_calibration`; it characterizes the runner and harness,
but it does not substitute for a product-versus-upstream baseline.

The benchmark dependency prefix is separate from the tested interpreter. The
controller prepares it from verified wheelhouse inputs, so the tested
distribution does not need to ship `pip` or `venv`. Use `--wheelhouse PATH` to
point at an already fetched wheelhouse.

## Workloads

The `realworld` suite complements pyperformance with larger operations that
exercise recognizable application paths. Its initial workloads cover:

| Workload | What it exercises |
| --- | --- |
| `django_wsgi_request` | Django's WSGI handler, middleware, routing, ORM-backed view, and response construction |
| `django_asgi_request` | The corresponding Django ASGI request path |
| `django_orm_10k` | Materializing and processing a deterministic 10,000-row ORM dataset |
| `django_template_realistic` | Rendering a template with loops, nested values, escaping, and formatting |
| `pylint_source` | A real lint pass over a pinned Python source corpus |
| `pycparser_source` | Parsing pinned C source inputs with pycparser |
| `compileall_source` | Compiling a pinned Python source tree into fresh bytecode output |
| `python_startup` | Fresh interpreter startup |
| `import_django` | Importing Django in a fresh process |
| `import_app_stack` | Importing Django, FastAPI/Pydantic, and SQLAlchemy in a fresh process |
| `pip_install_wheelhouse` | Installing a locked collection of predominantly pure-Python wheels into a fresh target directory, offline |
| `serialization_roundtrip` | Repeated pickle encoding/decoding of a shared object graph with correctness checks |
| `multiprocess_pool` | Process creation and work distribution, with child processes included in memory accounting |

The Django requests go through framework handlers rather than timing a
standalone template call. Schema setup and fixture creation happen outside the
timed operation. Each workload checks a result invariant or digest so a
regression cannot appear faster by silently skipping work. Operation counts
allow timing, memory, and allocation results to be normalized per request,
row, file, import process, or other unit of work.

The `pyperformance` suite remains the standardized layer. Its timing and
Linux memory runs are separate; its aggregate is context, not the overall
verdict. The harness runs the pinned pyperformance 1.14 scripts directly with
an external dependency prefix. For `2to3`, it also prepends the
pyperformance wheel's bundled `vendor/src` compatibility code for that
benchmark only. This avoids the script's fallback to the tested interpreter's
`pip` to install the removed `lib2to3`; the product does not ship `pip`. When
the bundled `lib2to3` source is present, `2to3` runs normally. If it is
missing, the result records `2to3` as unsupported with the reason instead of
silently omitting it.

Payload versions are pinned separately from the interpreter baseline in
[`inputs.lock.json`](inputs.lock.json). Several pyperformance dependencies
use compatible releases because the older upstream pins lack CPython 3.14
musllinux wheels: coverage 7.16.1, dulwich 0.24.10, SQLAlchemy 2.0.43,
MarkupSafe 3.0.3, PyYAML 6.0.3, and urllib3 2.5.0. These versions define this
harness's payload baseline; they are not interchangeable with measurements
from pyperformance using a different dependency set. The pyperformance Django
payload remains pinned at 3.2.4 and may still fail on some CPython 3.14
workloads. The repository-owned Django macros use Django 6.1.1 and should be
read as a distinct workload version. The `full` suite combines pyperformance
with the repository-owned macro suite.

The shared FastAPI payload uses Pydantic 2.13.5, `pydantic-core` 2.46.5, and
their locked transitive dependencies. `pydantic-core` is pinned to its
CPython 3.14 `musllinux_1_1_x86_64` wheel, which is compatible with the
benchmark image's musl 1.2 runtime.

## Memory and allocation measurements

The memory pass samples `/proc/<pid>/smaps_rollup` for the workload process and
its descendants. It records peak total PSS, RSS, private memory (USS-like), and
process count, with the sample interval and raw samples retained in the run
data. PSS is the primary process-tree comparison because RSS counts shared
pages in every process. Steady or post-load PSS is reported only when a
workload marks a meaningful phase boundary; a short-lived batch process has
no steady-state value. A cgroup peak is an optional secondary metric; it is reported
only when a result contains a measurement. The process-tree sampler does not
require cgroup delegation.
The default sampling interval is 10 ms; use `--memory-interval-ms` to change
it, and compare runs only when they use the same interval.

The allocation pass uses Memray separately from timing and memory. It records
total allocations, total allocated bytes, peak heap, allocator information,
and native allocation origins. Counts and bytes are normalized by the
workload's operation count where that is meaningful. Detailed allocation
tracing adds substantial overhead, which is why those durations are not
performance results. The raw Memray binary captures and machine-readable
stats are retained for every profiled run, including separate child captures
when following forks. They live under the ignored `benchmarks/results/` tree;
remove the run directory when the captures are no longer useful, and do not
commit them.

## Verdicts

Reports show per-workload timing, memory, and allocation changes. A timing
geometric mean cannot hide an individual real-world memory regression. Each
explicit interpreter pair receives per-workload memory checks. Against a
designated upstream CPython baseline, each primary workload's peak PSS must
remain within a small, noise-aware parity allowance; applicable steady-state
and post-load memory are checked as well. The allowance is derived from
repeated baseline variation and a small page-scale floor, not a large blanket
percentage. A PBS-relative failure reports a regression against PBS; it does
not establish the upstream guarantee. Workload-level failures remain visible
even when category or suite aggregates improve.

Allocation churn has its own verdict. Clear increases in allocated bytes or
allocation count per operation are highlighted, and material regressions can
fail the resource verdict. Memory failures and allocation failures are
reported separately so the source of a resource regression is clear. PBS
results remain labeled as PBS comparisons and do not receive the upstream
memory guarantee.

## Fairness and limits

The first implementation is for native Linux amd64. It discovers CPU topology
from Linux sysfs instead of assuming a fixed relationship between logical CPU
numbers. Paired runs record placement and ordering; the runner alternates
baseline/candidate order to limit thermal and frequency drift. For a
publication-quality comparison, use an otherwise quiet host and repeat the
run. Provenance records host, CPU, kernel, container, affinity, environment,
and interpreter details so noisy conditions can be assessed later.
ASGI, offline pip installation, and multiprocessing are marked noisy and use
at least five separate process-memory rounds. This follows self-comparison
evidence of occasional pip peak-PSS outliers; it adds observations while
keeping the same baseline-derived resource gate.

The benchmark image is pinned and both sides run against the same image bytes.
Inputs and benchmark dependencies are hash-locked. Fetch/prepare may use the
network, but the measurement phase is offline. Page cache is not forcibly
dropped and no privileged host tuning is performed. CPU frequency, shared
memory bandwidth, virtualization, and kernel scheduling can still affect
results; the report includes repeatability data rather than treating a single
number as conclusive. Low-level `perf` counters are optional diagnostics, not
part of the timing pass. Add `--perf-stat` to collect them as separate
diagnostics for each selected workload:

```sh
python3 benchmarks/bench.py run \
  --baseline /path/to/baseline/python \
  --candidate /path/to/candidate/python \
  --suite realworld --profile standard --perf-stat
```

Missing `perf` or kernel permissions are recorded as unavailable diagnostics;
they do not alter timing measurements or the resource verdict.

## Results

Each run gets a directory under `benchmarks/results/` containing
`provenance.json`, `summary.json`, and `summary.md`. For the default
container-backed run, these files are in the run's `run/` subdirectory. The
summary includes per-workload measurements, ratios, noise estimates, and
verdict reasons. Detailed results are grouped by suite and workload; timing,
memory, and allocation data remain distinct. Logs, raw memory samples, and
Memray captures support investigation and remain under the ignored results
tree.

Provenance includes baseline and candidate identity, Python version and build
configuration, artifact hashes, benchmark input lock hash, benchmark package
versions, container image, host and CPU details, affinity and run order,
measurement settings, and relevant Python environment variables. It is
intended to make a result reproducible or to show why it should be rejected.
Installed-size figures use each executable's containing prefix. For a system
Python such as the image interpreter, that prefix includes unrelated system
files; compare size figures only for similarly laid-out standalone installs.
