You are working on the current `main` branch of `joshuarli/python-build` on a **native Linux amd64 host**.

Implement this specification to completion. Do not merely write a plan.

Read the repository’s current `AGENTS.md` and inspect the existing `benchmarks/` implementation before changing anything. The local checkout is authoritative if it has advanced since the research snapshot below.

Do not push.

## Research snapshot

At the time this specification was prepared, `main` was:

```text
766f1abd03b534640bddebb17bd5834e774284d0
```

The existing product builds CPython 3.14.6. The existing benchmark harness is narrowly focused on:

```text
our x86_64 musl build
vs
Astral python-build-standalone
```

using pyperformance 1.14.0 in an Alpine container.

That existing work has useful pieces:

* pinned benchmark container;
* CPU affinity;
* serial and parallel execution modes;
* pyperf JSON;
* repeatability awareness;
* offline caller-side wheels;
* existing comparison/report code.

Preserve good machinery where justified.

However, its scope is no longer sufficient.

## Critical task boundary

This task is **independent of any Rust-for-CPython work**.

Do not assume:

* a `rust-cpython/` directory exists;
* CPython 3.16 support exists;
* Rust is installed;
* any stdlib implementation has changed;
* any previous Rust-related plan has been implemented.

Do not add Rust-related code in this task.

The benchmark harness must improve the **entire python-build repository as it exists today**, beginning with the current CPython 3.14.6 Linux amd64 product.

The resulting harness should naturally remain usable later against:

* another 3.14 build;
* CPython upstream;
* PBS;
* a future 3.16 build;
* a future Rust-enhanced CPython;
* arbitrary compatible CPython executables.

But do not build speculative abstractions specifically for future Rust.

## Mission

Replace the current “mostly pyperformance timing comparison” concept with a serious CPython benchmarking laboratory that measures:

```text
1. standardized interpreter performance
2. genuinely realistic application workloads
3. startup/import performance
4. packaging/tooling workloads
5. resident memory footprint
6. allocation count and allocation volume
7. process-tree memory behavior
8. optional low-level CPU diagnostics
```

The harness must answer questions such as:

```text
Did this Python build make Django faster?

Did it make a realistic Django process larger?

Did peak memory improve but allocation churn get worse?

Did imports become faster while startup RSS increased?

Did a stdlib optimization improve pyperformance but regress a real
framework workload?

Did a speedup merely move work into native code while materially
increasing heap allocation?

Can a candidate beat CPython upstream without using more memory?
```

A timing improvement accompanied by a material memory regression is **not a win**.

Memory parity or improvement versus the designated upstream baseline is a first-class requirement.

## Core design principle: three separate passes

Never try to collect all metrics in one execution.

Instrumentation changes program behavior.

Every benchmark workload should conceptually support three independent modes:

```text
timing
memory
allocations
```

### Timing pass

Minimal instrumentation.

Measure real wall-clock/throughput/latency using pyperf-quality methodology.

No:

* Memray;
* tracemalloc;
* RSS polling threads;
* malloc tracing;
* perf recording.

### Memory pass

Run the same semantic workload separately.

Measure:

* peak PSS;
* peak RSS;
* peak private/USS-like memory;
* steady-state memory where applicable;
* process count;
* optional cgroup peak.

Do not use these runs for timing conclusions.

### Allocation pass

Run a reduced but semantically identical workload under Memray.

Measure:

* total allocations;
* total allocated bytes;
* heap high-water mark;
* allocator distribution;
* native allocation origins;
* Python allocator activity;
* allocations per operation;
* allocated bytes per operation.

These runs are diagnostic/resource measurements only.

Never compare their elapsed time with normal timing runs.

## Existing benchmark suite problems to fix

The current suite has several structural limitations.

It currently:

* hardcodes the CPython 3.14.6 musl/PBS comparison;
* treats timing geometric mean as the central verdict;
* has no first-class memory gate;
* does not track process-tree memory;
* does not track allocation count/bytes;
* does not contain a first-class repository-owned realistic macro suite;
* allows some pyperformance payload dependency resolution at runtime;
* assumes benchmark environment behavior that is awkward for this project because the shipped product intentionally excludes `pip` and `venv`;
* hardcodes CPU topology assumptions that happened to fit one host;
* bakes the PBS reference into the benchmark image;
* cannot cleanly compare arbitrary baseline/candidate interpreters.

Fix these rather than layering more shell scripts around them.

## Scope for this task

Fully support:

```text
Linux amd64
```

first.

The current important product path is:

```text
x86_64-unknown-linux-musl
```

and the existing pinned Alpine benchmark container is a reasonable environment for it.

Do not implement macOS benchmarking in this task.

Do not modify the frozen Linux build implementation just to help benchmarking.

Benchmarking should consume built artifacts; it should not change how they are built.

## Proposed layout

Keep all benchmark-specific machinery under `benchmarks/`.

A reasonable shape is:

```text
benchmarks/
    README.md
    bench.py
    Dockerfile
    inputs.lock.json

    harness/
        __init__.py
        models.py
        runner.py
        environment.py
        process.py
        memory.py
        statistics.py
        report.py
        pyperformance.py

    workloads/
        __init__.py
        registry.py
        django_app/
        compileall_app.py
        imports.py
        pip_install.py
        pylint_app.py
        pycparser_app.py
        ...

    vendor/
    results/

    tests/
```

Do not follow this mechanically if the existing code suggests a simpler clean layout.

