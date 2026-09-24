# Objective

Replace the current narrow "pyperformance ours vs PBS" benchmark setup with a genuinely useful CPython qualification harness that answers four separate questions:

1. **How fast is this Python on realistic Python-heavy workloads?**
2. **How much actual process memory does it consume while doing them?**
3. **How much allocator churn does it create, including native/interpreter allocations?**
4. **If something changes, where did the CPU or memory behavior move?**

Performance improvement is not sufficient by itself.

The project-level invariant is:

```text
candidate memory use should be equal to or lower than
a comparable upstream CPython baseline
```

Small measurement noise can be classified separately, but do not hide a memory regression inside a global average or trade "10% faster for 20% more RAM" without making that regression explicit.

The benchmark harness must work with both:

* the existing CPython 3.14.6 product builds;
* future builds, including the isolated Rust-for-CPython 3.16 experiment.

The harness must **not** itself know or care whether the candidate contains Rust.

It benchmarks Python interpreters.

# Current state and shortcomings

At the research snapshot, `benchmarks/` contains approximately:

```text
benchmarks/
    Dockerfile
    README.md
    compare.py
    pool.py
    run_benchmarks.sh
    run_parallel.sh
    run_single.sh
    run_suite.sh
    shard.py
    vendor/
    results/
```

The current setup:

* is hardcoded around CPython 3.14.6;
* is hardcoded around x86-64 musl;
* compares mainly against Astral PBS;
* runs pyperformance 1.14.0;
* computes a timing geomean;
* has no first-class memory regression contract;
* has no allocation accounting;
* does not run genuinely rich application workloads such as a realistic Django request/ORM/template path;
* allows pyperformance payload dependencies to resolve from the package index at benchmark time;
* conflates "distribution parity against PBS" with "runtime performance against upstream CPython."

Retain the useful pieces, especially:

* CPU-affinity awareness;
* sequential authoritative mode;
* deterministic result files;
* pyperformance support;
* existing PBS comparison as a secondary reference;
* the fact that benchmark tool packages are already pinned.

But stop treating the current suite as the authoritative measure of CPython quality.

# Fundamental design: four independent lanes

Do **not** instrument timing runs.

Every benchmarkable workload should conceptually support independent execution under these lanes:

```text
time
memory
alloc
diagnostic
```

They may reuse workload definitions, fixtures and environments, but measurements must be collected in separate processes.

## 1. `time`

This is the authoritative performance measurement.

No:

* Memray;
* tracemalloc;
* allocation hooks;
* process memory polling from inside the candidate;
* pystats;
* profilers;
* debug allocator;
* forced GC.

Use ordinary production-like CPython behavior:

* GC enabled;
* ASLR enabled;
* hash randomization enabled;
* normal allocator;
* ordinary GIL configuration of the candidate.

This follows the philosophy of pyperformance: don't create an artificial interpreter state solely to make a benchmark quieter.

## 2. `memory`

Run the same logical workload separately under an **external** memory observer.

The candidate process must not run the sampler itself.

Track the complete candidate process tree where applicable.

Collect:

```text
rss
uss
pss where available
vms informationally
swap where available
process count
thread count
```

At minimum derive:

```text
startup footprint
post-import/setup footprint
steady-state footprint
peak RSS
peak USS
peak PSS where available
natural retained memory after workload
retained memory after an explicit post-workload gc.collect()
```

The explicit GC measurement is diagnostic only.

Do not insert `gc.collect()` into the workload itself or use post-GC memory as the sole memory result.

Also preserve the raw sampled time series.

## 3. `alloc`

This is a separate, deliberately instrumented run.

Use **Memray** where compatible.

Capture both:

* system allocator/native allocation behavior;
* Python allocator/pymalloc behavior.

A useful default for a deep allocation pass is conceptually:

```text
memray --native --trace-python-allocators
```

but validate actual CLI/version behavior before encoding it.

For each workload report at least:

```text
total allocation count
total bytes allocated
allocation-size distribution
allocator-type distribution
peak live heap where obtainable
retained/live bytes at the high-water mark
top sites by bytes
top sites by allocation count
allocations per normalized work unit
bytes allocated per normalized work unit
```

Keep compressed raw captures only when useful or requested; always keep a compact machine-readable stats summary.

Memray profiling overhead can be substantial, especially with Python allocator tracing and native stack collection.

**Never compare wall-clock timings from Memray runs.**

If Memray does not support an interpreter—quite plausible for development CPython 3.16—report:

```text
alloc_status: unsupported
reason: ...
```

