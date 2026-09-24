# macOS 3.16 application input and cold Django audit

Scope: read-only inspection at `3ff3b10` on 2026-09-24. No dependencies were
fetched, installed, or tested. This is an implementation plan, not a claim
that the proposed wheels run on the experimental interpreter.

## Current boundary

- `benchmarks/inputs.lock.json` has one target: CPython 3.14, Linux x86_64,
  musl. Its 98 artifacts comprise 97 wheels and one source archive; 11 wheels
  have native musllinux tags (nine `cp314`, one `cp36-abi3`, one `cp39-abi3`).
  The `macros` group includes native `greenlet`, `isort`, and `pydantic-core`
  wheels built for Linux. Its included `core` group adds Linux `psutil`.
  `benchmarks/vendor/` contains four checked-in wheels; its `psutil` wheel
  is also musllinux. These artifacts cannot silently become the macOS 3.16
  application environment.
- `benchmarks/harness/inputs.py:load_lock` explicitly accepts only Linux
  x86_64. `fetch_inputs` verifies size and SHA-256 and publishes cached
  artifacts; `prepare_site` verifies then extracts a selected group's wheels
  into a shared external site. It checks a wheel's declared tags against its
  filename, but does **not** check those tags against either interpreter or
  the host. A macOS lock needs an explicit target/ABI validation before
  extraction. Keep Linux's existing lock and target behavior intact.
- `benchmarks/bench.py:_run_internal` admits native arm64 macOS with `--local`,
  but `realworld` selects `macros` and the Linux lock, while `pyperformance`
  and `full` are rejected on macOS. `bench.py fetch` intentionally skips the
  wheelhouse for macOS. The checked-in macOS baseline JSON is a smoke result;
  it supplies no application dependency fixture. No cached wheelhouse or
  3.16 stage tree was present in this assigned worktree. The existing
  `benchmarks/workloads/fixtures/tooling/` source trees, Django application,
  and `catalog_url` records are repository-owned, platform-neutral inputs.
  The checked-in pure-Python `packaging`, `pyperf`, and `pyperformance` wheels
  may be candidate bytes for a future macOS lock after their metadata and
  behavior are checked; their presence is not a compatibility verdict.
- `benchmarks/workloads/registry.py` marks package requirements per workload,
  but `_requires_macro_inputs` prepares the entire `macros` group for any
  package workload. A Django-only selection therefore still pulls native
  FastAPI/Pydantic, pylint, and SQLAlchemy dependencies. `workload_environment`
  exposes the shared prefix through `PYTHONPATH` and disables user site and
  bytecode writes. This path avoids a `pip` or `venv` dependency in the
  measured interpreter. `pip_install_wheelhouse` is a separate workload that
  explicitly needs locked pip and an installable complete wheelhouse.

## Bounded input implementation

1. Decide whether third-party application packages and a macOS benchmark
   input lock are in scope for this **experiment**. This changes the current
   source/dependency boundary in `rust-for-cpython.md`; it does not change the
   production 3.14 product. Approve the chosen application set and package
   versions before resolving new artifacts. Do not substitute a different
   version on only one side of a comparison. A small first tranche is Django
   WSGI/ASGI/ORM/template plus the existing package-free application and
   tooling fixtures. Add pylint, pycparser, FastAPI, SQLAlchemy, and the pip
   installation workload only when each has its own complete compatible
   closure and a stated measurement purpose.
2. Add a separately named macOS arm64 CPython 3.16 lock rather than relabeling
   `benchmarks/inputs.lock.json`. Preserve each record's exact URL, filename,
   SHA-256, byte size, license, purpose, version, wheel tags, and workload
   group. Resolve a complete transitive closure per selected group from
   distribution metadata for the actual target interpreter. The existing
   Django 6.1.1, asgiref 3.12.1, and sqlparse 0.6.0 entries are pure wheel
   candidates, subject to metadata and 3.16 execution checks. Reuse an
   already pinned byte only if its wheel tag, metadata requirements, and
   behavior pass for the target. Pin native macOS arm64/ABI wheels by their
   own bytes; do not install or extract a musllinux extension on macOS.
3. Generalize `benchmarks/harness/inputs.py:load_lock` to validate an explicit
   supported target descriptor, and check every selected wheel tag against
   both tested interpreters before `prepare_site` extraction. Fail closed on
   unmatched or ambiguous artifacts, including multiple versions in one
   group. Route `benchmarks/bench.py` local arm64 input selection and its
   `fetch` path to the new lock and wheelhouse; snapshot the selected lock
   and exact artifact digests in each result. Split package groups by actual
   workload closure so a Django-only run needs only Django's approved inputs.
   Keep the Linux lock, offline container path, and frozen Linux tests as is.
4. Use the same prepared site and fixture bytes for upstream 3.16 control,
   last accepted fork control, and candidate. Validate imports and complete
   output digests before timing. Record unsupported rows explicitly when no
   compatible closure exists. Extend selected pyperformance only after the
   macOS allocation/memory limitation and its separate package payload are
   represented honestly; `benchmarks/harness/pyperformance.py` already runs
   scripts from an external prefix, but `bench.py` presently blocks the suite
   on macOS. Selected Pyston macros likewise need an approved, byte-pinned
   source/fixture and compatibility review; none is present in this lock.

## True cold Django first request

`benchmarks/workloads/django.py:_bootstrap_application` imports and sets up
Django, creates schema, and seeds 10,000 rows. `_run_wsgi` and `_measure_asgi`
then construct a handler and issue a validation request before starting their
internal `perf_counter` interval. These are warm request measurements, even
though `benchmarks/harness/runner.py:run_workload` launches a new process for
each pass. `import_django` in `benchmarks/workloads/extra.py` covers fresh
import only, not a request.

Implement a separate `django_wsgi_first_request` (and ASGI counterpart if
needed) in `benchmarks/workloads/registry.py` and `django.py`. Prepare one
deterministic, byte-hashed SQLite database fixture outside the timed process,
using the same model and row definitions as `_seed_database`. Each measurement
starts a fresh interpreter with that fixture available read-only or through a
private per-run copy, imports Django, runs `django.setup()`, builds its handler,
executes exactly one request, validates status and full response digest, and
exits. No earlier request, template render, or handler initialization occurs
in that process. Use the external process duration in
`benchmarks/harness/runner.py` as wall latency from spawn to completion; the
current runner favors the workload's internal `elapsed_seconds`, which omits
startup. Label the operation `first request process` and document whether
database copy/open is inside the measured boundary. A second optional phase
marker can separate setup from request execution without changing the
primary end-to-end number. Preserve separate warm WSGI/ASGI rows. Add a
focused regression proving one request only, identical digest across fresh
processes, and that the reported timing uses the process boundary. Compare
the same fixture and bytecode policy on all interpreters.

## Decision and evidence gate

The immediate scope decision is authorization to add a target-specific
benchmark dependency lock and the selected third-party application set for
the macOS 3.16 experiment. Without that decision, package-free workloads can
run locally, but a primary application-suite or cold-Django qualification
cannot. Once approved, the hard judge is target-tag/metadata validation,
then complete workload correctness and self-comparison before performance
claims. Current macOS results still lack qualified unique/proportional memory
and allocations per `rust-for-cpython.md`; neither missing metric is a pass.