Prefer fewer files when they remain understandable.

Avoid:

* YAML;
* plugin frameworks;
* dependency injection;
* class hierarchies for three functions;
* generalized workflow engines;
* a database;
* benchmark bookkeeping ceremony.

A small typed stdlib Python controller is preferable.

## CLI

Replace the current collection of entry points with one obvious controller.

Something approximately like:

```text
python3 benchmarks/bench.py doctor

python3 benchmarks/bench.py fetch

python3 benchmarks/bench.py run \
    --baseline <baseline descriptor/path> \
    --candidate <candidate descriptor/path> \
    --suite smoke

python3 benchmarks/bench.py run \
    --baseline ... \
    --candidate ... \
    --suite pyperformance

python3 benchmarks/bench.py run \
    --baseline ... \
    --candidate ... \
    --suite realworld

python3 benchmarks/bench.py run \
    --baseline ... \
    --candidate ... \
    --suite full

python3 benchmarks/bench.py compare <result-directory>
```

The exact CLI can differ if there is a substantially cleaner design.

Keep presets useful.

The existing:

```text
ours vs pinned PBS 3.14.6 musl
```

comparison should remain easy, but it should become a preset layered over the generic harness rather than defining the harness.

If cheap, preserve `run_benchmarks.sh` as a compatibility wrapper around the new controller. Do not maintain two implementations.

## Interpreter model

The benchmark engine must have explicit concepts of:

```text
baseline
candidate
```

with metadata such as:

```text
label
python executable
artifact/source identity
Python version
implementation
ABI
build flags
compiler
platform
```

Do not silently call PBS “upstream”.

These are distinct potential baselines:

```text
CPython upstream
Astral PBS
previous python-build artifact
self-comparison control
```

Reports must name exactly what they compare.

Default serious comparisons should require baseline and candidate to have the same:

```text
CPython major.minor
```

and ideally the same micro/source lineage when testing build quality.

Allow cross-version research only through an explicit override and label those results accordingly.

## Product constraint: do not require pip or venv in the tested Python

The distributed python-build interpreter deliberately does not ship:

```text
pip
ensurepip
venv
```

The benchmark harness must respect that.

Do not change the product scope merely so benchmarks are easier to provision.

Do not test a different Python installation than the product.

### Benchmark dependency provisioning

Create benchmark environments externally.

A good strategy is:

1. use a controller/bootstrap Python to fetch packages;
2. lock every benchmark input by exact version and hash;
3. construct benchmark-only `site-packages` prefixes;
4. invoke the tested interpreter with those prefixes;
5. never install anything into the tested Python distribution.

A pinned pip wheel can be used as a benchmark bootstrap tool without becoming part of the product.

For example, it is acceptable for the harness to arrange something equivalent to:

```text
PYTHONPATH=<pinned pip wheel>
<tested-python> -m pip \
    --isolated \
    --no-index \
    --find-links <wheelhouse> \
    --target <benchmark-site-packages> \
    ...
```

provided this is verified to work cleanly and does not mutate the interpreter.

An even cleaner approach for pyperformance is worth investigating:

* provision each benchmark's dependency set into an external flat prefix;
* invoke the benchmark's own `run_benchmark.py` directly using the tested Python;
* let its `pyperf.Runner` perform measurement;
* avoid pyperformance's normal environment creation machinery entirely.

This has a major advantage: it does not require `venv`.

Do not fork pyperformance benchmark implementations unnecessarily.

## Reproducibility and network policy

The actual benchmark run must be completely offline.

Split:

```text
fetch/prepare phase: network allowed
run phase: network denied
```

Pin benchmark inputs.

Create a benchmark lock containing at least:

```text
name
version
URL/source
SHA-256
size
license if relevant
purpose/workload
```

For wheel dependencies also record:

```text
filename
wheel tags
SHA-256
```

Resolve transitive dependencies during preparation and freeze them.

Do not allow:

```text
pip install <floating name>
```

during measurement.

For pyperformance, its benchmark requirements are a useful starting point but transitive dependency versions must not float unnoticed.

Populate a complete offline wheelhouse before measurement.

Where practical, run the actual benchmark container with:

```text
--network none
```

Fail if something attempts to fetch the network.

## Keep pyperformance, but demote it from “the answer” to one benchmark layer

Use current pinned pyperformance 1.14.0 unless research during implementation discovers a compelling compatibility reason to change it.

It remains the standardized interpreter suite.

It is valuable because it already contains substantial workloads such as:

```text
FastAPI HTTP serving
Django templates
Sphinx
SQLAlchemy
Dask
SymPy
NetworkX
SQLGlot
xDSL
Tornado HTTP
Chameleon
Docutils
Dulwich
pathlib
JSON
pickle
regex
TOML
XML
YAML
startup
```

The recent FastAPI benchmark is particularly useful because it runs a real FastAPI/Uvicorn endpoint including:

* HTTP;
* path parameter extraction;
* Pydantic validation;
* JSON serialization;
* concurrent clients.

Keep the full pyperformance suite available.

Also expose useful report groupings:

```text
apps
startup/import
stdlib
numeric
async/network
parsing/serialization
```

Do not let one whole-suite geomean hide category-specific regressions.

### Pyperformance timing

Continue to use rigorous pyperf execution.

Preserve individual run values.

Use pyperf's statistical comparison/significance machinery where appropriate instead of replacing it with naive arithmetic.

### Pyperformance memory