Do not install a different Python or silently fall back to some incomparable allocator profiler.

OS-level memory qualification must still work even if Memray does not.

## 4. `diagnostic`

Optional heavyweight investigation lane.

On Linux, support useful diagnostics such as:

```text
perf stat
perf record
```

when available.

Useful counters include:

```text
cycles
instructions
branches
branch misses
cache misses
page faults
context switches
task-clock
```

Also leave room for:

```text
CPython pystats
native stack profiles
```

These are diagnostic evidence, not timing verdicts.

A pystats-enabled Python is a different build configuration. Never mix pystats timings into normal timing comparisons.

# Generic interpreter model

The new harness should fundamentally accept:

```text
--baseline /absolute/path/to/python
--candidate /absolute/path/to/python
```

Everything else should build on this.

Do not encode assumptions such as:

```text
python3.14
PBS
ours
Rust CPython
```

inside workload machinery.

Convenience wrappers may resolve known project artifacts, but the core harness compares arbitrary same-minor CPython executables.

By default require:

```text
baseline major.minor == candidate major.minor
```

A cross-version comparison should require an explicit exploratory override and must be labelled as such.

# Baseline policy

There are two different reference concepts. Keep them distinct.

## Primary: matched upstream CPython

The authoritative performance/memory baseline should be an upstream CPython build of the same version/line as the candidate, compiled as comparably as practical:

```text
same architecture
same deployment target
same C compiler family/version
same PGO policy
same LTO policy
same GIL mode
same optimization level
same benchmark dependency bytes
```

This is the baseline used for claims like:

> this optimization improves CPython without increasing memory.

For experimental CPython 3.16 work, the baseline should be vanilla upstream CPython 3.16 from the closest appropriate source revision, not Python 3.14 and not PBS 3.14.

The harness does not have to become a giant generic CPython builder. It may accept an explicitly built matched baseline.

However, provenance must clearly describe whether a comparison is:

```text
upstream_matched
distribution_reference
exploratory
```

Only `upstream_matched` is strong enough for the memory regression gate.

## Secondary: distribution references

Keep Astral python-build-standalone comparisons.

They are useful for:

* checking distribution quality;
* comparing compiler choices;
* catching large performance gaps.

They are not the definition of upstream CPython runtime overhead.

Do not merge the upstream and PBS scores.

# Reproducible benchmark dependencies

Benchmark dependency drift is unacceptable.

The current design pins the pyperformance driver stack but lets many benchmark payload packages resolve from the package index during the run.

Fix this.

Add an explicit online preparation phase, approximately:

```text
python3 benchmarks/run.py fetch ...
```

and make actual qualification runs offline.

Use the repository's content-addressed cache infrastructure where it fits.

Pin:

* benchmark source repositories by commit;
* all benchmark package wheels/sdists by version and SHA-256;
* benchmark fixture corpora by digest;
* external helper binaries, if any, by digest.

Build or download one compatible wheelhouse for a baseline/candidate pair.

When baseline and candidate share CPython minor/ABI, use the **same wheel bytes** for both whenever technically possible. This is especially important for dependencies containing C extensions: we do not want "different third-party compiled code" to become an accidental benchmark variable.

The benchmark environment itself is an input and must be fingerprinted.

Do not commit hundreds of megabytes of wheels into Git merely for convenience. Use locked metadata + the existing content-addressed cache.

Actual benchmark execution must fail if it attempts network access.

# Research suites to integrate

Do not throw away pyperformance.

Instead make it one layer of the benchmark system.

## `python/pyperformance`

Keep the pinned pyperformance 1.14.0 suite unless investigation finds a concrete compatibility reason to move.

Current pyperformance already contains useful realistic workloads including, among many others:

```text
FastAPI + Uvicorn + Pydantic HTTP requests
Django template rendering
Sphinx documentation builds
SQLAlchemy declarative ORM
SQLAlchemy imperative ORM
Mercurial startup
Dask
SymPy
NetworkX
SQLGlot
Tornado HTTP
asyncio networking
JSON
pickle
pathlib
logging
regex
TOML
XML ElementTree
startup/import workloads
GC workloads
```

The current FastAPI benchmark is substantially more realistic than a trivial function microbenchmark: it serves a real FastAPI application, validates path parameters, serializes a Pydantic model and exercises HTTP handling.

The Sphinx benchmark is also valuable: it performs an actual Sphinx documentation build while intentionally moving much filesystem input into memory to make the result more Python-heavy and less storage-noise-heavy.