Run pyperformance again, separately, using its Linux memory tracking mode.

Extract:

```text
mem_max_rss
command_max_rss
```

as appropriate.

This is useful and is what Faster CPython's benchmark infrastructure already consumes.

However, pyperf max RSS is **not sufficient** for the new macro workloads, particularly multiprocess servers. Use the process-tree memory collector described later.

## Build a repository-owned realistic macro suite

Create a default `realworld` suite of approximately 10–15 workloads.

Do not turn it into 100 tiny microbenchmarks.

Each workload should exercise a meaningful application operation and have an obvious operation count so memory/allocation results can be normalized.

The initial suite should cover at least:

```text
web framework
ORM/database object materialization
template rendering
source analysis
parser/compiler work
packaging/install
startup/imports
serialization/protocol work
multi-process or server behavior
```

The exact final set should be justified in `benchmarks/README.md`.

## Tier 1: realistic Django workload

This is mandatory.

Do not merely add another `Template.render()` microbenchmark; pyperformance already has one.

Research and borrow methodology from the actively maintained:

```text
django/django-asv
```

benchmark suite.

At research time it contained real benchmarks for:

* WSGI request handling;
* ASGI request handling;
* default middleware;
* URL resolving/reversing;
* templates;
* forms;
* model creation;
* bulk create;
* ORM filtering;
* `select_related`;
* `prefetch_related`;
* aggregation;
* values/values_list;
* 10,000-row materialization;
* system checks.

Use these as evidence for workload design.

Do not needlessly embed ASV itself into python-build.

Own a small deterministic Django benchmark application.

### Pin Django

Use a modern stable Django release that supports the product's Python version and lock its exact wheel plus dependencies.

At the research date Django 6.1.x is the current stable family, but validate compatibility with CPython 3.14 and pin an exact version rather than blindly following latest.

### Django app shape

Create a compact realistic application with, for example:

```text
Author
Post
Comment
Tag
```

and deterministic seeded data.

A realistic request should include:

```text
middleware
URL resolution
request object creation
ORM lookup/filtering
select_related/prefetch_related
Python model object creation
template rendering or JsonResponse
escaping/string formatting
response construction
```

Verify response correctness with a deterministic digest or invariant so the benchmark cannot accidentally optimize itself into doing less work.

Use SQLite for deterministic local operation.

Configure it for benchmark stability where sensible, for example:

```text
synchronous = OFF
journal_mode = MEMORY
```

or use an in-memory database where that still exercises the intended ORM path.

The point is measuring Python/framework work rather than storage latency.

### Required Django scenarios

Implement at least these:

```text
django_wsgi_request
django_asgi_request
django_orm_10k
django_template_realistic
```

#### `django_wsgi_request`

Exercise the actual Django WSGI handler including middleware and application routing.

A request should hit an ORM-backed view and produce a meaningful response.

Do not time setup, schema creation, or fixture loading.

#### `django_asgi_request`

Equivalent meaningful ASGI path.

Avoid benchmarking a trivial no-op async function.

Exercise the Django ASGI handler and middleware.

#### `django_orm_10k`

Borrow the spirit of Django ASV's `query_values_10000`.

Prepopulate 10,000 deterministic rows.

Measure materialization or model conversion over them.

This is extremely useful for:

* object allocation;
* dictionary/list creation;
* Unicode;
* integer handling;
* SQLite row conversion;
* GC;
* memory peak.

#### `django_template_realistic`

Render a realistic template with:

* loops;
* nested attributes;
* escaping;
* conditionals;
* dates/numbers;
* URL generation if practical.

Not merely a one-variable template.

### Full HTTP Django mode

If it can be made stable without bloating the implementation, add:

```text
django_http
```

using a real one-worker WSGI or ASGI server and an external client.

Borrow ideas from Pyston's DjangoCMS/Gunicorn/aiohttp macrobenchmarks.

Important:

* server and load generator must use disjoint physical CPUs;
* choose an ephemeral port;
* exclude server startup from steady request timing;
* verify every response;
* record throughput and latency distribution;
* include server startup as a separate metric if useful.

Do not block the whole task on this if the in-process Django request workloads are substantially more stable and representative.

## Tier 1: Python source/tooling workloads

### `pylint`

Add a realistic pylint run over a pinned Python source corpus.

Good inputs include a stable sizeable pure-Python package or checked-in deterministic source fixture.

Measure a real lint pass, not parsing one tiny file.

Suppress output without disabling work.

This exercises:

* AST;
* imports;
* inspect;
* typing-ish metadata;
* collections;
* strings;
* dictionaries;
* graph traversal;
* GC.

The old Pyston macrobenchmark is useful prior art but should not be copied blindly because it is stale.

Use a modern pinned pylint.

### `pycparser`

Add a pycparser workload over several sizeable preprocessed C files.

Preload input bytes outside the timed region if the benchmark is intended to measure parsing rather than disk I/O.

This is an excellent Python-heavy parser/object-allocation workload.

### `compileall`

Add:

```text
compileall_django
```

or an equivalent large pure-Python corpus.

Benchmark CPython parsing/AST/compiler/bytecode production over a realistic package tree.

Use a fresh deterministic output destination each run.

Do not accidentally measure stale `.pyc` reuse.

This is an especially valuable complement to startup/import benchmarking.

## Tier 1: packaging workload

Add a realistic offline package installation benchmark.

Something equivalent to:

```text
pip_install_wheelhouse
```

Use a pinned pip bootstrap and a locked wheelhouse.

Install a representative collection of primarily pure-Python packages into a fresh target directory.

Candidate packages should collectively exercise:

```text
zipfile
zlib
hashing
pathlib
shutil
importlib.metadata
email metadata parsing
record parsing
filesystem creation
bytecode compilation
```

A Django stack is a natural part of this corpus.

Avoid making the result mostly a benchmark of large native wheel extraction.

No network.

Time the actual install operation into a clean directory.

Also collect its process-tree memory and allocation profile in the other passes.

Because pip is a benchmark payload only, do not add it back to the shipped Python.

## Tier 1: startup and imports

Fresh-process startup is a major practical dimension that pyperformance geomeans can obscure.

Include at least:

```text
python_startup
import_django
import_app_stack
```

Potential representative app stack:

```text
Django
FastAPI/Pydantic
SQLAlchemy
```

if version compatibility remains clean.

Measure a fresh process each iteration.

Record both:

```text
time
peak memory
```

For import workloads distinguish intentionally between:

```text
precompiled bytecode case
source compilation case
```

Do not let random first-run `.pyc` creation contaminate measurements.

A good default is:

* benchmark dependencies precompiled before timed imports;
* bytecode tree read-only during the benchmark;
* use `compileall` as the separate source-compilation workload.

## Other useful realistic workloads

Select enough to create coverage without bloating the suite.

Good candidates include:

### Sphinx

Already in pyperformance and reasonably realistic.

Keep it and surface it prominently as an application workload.

### FastAPI

Already present in current pyperformance.

Do not duplicate it unless adding a clearly different full-server/process measurement.

### SQLAlchemy

Already present in pyperformance.

Use its existing ORM workloads as part of the application category.

### Thrift or another protocol workload

The old Pyston Thrift benchmark is a good workload shape:

```text
construct Python object graph
serialize
deserialize
repeat
```

Use it only if a modern dependency set remains clean.

### mypy

Potentially excellent real Python tooling workload.

Be careful: contemporary mypy may use compiled components depending on distribution/build mode.

If the chosen distribution ceases to be primarily interpreter-sensitive, either force an appropriate pure-Python build or omit it.

Do not claim a workload is Python-heavy if most measured work actually moved to an unrelated native extension.

## Workload registry

Create one small explicit registry.

Each workload should declare enough metadata to avoid special cases spread around the runner, for example:

```text
name
category
command/driver
operations per iteration
timing rounds
warmups
memory rounds
supports allocation profiling
process model
expected outputs
required packages
```

This can be a frozen dataclass or simple dict structure.

Do not build a plugin system.

## Timing methodology

Timing must be rigorous but practical.

### Physical CPU topology

Do not retain assumptions like:

```text
CPU i and i+16 are SMT siblings
```

Discover topology from Linux sysfs, including:

```text
/sys/devices/system/cpu/cpu*/topology/thread_siblings_list
core_id
physical_package_id
```

and NUMA information where available.

Choose physical cores explicitly.

For paired simultaneous execution, baseline and candidate must get comparable core placement across sockets/CCDs/NUMA nodes.

For serious verdicts, prefer sequential paired execution unless simultaneous execution has a demonstrated noise advantage.

### Paired order

Thermal/frequency drift can create systematic bias.

Use alternating/paired ordering such as:

```text
baseline
candidate
candidate
baseline
```

across rounds.

Do not always run baseline first.

### Core pinning

For single-process CPU-heavy macro workloads:

```text
one dedicated physical core
```

is usually preferable.

For servers:

```text
server core(s)
client/load-generator core(s)
```

must be disjoint.

### Host metadata

Record:

```text
CPU model
logical CPU count
physical core topology
NUMA topology
kernel version
container runtime/version
CPU governor
turbo/boost state where detectable
microcode version where available
load average
memory size
swap state
```

Do not require privileged tuning.

If the host is noisy or frequency policy is unsuitable, warn in provenance instead of mutating the machine without permission.

### Rounds

Macro workloads should generally execute as multiple fresh-process rounds.

Use enough rounds to characterize noise; approximately 5–10 is a sensible starting range depending on workload cost.

Do not pretend a single 30-second run is statistically rigorous merely because it is long.

### Statistics

For macros report at least:

```text
median
mean
minimum
maximum
standard deviation
coefficient of variation
MAD
paired candidate/baseline ratios
```

Add a confidence interval for the paired ratio using a simple reproducible bootstrap or another justified paired estimator if practical.

Do not add numpy/scipy just for statistics.

Stdlib Python is sufficient.

Do not hide all macros behind one global geometric mean.

Category aggregates are useful; individual workload results are authoritative.

## Resident memory methodology

This is a mandatory part of the harness.

### Important distinction

Track separately:

```text
RSS
PSS
private/USS-like memory
```

RSS alone is inadequate for multiprocess applications because shared library/interpreter pages get counted once per process.

For process trees, **PSS should be the primary resident-memory comparison**.

### `/proc/<pid>/smaps_rollup`

On Linux, build a small external process-tree memory sampler using `/proc`.

Parse at least:

```text
Rss
Pss
Private_Clean
Private_Dirty
Private_Hugetlb
Shared_Clean
Shared_Dirty
Swap
```

Compute a USS-like private total from the private fields.

Discover process descendants externally.

Do not rely on the target Python to inspect itself.