Keep those.

Use pyperformance tags/groups in the report instead of reducing all ~100 results to one number.

## `pyston/python-macrobenchmarks`

Faster CPython's production benchmark infrastructure combines pyperformance with Pyston's macrobenchmark repository.

Research snapshot for Pyston's suite:

```text
pyston/python-macrobenchmarks
commit d2aac54ec18e808afbf8e592302c3819f2e5785a
```

Relevant workloads include:

```text
djangocms
flaskblogging
aiohttp
gunicorn
kinto
mypy2
pycparser
pylint
thrift
```

The existing DjangoCMS benchmark:

* creates an actual Django CMS site;
* performs migrations;
* runs Django's server;
* sends hundreds of HTTP requests;
* exercises templates and basic authentication machinery.

It is useful prior art, although it is not sufficient as our only Django benchmark and its comments themselves acknowledge that the tested route could be richer.

Pin the macrobenchmark source commit rather than following `main`.

Audit each workload's dependencies for current-Python compatibility before including it in the qualification set.

Do not include huge native-compute workloads such as PyTorch merely to inflate the definition of "real world" if most runtime is outside Python and the dependency footprint is enormous.

# Add a first-party realistic Django benchmark

This is important enough that we should own a small benchmark rather than depend solely on `django_template` or old DjangoCMS.

Create a compact deterministic Django application under the benchmark tree.

As of September 2026 the current Django release is 6.1.1. Pin it for the CPython 3.14 benchmark environment.

Django 6.1 officially supports Python 3.12–3.14, not 3.15/3.16.

Therefore:

* CPython 3.14 comparisons should use the pinned current Django release.
* A CPython 3.16 comparison may try the exact same pinned benchmark environment.
* If it cannot run, report the workload as unsupported for that interpreter.
* Do not silently use a different Django version on candidate and baseline.
* A future separately named `django-next` benchmark may target a Django development revision that supports a newer Python, but it must be a distinct benchmark identity.

## Django benchmark shape

Use SQLite to avoid introducing an external database server into the default deterministic qualification environment.

SQLite is not intended to pretend PostgreSQL performance is irrelevant. It keeps the workload reproducible and lets us exercise the Python parts of Django.

Make the application rich enough that SQLite itself is not the dominant cost.

Seed deterministic relational data such as:

```text
Category
Product
Customer/User
Order
OrderLine
```

Use real model relationships.

Create at least these workloads.

### `django_cold_start`

Fresh subprocess each sample.

Measure:

```text
import django
django.setup()
app registry population
settings loading
URLconf loading
model import
middleware construction
```

Record both wall time and process peak/current memory.

This is important for CLIs, server worker startup, tests and development workflows.

### `django_wsgi_mixed`

Call Django's WSGI handler directly so the benchmark measures Django/Python rather than a load generator and TCP stack.

Use a deterministic weighted mix of requests exercising:

* URL resolution;
* middleware;
* ORM model materialization;
* `select_related`/prefetch behavior;
* template inheritance;
* template filters;
* HTML escaping;
* context construction;
* response objects;
* cookies/session-like processing where practical.

A representative HTML route should query enough rows and related objects to create substantial Python work, then render them.

### `django_asgi_mixed`

Exercise the corresponding Django ASGI handler with controlled ASGI scope/send/receive objects.

Do not make the event loop or benchmark harness dominate the workload.

### `django_json`

ORM query + model/value conversion + `JsonResponse` serialization of a nontrivial result.

### `django_form_validation`

POST-like request through Django form/model validation with realistic fields and errors/success cases.

### `django_orm`

Direct application-level ORM workload:

```text
filtered selects
related-object materialization
annotations/aggregation
object construction
small updates inside transactions
```

Do not benchmark SQL in isolation.

## Optional actual HTTP Django workload

An actual HTTP server test is useful in addition to the direct handler path.

If implemented, the load-generating controller should **not run under the candidate interpreter**.

Otherwise candidate Python performance affects both the server and the load generator and obscures attribution.

Use one invariant benchmark-controller environment for both baseline and candidate.

Measure:

```text
request throughput
p50
p95
p99
server CPU
server process-tree memory
```

Use dynamically allocated ports. Never repeat the current fixed-port race problem.

Do not make this the only Django test. The direct WSGI/ASGI paths are cleaner interpreter measurements.

# Add packaging/import workloads

A CPython distribution spends enormous real-world time in package-management, import and source-processing paths.

Add deterministic macro workloads for these.

## `wheel_install`