A pinned controller-side psutil is acceptable, but using `/proc` directly is simple and removes another variable.

Poll at approximately:

```text
10–20 ms
```

for memory passes.

The exact interval should be configurable and recorded.

Do not use this sampler during timing passes.

### Process-tree metrics

For every macro workload record:

```text
peak total PSS
peak total RSS
peak total private memory
peak process count
PSS/RSS timeline or enough raw samples to reconstruct it
```

For long-lived/server workloads also capture:

```text
startup/idle PSS
steady-state PSS before load
peak PSS under load
steady-state PSS after load
post-GC/settled PSS if meaningful
```

For repeated batches, record memory growth.

A server that begins at 100 MiB and grows 20 MiB every batch is a regression even if one short request run looks fine.

### cgroup v2

If the environment provides a writable/delegated cgroup v2 subtree, additionally use:

```text
memory.current
memory.peak
memory.events
```

for the isolated workload cgroup.

This is a useful whole-workload measurement because it includes descendants and kernel-accounted memory.

But treat it as a secondary metric because:

* delegation may not be available;
* it includes page cache and some kernel/socket memory;
* its semantics are not the same as process PSS.

Detect support.

Do not require root.

### Page cache

Do not require:

```text
echo 3 > /proc/sys/vm/drop_caches
```

or root.

Real applications commonly run with a warm page cache anyway.

Keep cache state consistent through warmup/order and record the policy.

## Allocation methodology: Memray

Use Memray for dedicated allocation passes.

At the research date current Memray is 1.20.0 and it supports CPython 3.14 plus musllinux x86_64 wheels.

Pin the exact compatible version and hash used by this repository.

Memray is particularly valuable here because it can observe:

```text
system/native allocations
native extension allocations
interpreter allocations
individual Python allocator requests
```

### Allocation profile flags

For the detailed allocation pass use:

```text
--native
--trace-python-allocators
```

where supported.

Memray itself warns that tracing Python allocators substantially increases runtime and capture volume.

That is why this is a separate pass.

### Extract machine-readable data

Use Memray's JSON statistics rather than scraping terminal output.

Record at least:

```text
total_num_allocations
total_bytes_allocated
metadata.peak_memory
allocator_type_distribution
top allocations by bytes
top allocations by count
top allocating modules
```

Normalize where applicable:

```text
allocations / operation
bytes allocated / operation
```

For HTTP:

```text
allocations / request
bytes allocated / request
```

For ORM:

```text
allocations / row
bytes allocated / row
```

For import:

```text
allocations / import process
```

### Native stacks

Keep native allocation information because future CPython changes may move work between:

```text
Python
CPython C
third-party C
other native code
```

The resource result matters regardless of implementation language.

### Multiprocess allocation profiling

Memray supports following forks, but keep complexity under control.

For pre-fork server workloads either:

* use Memray follow-fork and aggregate child reports carefully; or
* use an equivalent single-process semantic workload for detailed allocator attribution and rely on PSS for the real multiprocess case.

Do not create misleading aggregate numbers.

## Memory/resource acceptance policy

Implement explicit pass/fail logic.

This is not merely an informational chart.

### Baseline

The strict memory guarantee applies to a baseline explicitly labeled as:

```text
upstream CPython
```

and built/configured comparably.

PBS comparisons remain useful, but are PBS comparisons.

Do not label them upstream.

The harness should not implement a second CPython build system just to manufacture a baseline.

Accept a supplied baseline interpreter/artifact.

### Noise-aware parity

“Equal or better” cannot mean byte-for-byte equality of RSS; ASLR, allocator layout, kernel behavior and sampling introduce noise.

Determine memory repeatability from repeated baseline runs.

For each metric derive a practical noise allowance from something such as:

```text
baseline MAD / repeat spread
+
small absolute page-scale floor
```

Keep this policy simple and transparent.

Do not use a giant arbitrary tolerance like 10%.

### Tier-1 memory gate

For every primary real-world workload:

```text
candidate peak PSS must not show a material regression
```

against upstream.

Also gate applicable:

```text
steady-state PSS
post-load PSS
memory growth
```

A workload failing its memory gate cannot be rescued by improvements elsewhere.

Do not average away a 15% Django memory regression because ten tiny benchmarks improved.

### Overall memory summary

In addition to per-workload gating, report category-level and overall geometric/median ratios.

Overall resident memory should be at parity or better.

But the per-workload gate remains authoritative.

### Allocation gate

Allocation metrics should receive their own verdict.

At minimum:

* any clear increase in allocated bytes/op must be highlighted;
* any clear increase in allocation count/op must be highlighted;
* large regressions should fail the resource verdict unless specifically waived.

Do not choose a broad hardcoded tolerance without measuring Memray repeatability first.

Keep resident-memory failure separate from allocation-churn failure so the report explains *why* the resource verdict failed.

## Startup memory

Explicitly measure the cost of a nearly empty interpreter.

Examples:

```text
python -c pass
python -S -c pass
```

where meaningful.

Record:

```text
startup wall time
peak PSS/RSS
```

This is important because adding native runtimes, larger static tables, new shared libraries, or eager imports can increase baseline cost even if application hot loops get faster.

The benchmark harness should catch such regressions regardless of their origin.

## Installed/binary size

Add secondary size metrics.

Record for each candidate/baseline:

```text
total installed bytes
interpreter executable size
libpython size
extension-module total size
stdlib source size
```

Do not make these part of the initial hard memory verdict.

They are useful diagnostics for code-size growth and mapped-page changes.

## Optional `perf stat` diagnostics

If Linux perf events are available without privilege changes, support an optional diagnostics mode.

Useful counters include:

```text
task-clock
cycles
instructions
branches
branch-misses
cache-references
cache-misses
page-faults
minor-faults
major-faults
context-switches
cpu-migrations
```

Record:

```text
instructions/op
cycles/op
IPC
cache misses/op
faults/op
```

Do not require this mode for normal benchmark completion because:

```text
perf_event_paranoid
virtualization
container permissions
```

may prohibit it.

Never alter host security settings automatically.

## Result layout

Every run should be self-contained.

For example:

```text
benchmarks/results/<timestamp>/
    provenance.json
    summary.json
    summary.md

    pyperformance/
        baseline-timing.json
        candidate-timing.json
        baseline-memory.json
        candidate-memory.json

    realworld/
        django_wsgi_request/
            timing.json
            memory.json
            allocations.json
            raw/
        django_asgi_request/
        django_orm_10k/
        ...

    logs/
```

Raw Memray binary captures can be large.

Keep them if requested or for failed/regressed workloads; it is acceptable to discard successful raw captures after extracting stable JSON statistics if that policy is explicit.

Do not put giant captures under git.

## Result schema

Use one common workload result representation.

Each workload should expose, where applicable:

```text
identity:
    workload
    category
    operation
    operation_count
    dependency versions/hashes

timing:
    rounds
    raw samples
    median
    mean
    stdev
    MAD
    throughput
    latency percentiles

memory:
    peak_pss
    peak_rss
    peak_private
    steady_pss
    postload_pss
    memory_growth
    cgroup_peak
    raw sample path

allocations:
    total_allocations
    total_bytes_allocated
    heap_peak
    allocations_per_operation
    bytes_per_operation
    allocator distribution

comparison:
    time_ratio
    memory ratios
    allocation ratios
    noise estimates

verdict:
    timing
    memory
    allocations
    overall
    reasons
```

Not every workload needs every field.

Use `null`/absence honestly.

Do not invent zeroes for unavailable measurements.

## Report

Generate both:

```text
summary.json
summary.md
```

The Markdown report should start with an executive table similar to:

```text
Workload             time       peak PSS    alloc bytes/op   verdict
django_wsgi_request  -7.2%      -1.3%       -4.5%            PASS
django_orm_10k       -3.1%      +8.7%       +6.1%            FAIL memory
import_django        -5.4%      +0.2%       -0.8%            PASS
...
```

Then report category summaries.

Timing direction must be obvious.

Memory direction must be obvious.

Do not use ambiguous ratios without labels.

A user should be able to tell in seconds:

```text
what got faster
what got slower
what got bigger
what allocates more
what actually failed
```

## Benchmark provenance

Record enough context to reproduce or reject a result.

At minimum:

```text
git commit of python-build
baseline identity
candidate identity
Python versions
sysconfig build flags
compiler identities
artifact SHA-256s
benchmark lock SHA-256
Docker image digest
kernel
CPU model
topology
governor
boost state
host memory
swap
container runtime
CPU affinity
run ordering
benchmark package versions
pyperformance version
pyperf version
Memray version
memory sampling interval
perf availability
timestamp
```

Record environment variables that materially affect Python:

```text
PYTHONHASHSEED
PYTHONMALLOC
PYTHONPATH
PYTHONNOUSERSITE
PYTHONDONTWRITEBYTECODE
```

Use fixed `PYTHONHASHSEED` for paired deterministic macro runs unless the workload specifically tests hash randomization.

## Fairness

Baseline and candidate must use byte-identical:

```text
benchmark source
benchmark dependency files
datasets
database fixture
wheelhouse
environment
container userland
```

Only the interpreter/distribution under test should differ.

Do not allow candidate-specific benchmark dependency builds.

Where native benchmark dependency wheels are used, document them because they can dilute interpreter sensitivity.

Prefer pure-Python dependencies for custom macro workloads where practical.

## Parallel benchmark execution

The current high-throughput sharded mode is useful for iteration.

Keep an accelerated mode.

However, a **published/acceptance verdict** should default to the strongest isolation mode, not maximum machine saturation.

Shared:

```text
L3
memory bandwidth
thermal budget
power budget
NUMA fabric
```

can couple supposedly isolated cores.

Provide at least:

```text
quick
standard
rigorous
```

or equivalent profiles.

A good conceptual split is:

### `quick`

Small pyperformance subset + short macros.

Developer iteration only.

### `standard`

Full real-world suite + selected pyperformance apps, multiple rounds, full memory gates.

Useful for ordinary development.

### `rigorous`

Full pyperformance + full macros + repeated timing + repeated memory + allocation profiling.

Acceptance/publication quality.

## Workload noise classification

Some workloads are inherently noisier.

Track their repeatability.

A workload that cannot self-compare reliably should not silently participate in hard aggregate gates.

Classify it explicitly as:

```text
stable
noisy
diagnostic-only
```

Do not solve flaky benchmarks by simply widening all tolerances.

Fix the workload or remove it from the hard verdict.

This is especially relevant to:

```text
loopback TCP
async scheduling
multiprocessing
fixed-port legacy benchmarks
```

## Self-comparison calibration

This is mandatory.

The harness needs a control command or mode that runs:

```text
same interpreter
vs
same interpreter
```

through the exact normal machinery.