Use a pinned local wheelhouse containing a realistic representative Python application dependency graph.

Install into a fresh target directory/venv completely offline.

Exercise:

```text
ZIP decompression
hashing
path handling
wheel metadata
email/package metadata parsing
filesystem creation
bytecode-related setup where appropriate
```

The exact package graph must be pinned and identical between baseline and candidate.

Record warm-cache timing as the default CPU-focused comparison.

Do not attempt to flush the OS page cache between runs in normal mode.

A separate cold-I/O experiment can be added later if needed.

## `wheel_extract`

Pure install/extraction path over a pinned corpus of representative wheels, excluding dependency resolution.

This is particularly valuable for measuring:

```text
zipfile
zlib
pathlib
hashlib
metadata parsing
```

## `compileall_real_tree`

Compile a pinned real-world Python source tree—Django, Sphinx, or another substantial corpus.

Measure:

```text
parser/compiler
path traversal
tokenization
marshal
filesystem interactions
```

Keep worker count fixed.

## `import_real_app`

Fresh-process import/setup of substantial pinned applications such as:

```text
Django application
Sphinx
SQLAlchemy application
```

Capture wall time and startup/peak memory.

This complements micro startup benchmarks.

# Other realistic application workloads

Do not reinvent benchmarks already done well upstream.

The qualification manifest should end up covering these broad classes:

| Class                      | Representative workloads                                                             |
| -------------------------- | ------------------------------------------------------------------------------------ |
| Web/framework              | first-party Django; pyperformance FastAPI; selected aiohttp/gunicorn macrobenchmarks |
| ORM/data                   | Django ORM; SQLAlchemy                                                               |
| Developer tooling          | Sphinx; mypy; pylint/pycparser where compatible                                      |
| Packaging/import           | wheel install/extract; compileall; real-app imports                                  |
| Async/network              | asyncio, FastAPI, aiohttp                                                            |
| Serialization              | JSON, pickle, XML, TOML                                                              |
| Text/parsing               | regex, pathlib, HTML/XML, SQLGlot                                                    |
| Numeric/Python object work | SymPy, selected pure-Python pyperformance workloads                                  |
| Startup                    | python startup, stdlib startup, Django cold start, Mercurial                         |
| GC/object churn            | pyperformance GC workloads                                                           |

Every reported aggregate must retain these group boundaries.

Do not let one geometric mean conceal that Django regressed 12% while nbody improved 15%.

# Workload tiers

Define three conceptual tiers.

## Tier 1: qualification macros

Small set of high-value real applications which get the full treatment:

```text
time
memory time series
allocation profile where supported
```

Suggested Tier 1:

```text
django_cold_start
django_wsgi_mixed
django_asgi_mixed
django_orm
django_json
fastapi_http
sphinx
sqlalchemy
mypy2 or equivalent modern mypy workload
wheel_install
compileall_real_tree
import_real_app
```

Keep it around this size.

These are the important human-readable results.

## Tier 2: standardized suite

Full useful pyperformance suite plus selected compatible Pyston macrobenchmarks.

Run:

```text
authoritative timings
max-RSS style memory measurement
```

Where practical, allow deeper memory/allocation instrumentation of any individual benchmark via CLI.

Do not require hundreds of huge Memray traces for every routine qualification.

## Tier 3: targeted kernels

Module-specific benchmarks used when optimizing things such as:

```text
difflib
zlib
base64
pathlib
tomllib
json
logging
urllib.parse
```

These are not a substitute for Tier 1.

They explain *why* the realistic workload moved.

# Memory methodology

Memory needs to become a first-class regression dimension.

## External sampler

Implement a small benchmark-controller sampler.

`psutil` is already present in the benchmark tool stack and is appropriate.

Prefer:

```text
memory_full_info().uss
memory_full_info().pss
memory_info().rss
```

where supported.

USS is particularly useful because it approximates the memory unique to the process that would disappear when that process exits.

For a multi-process server:

```text
aggregate USS = sum USS across process tree
aggregate PSS = sum PSS across process tree where available
aggregate RSS = secondary/informational
```

Summed RSS double-counts shared pages and should not be our primary multi-process memory metric.

Discover children repeatedly during sampling so dynamically created worker processes are included.

A roughly 20–50 ms sampling interval is appropriate by default; benchmark and tune the observer overhead. It runs outside the candidate and therefore must not contaminate timing runs.

Record timestamps and process identities in the raw sample stream.

## Short-lived processes

Polling can miss the peak of very short startup workloads.