Use it to characterize:

```text
timing noise
memory noise
allocation measurement repeatability
```

The self-comparison should not show systematic wins/losses.

Use its measured variation when selecting default resource thresholds.

This is much more defensible than inventing tolerances.

## Benchmark correctness

Every macro benchmark must validate its result.

Examples:

```text
Django: response digest/status/query result
pycparser: AST count/digest
pylint: known message/count digest
compileall: expected compiled file count/hash
pip: installed RECORD/package inventory
serialization: decoded object equality
```

Do not allow an optimization/regression to accidentally skip work while reporting a speedup.

Correctness verification should occur outside or minimally inside the timed region, depending on what best preserves workload semantics.

## Process cleanup

Server/process benchmarks must be robust.

Use:

```text
process groups
timeouts
SIGTERM then SIGKILL fallback
ephemeral ports
temporary directories
```

No orphan workers.

No fixed ports shared across benchmark shards.

After every workload verify the process tree is gone.

## Dataset policy

Small benchmark source fixtures may live in the repo.

Large corpora must be locked external inputs.

Every external corpus requires:

```text
URL/repository
commit/version
hash
license
purpose
```

Do not benchmark against the current working tree as an uncontrolled mutable corpus.

## Benchmark image

Refactor `benchmarks/Dockerfile` into a generic benchmark environment.

Do not bake one baseline interpreter into the image.

The same image should be able to receive:

```text
baseline artifact
candidate artifact
wheelhouse
benchmark inputs
```

at runtime.

Keep Alpine/musl support for the existing product comparison.

Make the container fail closed on the wrong architecture.

Actual measurement should use the same container bytes for both sides.

## Existing PBS comparison

Preserve it as a useful preset.

For example:

```text
python3 benchmarks/bench.py run --preset pbs
```

can resolve:

```text
baseline = sources.lock.json reference-pbs
candidate = current x86_64 musl dist artifact
```

But its output should now include:

```text
timing
pyperformance memory
real-world macros
resource metrics
```

where compatible.

It must say:

```text
baseline: Astral PBS 20260610
```

not:

```text
baseline: upstream
```

## Upstream CPython comparison

Design the generic interface so I can later provide a matching upstream CPython executable or artifact and request:

```text
baseline = upstream CPython
candidate = python-build
```

without modifying benchmark code.

Do not implement a whole upstream build pipeline in this task.

If a compatible upstream Python executable is available on the host, it is useful to perform one validation comparison during development.

## Research references to inspect during implementation

Read these projects before finalizing the design.

### `python/pyperformance`

Current standardized CPython benchmark suite.

Important current workloads include FastAPI, Sphinx, Django templates, SQLAlchemy, Dask, SymPy, NetworkX, SQLGlot and xDSL.

Use its benchmark implementations rather than rewriting identical ones.

### `psf/pyperf`

Study:

```text
--track-memory
mem_max_rss
command_max_rss
affinity
benchmark JSON
compare_to
significance calculations
```

Do not replace mature pyperf methodology gratuitously.

### `faster-cpython/bench_runner`

Study its handling of:

```text
timing comparisons
memory extraction
mem_max_rss
command_max_rss
significance
benchmark exclusions
longitudinal results
```

Do not vendor the entire project.

Our needs are smaller and include additional process-tree/PSS/application measurements.

### `faster-cpython/benchmarking-public`

Use as evidence for how the CPython performance project publishes timing and memory separately.

### `django/django-asv`

This is one of the most important references for this task.

At research time its active suite included:

```text
model operations
ORM/query operations
10k row materialization
WSGI/ASGI request handling
middleware
forms
templates
URLs
system checks
```

Reuse workload *ideas and semantics*.

Do not import ASV as the central python-build benchmark engine.

### `pyston/python-macrobenchmarks`

Useful historical macro workload designs:

```text
DjangoCMS
aiohttp
Gunicorn
Flask
mypy
pylint
pycparser
Thrift
Kinto
```

The repository is relatively stale compared with the other sources.

Use it as design prior art, not a dependency to inherit wholesale.

### `bloomberg/memray`

Use for detailed allocator profiling.

Important capabilities:

```text
native allocation stacks
Python allocator tracing
fork following
machine-readable stats
total allocation count
total allocated bytes
heap peak
allocator distribution
```

Respect its warning that detailed allocation tracing has significant overhead.

## Testing the benchmark harness itself

Add focused unit/integration tests.

At minimum test:

### Memory parser

Fixtures for `/proc/<pid>/smaps_rollup`.

Verify:

```text
RSS
PSS
private total
swap
```

calculations.

### Process tree

Spawn a known parent + children and verify descendants are accounted for and disappear cleanly.

### Memory peak

Create a child that allocates a known substantial buffer, holds it, then releases it.

Verify the sampler observes the expected direction/magnitude.

Do not assert absurd byte-perfect values.

### Statistics

Test:

```text
median
MAD
stdev
CV
paired ratios
noise threshold
verdict
```

on deterministic synthetic inputs.

### Result schema

Round-trip result JSON.

Reject malformed/incompatible results explicitly.

### Dependency lock

Corrupted or wrong SHA-256 inputs must fail.

### Offline guarantee

At least one integration smoke should run the prepared benchmark environment with networking unavailable.

### No target venv/pip assumption

A fixture/interpreter simulation should prove benchmark provisioning does not rely on:

```text
python -m venv
python -m pip
```

being available from the tested distribution's installed stdlib.

### Self comparison

Run a cheap real self-comparison.

It should produce a passing resource/timing verdict.

### Existing suite regression

Keep existing unit tests green.

If old benchmark utility tests are replaced, update them rather than carrying redundant obsolete code.

## Performance of the harness

Do not over-optimize benchmark setup.

Correctness and reproducibility matter more.

But keep iteration practical:

```text
quick    minutes
standard manageable development run
rigorous intentionally expensive
```

Avoid requiring a multi-hour full pyperformance run just to test one Django change.

Allow workload/category selection:

```text
--workload django_wsgi_request
--category web
```

or equivalent.

## README rewrite

Rewrite `benchmarks/README.md` around the new conceptual model.

It should explain:

1. what the benchmark system measures;
2. why timing/memory/allocation runs are separate;
3. how to fetch inputs;
4. how to run quick/standard/rigorous;
5. how to compare arbitrary interpreters;
6. how PBS preset works;
7. how upstream CPython should be supplied;
8. what each default macro workload represents;
9. how memory is measured;
10. how allocation metrics are measured;
11. how verdicts work;
12. benchmark fairness/noise limitations;
13. result/provenance layout.

Delete stale prose describing the old harness as though it were the complete methodology.

## What not to do

Do not:

* change the CPython production build to support benchmarks;
* add pip/venv back into the shipped product;
* require Rust;
* assume future CPython 3.16 work;
* run networked benchmarks;
* measure timing while Memray is enabled;
* use tracemalloc as a substitute for total process memory;
* use RSS alone for multiprocess workload verdicts;
* use a giant global geomean to hide regressions;
* require root;
* disable ASLR globally;
* drop kernel caches;
* mutate CPU governor automatically;
* install packages globally on the host;
* blindly vendor Pyston's old suite;
* implement a second copy of pyperf;
* add a giant benchmark framework.

## Recommended implementation order

Proceed approximately in this order:

1. Understand and preserve the useful pieces of the existing suite.
2. Create generic baseline/candidate model and result schema.
3. Generalize benchmark image so baseline is no longer baked in.
4. Implement locked offline dependency preparation without requiring target pip/venv.
5. Implement topology discovery and robust CPU assignment.
6. Integrate current pyperformance timing through the new runner.
7. Add separate pyperformance memory pass.
8. Implement `/proc` process-tree PSS/RSS/private sampler.
9. Implement Django macro application and required scenarios.
10. Add source/tooling/startup/packaging macros.
11. Integrate Memray allocation runs.
12. Implement comparison/noise/resource verdicts.
13. Add self-comparison calibration.
14. Add optional perf-stat diagnostics.
15. Rewrite reporting and README.
16. Run actual baseline/candidate smoke and self-comparison.
17. Inspect the complete diff and delete obsolete duplicate machinery.

Do not stop after infrastructure if no real macro workload has actually been run.

## Acceptance criteria

The work is complete only when all of the following are true:

1. Existing production build behavior is unchanged.
2. No Rust-for-CPython work is assumed or added.
3. The harness works from current `main` on native Linux amd64.
4. Existing x86_64 musl artifacts can be benchmarked.
5. PBS remains available as a named baseline preset.
6. Arbitrary baseline/candidate interpreter identity is modeled generically.
7. Benchmark runs require no target `pip`, `ensurepip`, or `venv`.
8. Runtime benchmark execution is offline.
9. Benchmark dependencies are reproducibly locked.
10. Full pyperformance timing remains available.
11. Pyperformance memory is collected in a separate pass.
12. A repository-owned real-world suite exists.
13. It includes meaningful Django WSGI, ASGI, ORM-10k and template workloads.
14. It includes realistic source/tooling work.
15. It includes startup/import measurements.
16. It includes an offline package-install workload.
17. Macro timing uses multiple paired runs.
18. CPU topology is discovered rather than hardcoded.
19. Process-tree peak PSS, RSS and private memory are recorded.
20. Applicable steady/post-load memory is recorded.
21. Memray records allocation counts and bytes in a separate pass.
22. Allocation metrics are normalized per operation where meaningful.
23. Resource regressions receive an explicit verdict.
24. A timing speedup cannot override a failed memory gate.
25. Reports never mislabel PBS as upstream CPython.
26. A self-comparison mode validates benchmark noise.
27. Every macro benchmark validates correctness.
28. No orphan server/worker processes remain after runs.
29. `summary.json` contains all machine-readable metrics.
30. `summary.md` gives an immediately actionable human report.
31. Provenance is sufficient to reproduce or reject a result.
32. Harness tests pass.
33. Existing repository tests remain green.
34. At least one complete smoke comparison has been executed on the Linux amd64 development host.
35. The final implementation is materially simpler to understand than the current collection of benchmark shell scripts.

## Final standard

The finished benchmark harness should make it difficult to fool ourselves.

A future optimization should not be able to earn a “faster” headline because:

* it only improved microbenchmarks;
* a framework got slower;
* startup got worse;
* peak memory grew;
* worker PSS grew;
* allocation churn exploded;
* a benchmark silently performed less work;
* dependency versions changed;
* a load generator became the bottleneck;
* CPU placement favored one side;
* baseline always ran cold and candidate warm;
* the comparison was actually PBS rather than upstream;
* instrumentation contaminated the timing result.

The benchmark system is part of the correctness discipline of `python-build`, not a demo.

Implement it accordingly.