For these, supplement the sampler with OS child max-RSS information where possible, normalizing units carefully.

Do not assume `ru_maxrss` uses the same units on Linux and Darwin.

Add tests specifically for unit normalization.

## Memory phases

Workloads under our control should expose phase markers to the controller when useful:

```text
process_started
imports_complete
fixture_setup_complete
warmup_complete
steady_state
workload_complete
post_gc
```

Do not require every third-party pyperformance benchmark to adopt this.

For our Tier-1 workloads it will make memory regressions dramatically easier to understand.

## Memory report

Per workload report:

```text
baseline peak_uss
candidate peak_uss
absolute delta bytes
relative delta
baseline peak_rss
candidate peak_rss
steady-state deltas
retained deltas
PSS where available
sampling coverage
number of processes
```

Never print only percentages.

"+2%" means something entirely different when the baseline is 12 MiB versus 2 GiB.

# Memory regression policy

The target is:

```text
candidate <= matched upstream baseline
```

Report exact `better`, `equal`, or `higher` raw direction.

Because operating-system measurement has page granularity and run-to-run noise, add a small **measurement noise band**, not a performance budget.

A sensible starting classification is:

```text
equal_within_noise:
    relative excess <= 1%
    AND
    absolute excess <= 1 MiB
```

Anything beyond both dimensions is a regression.

Refine the exact noise bound empirically by repeatedly comparing an interpreter against itself.

Do not simply assume 1% is correct.

The implementation should include a self-comparison calibration command that measures baseline-vs-baseline variance and emits observed memory noise.

Tier-1 memory is individually gated.

A good geomean cannot cancel an individual Tier-1 memory regression.

For an `upstream_matched` comparison:

```text
unexpected Tier-1 memory regression => qualification failure
```

For PBS/distribution/exploratory comparisons, report memory but do not claim it satisfies the upstream memory contract.

# Allocation methodology

Memray is the preferred allocation profiler because it can track:

* Python code;
* CPython interpreter allocations;
* native extension allocations;
* native stacks;
* pymalloc allocations when explicitly requested.

Do not use `tracemalloc` as the primary allocation metric because it does not provide a complete picture of native/Rust/C allocation behavior.

## Two concepts

Preserve both:

### System allocator pressure

Default/native Memray tracking tells us when Python/native code requests memory from the system allocator.

Useful for:

```text
real heap growth
large allocations
Rust allocations using the system allocator
native libraries
fragmentation pressure
```

### Python object churn

`--trace-python-allocators` makes individual pymalloc allocations visible.

Useful for detecting an optimization that is "fast" only because it creates dramatically more transient Python objects.

Report both.

## Normalize

Every custom workload must define a stable unit such as:

```text
one Django request
one ORM transaction
one document build
one type-check operation
one wheel installation
one import
```

Report allocation metrics both absolute and per unit.

Examples:

```text
allocations/request
allocated bytes/request
allocations/document
allocated bytes/wheel
```

## Profiling scope

For Tier 1, perform allocation measurement over a controlled, shortened workload large enough to reach representative steady behavior but small enough that tracing every allocation is tractable.

Do not record a 10-minute allocator trace just because the timing workload normally runs for 10 minutes.

The logical work must be identical; only repetition count may be reduced.

Record the repetition count in the result.

## Self-test

Add an allocation instrumentation self-test before trusting the lane.

It should prove that we can observe at least:

```text
ordinary Python object allocations
system malloc allocations
native-extension allocations
```

For the future Rust build, native Rust allocator activity should also be validated when an appropriate module is available.

If the profiler misses an allocation class, report that limitation explicitly.

# Timing methodology

## Authoritative mode is serial

Do not run candidate and baseline simultaneously for published qualification numbers.

Concurrent runs share:

```text
last-level cache
memory bandwidth
thermal headroom
power budget
frequency behavior
```

The current parallel sharded system is useful for a quick smoke result but is not authoritative.

Retain it only as an explicitly named fast mode.

## Paired runs

For Tier-1 macros, run baseline and candidate in a counterbalanced order such as:

```text
B C C B
C B B C
```

across repeated sets.

This reduces slow thermal/frequency drift.

Use the same:

```text
CPU affinity
fixture bytes
hash seed for each pair
environment
benchmark-controller process
```

For hash randomization, do not disable it globally.

A useful approach is to generate a deterministic sequence of nonzero seeds, then run baseline and candidate with the same seed for each matched pair. Different pairs get different seeds.

That controls pairwise noise while still testing realistic hash-randomized execution.

## Linux

Use pyperf's tuning capability where available.

Capture:

```text
governor
turbo state
CPU affinity
CPU model
SMT topology
load average
kernel
container state
```

Never benchmark under QEMU and publish the result as native performance.

Linux arm64 benchmarks require a native arm64 host.

## macOS

Run natively on Apple Silicon.

We cannot tune the scheduler/CPU as aggressively as Linux.

Record:

```text
machine model
macOS version
power mode if discoverable
thermal state if discoverable
load
active CPU architecture
```

Prefer an otherwise idle machine and serial paired runs.

# Freeze benchmark loop counts

Faster CPython's benchmark infrastructure has an important technique: use a baseline run to establish fixed loop counts rather than letting each interpreter independently calibrate how much work to perform.

Adopt this where pyperformance supports it.

Calibration should happen from the baseline.

Candidate and baseline should then execute identical logical loop counts.

Do not let "candidate is faster" accidentally cause it to run more operations during memory measurement.

For our custom workloads, repetition counts are explicitly fixed anyway.

# Results and provenance

Replace scattered ad-hoc result naming with one run directory such as:

```text
benchmarks/results/<run-id>/
    manifest.json
    environment.json
    timing/
    memory/
    alloc/
    diagnostic/
    report.json
    report.md
```

Do not create a database.

JSON is sufficient.

## `environment.json`

Capture:

```text
hardware
CPU topology
OS/kernel
container image digest if any
baseline interpreter path
candidate interpreter path
baseline SHA-256
candidate SHA-256
full sys.version
sys.implementation
sysconfig build flags
compiler identity
PGO/LTO status where knowable
GIL/free-threading mode
benchmark source commits
wheel/input hashes
benchmark tool versions
CPU affinity/tuning
environment-variable allowlist
```

Also capture loaded native dependency identity when useful for interpreting results.

## `report.json`

For each benchmark include explicit metrics instead of overloading one shape.

Example conceptually:

```text
name
group
tier
support status

timing:
    values
    mean/median as appropriate
    baseline
    candidate
    ratio
    confidence/significance

memory:
    peak_rss
    peak_uss
    peak_pss
    steady_rss
    steady_uss
    retained_rss
    retained_uss
    absolute deltas
    ratios
    classification

alloc:
    system allocations
    Python allocator allocations
    total allocated bytes
    normalized counts
    top sites
    profiler/version

artifacts:
    raw result references
```

Do not discard underlying samples when generating summaries.

# Reporting

Produce a concise `report.md` that a human can actually use.

Start with Tier-1 application workloads.

For each show something like:

```text
                 Time        Peak USS       Allocs/unit
Django WSGI      -7.2%       -1.4 MiB       -8.1%
Django ORM       -2.1%       +0.2 MiB       +1.7%
Sphinx           +0.4%       -3.8 MiB       -2.2%
wheel install    -5.9%       equal          -4.0%
```

Do not use color as the only way to convey result direction.

Then include grouped standardized-suite summaries.

Groups should include at least:

```text
apps/web
startup/import
tooling
serialization
parsing/text
async/network
object/GC
numeric
```

Retain per-benchmark details after the summaries.

A global timing geomean may be shown, but it is not the verdict by itself.

Likewise a global memory average is informational only.

# Statistical treatment

Continue to rely on pyperf/pyperformance's statistical machinery for standard timing results rather than building a homegrown replacement.

For custom macro workloads, either integrate them cleanly with pyperf or use paired repeated measurements with a simple transparent summary.

Do not implement an elaborate statistics framework.

At minimum preserve:

```text
raw observations
central estimate
variance/spread
paired ratios
significance/confidence where available
```

Self-comparison is mandatory.

Before accepting a threshold, run:

```text
baseline vs baseline
candidate vs candidate
```

to characterize noise.

The report should make obvious when an apparent 0.5% change is smaller than environmental variance.

# CLI

Replace the proliferation of shell entry points with a small Python front door.

A reasonable interface is:

```text
python3 benchmarks/run.py doctor
python3 benchmarks/run.py fetch --python <baseline-python>
python3 benchmarks/run.py run \
    --baseline <python> \
    --candidate <python> \
    --suite qualification

python3 benchmarks/run.py run \
    --baseline <python> \
    --candidate <python> \
    --suite full

python3 benchmarks/run.py compare <run-dir>
```

Useful selectors:

```text
--lane time
--lane memory
--lane alloc
--lane diagnostic
--benchmark NAME
--group NAME
--quick
```

Do not build a giant configuration CLI.

Use a simple checked-in manifest for workload definitions and locked inputs.

The existing shell scripts can become tiny compatibility wrappers if retaining them helps existing workflows. Otherwise remove superseded orchestration after the new path is verified.

# Suggested modes

## `--suite qualification`

Tier-1 realistic workloads.

This should be the default answer to:

> Is this Python actually better?

Run time + memory by default.

Allocation profiling can be included in a full qualification run where supported.

## `--suite full`

Qualification macros plus full standardized pyperformance and selected compatible Pyston macrobenchmarks.

## `--quick`

Small smoke run.

It proves:

```text
benchmark environments work
candidate starts
baseline starts
Django workload works
memory sampler works
result generation works
```

It is not evidence for a performance claim.

# Platform architecture

The harness belongs to the whole project.

Support the project targets conceptually:

```text
aarch64-apple-darwin
x86_64-unknown-linux-musl
aarch64-unknown-linux-musl
```

Performance execution must be native.

The existing pinned Alpine Docker environment is appropriate for Linux.

Generalize it enough to work natively on both supported Linux architectures rather than hardcoding x86-64.

Do not run arm64 benchmarks via emulation on an x86 host.

On macOS, run the benchmark controller natively rather than inside Linux Docker.

Use the same benchmark definitions and result schema on all platforms.

Platform-specific absence of a metric is allowed:

```text
PSS unavailable on macOS
```

should be represented as unavailable, not zero.

# Third-party benchmark compatibility

Third-party application benchmarks inevitably lag development Python.

This must be explicit data.

Possible workload status values:

```text
ok
unsupported_python
missing_platform_support
instrumentation_unavailable
failed
skipped_by_policy
```

If Django 6.1.1 refuses to work on CPython 3.16, that is:

```text
unsupported_python
```

It is not permission to install some random different Django revision for only one interpreter.

For a valid head-to-head benchmark, baseline and candidate use the same workload bytes.

# Avoid accidental native-library benchmarks

A "real world" benchmark is not automatically a good interpreter benchmark.

Avoid making the primary suite dominated by work such as:

```text
large NumPy BLAS operations
PyTorch kernels
compression entirely inside an unchanged C library
database server execution
network latency
disk throughput
```

unless the purpose of the workload is specifically to test the Python glue surrounding that operation.

The workload should contain enough actual Python execution that CPython implementation changes can plausibly matter.

# Memory vs binary size

Track installed/native binary sizes separately:

```text
python executable
libpython
extension modules
Rust/C runtime payload
total installed native bytes
```

This is not runtime memory, but it matters for the Rust-for-CPython trajectory because many Rust `cdylib`s can duplicate runtime code.

Do not conflate:

```text
disk size
mapped virtual size
resident memory
unique resident memory
heap allocation
```

Report them separately.

# Specific Rust-for-CPython relevance

Do not special-case Rust behavior in the harness.

However, this harness exists partly so future Rust migrations have a stringent acceptance test.

For a future module migration, the expected workflow should become:

```text
1. run upstream-matched baseline
2. run candidate before change
3. implement Rust acceleration
4. run targeted kernel benchmark
5. run Tier-1 qualification macros
6. run full timing suite
7. compare peak/steady/retained memory
8. compare allocation churn
9. investigate any regression before accepting the migration
```

A dramatic microbenchmark win is insufficient if:

```text
Django slows down
startup regresses
peak USS rises materially
allocation churn explodes
```

# Research references and lessons

Study these directly during implementation.

## Faster CPython `bench_runner`

Important ideas to borrow, not necessarily code:

* pyperformance + python-macrobenchmarks combined through a manifest;
* bare-metal timing;
* reference versions;
* baseline-derived fixed loop counts;
* timing and memory as distinct output dimensions;
* pystats as separate diagnostic information.

Do not import the entire project as a dependency unless there is a compelling reason. Our needs are smaller and cross into project-specific distribution qualification.

## `python/pyperformance`

Keep its philosophy:

* realistic application behavior;
* GC stays enabled;
* ASLR stays enabled;
* hash randomization stays enabled;
* outliers are real data rather than automatically deleted;
* use pyperf stabilization/tuning;
* support custom benchmarks through manifests.

Its `--track-memory` mode is useful prior art but currently documented as platform-limited and, importantly, memory instrumentation adds timing jitter. Our cross-platform external sampler is therefore still valuable.

## `pyston/python-macrobenchmarks`

Use selected application workloads and learn from its simple real-server designs.

Pin source and dependencies.

Do not blindly inherit every old benchmark.

## Bloomberg Memray

Use as allocation profiler where compatible.

Important properties:

* tracks allocations in Python and native code;
* `--native` gives native frames;
* `--trace-python-allocators` reveals pymalloc activity;
* stats include allocation counts and total allocated bytes;
* JSON stats output exists;
* tracing Python allocators creates much larger/slower profiles.

This is why allocation profiling is a separate lane.

# Implementation hygiene

Prefer:

```text
stdlib Python for orchestration
psutil as the already-pinned external process observer
pyperf/pyperformance for timing
Memray only in the allocation lane
small checked-in first-party workloads
locked external sources
JSON raw results
Markdown summary
```

Avoid:

```text
a benchmark database
a web dashboard
a plugin framework
YAML orchestration
new service dependencies
Kubernetes/containers on macOS
automatic cloud runners
a homegrown statistics package
giant generated fixtures
duplicating pyperf internals
```

Do not introduce more ceremony than the benchmark needs.

# Tests

Add unit tests for at least:

```text
interpreter identity validation
same-minor comparison enforcement
memory unit normalization
USS/RSS/PSS parsing
process-tree aggregation
child appearance/disappearance during sampling
short-lived process handling
result-schema serialization
ratio/delta calculations
memory noise classification
unsupported metric handling
unsupported benchmark handling
benchmark lock/hash verification
offline enforcement
group aggregation
Tier-1 memory gate
```

Add functional smoke tests using tiny fake workloads so normal repository tests do not spend minutes benchmarking.

Do not make the unit test suite run Django macrobenchmarks.

# Acceptance criteria

The redesign is complete only when all of the following hold.

1. The harness can compare two explicitly supplied Python interpreters without knowing how either was built.
2. CPython 3.14.6 remains supported.
3. The future CPython 3.16/Rust build can be supplied without architectural changes.
4. Existing PBS comparison remains available as a secondary reference.
5. A matched upstream CPython can be designated as the primary baseline.
6. Benchmark execution is offline after an explicit fetch/preparation step.
7. Third-party benchmark dependencies are byte-pinned.
8. pyperformance remains available as a full standardized suite.
9. Selected Pyston macrobenchmarks are integrated or their incompatibility is explicitly documented.
10. A first-party modern Django application benchmark exists.
11. Django cold-start, WSGI, ASGI, ORM and serialization behavior are exercised.
12. Packaging/install/import workloads exist.
13. Authoritative timing runs contain no memory/allocation profiler.
14. Memory is collected separately by an external observer.
15. RSS and USS are tracked; PSS is tracked where available.
16. Multi-process workloads include their process tree.
17. Raw memory time series are retained.
18. Allocation profiling uses Memray where supported.
19. System/native allocation pressure and Python allocator churn are distinguishable.
20. Allocation counts and bytes are normalized per logical work unit.
21. Memray timing is never used as performance timing.
22. Tier-1 workloads receive individual memory regression verdicts.
23. A global average cannot hide a Tier-1 memory regression.
24. Baseline-vs-baseline noise calibration is implemented.
25. Benchmark order is counterbalanced for serious macro comparisons.
26. Baseline-derived fixed loop counts are used where supported.
27. Linux CPU tuning/affinity metadata is captured.
28. macOS runs natively and capture useful host/power/thermal metadata where available.
29. Native Linux arm64 is supported architecturally; emulation is rejected for performance runs.
30. Results have a stable machine-readable JSON schema.
31. Every run produces a concise human-readable Markdown report.
32. Existing repository tests remain green.
33. Old superseded benchmark scripts/docs are either removed or reduced to clear compatibility wrappers.
34. `benchmarks/README.md` accurately explains what each measurement means and, just as importantly, what it does **not** mean.

# Final quality bar

The end result should make it possible to look at a future optimization and answer, with evidence:

```text
Django WSGI requests are 8.4% faster.
Sphinx is 3.1% faster.
Wheel installation is 11.2% faster.
The full pyperformance apps group is 4.7% faster.

Peak unique memory is unchanged within measured noise.
Django steady-state USS is 1.8 MiB lower.
Startup RSS is unchanged.
Allocations/request fell 12%.
Total allocated bytes/request fell 9%.

No Tier-1 workload regressed materially.
```

That is substantially more useful than:

```text
pyperformance geomean: 1.06x
```

The benchmark system should become a first-class correctness constraint for performance work, particularly as CPython internals begin moving to Rust.

Implement it accordingly.
