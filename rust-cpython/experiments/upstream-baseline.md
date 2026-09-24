# Matched upstream CPython 3.16 control

## Source choice

Use upstream `python/cpython` commit **`0983642c966d9c536416101e99b7d2b085483847`** as the proposed vanilla control for the pinned Rust-for-CPython commit `b812b4a7b9efaca46b98544a8633b7d7e454166b`. GitHub's [upstream-to-fork comparison](https://github.com/Rust-for-CPython/cpython/compare/python:0983642c966d9c536416101e99b7d2b085483847...b812b4a7b9efaca46b98544a8633b7d7e454166b) identifies that upstream commit as the merge base and shows 35 fork commits after it. The [upstream commit](https://github.com/python/cpython/commit/0983642c966d9c536416101e99b7d2b085483847) is dated 2026-07-18; its [`Include/patchlevel.h`](https://github.com/python/cpython/blob/0983642c966d9c536416101e99b7d2b085483847/Include/patchlevel.h) declares `3.16.0a0`. The pinned [fork tip](https://github.com/Rust-for-CPython/cpython/commit/b812b4a7b9efaca46b98544a8633b7d7e454166b) is dated 2026-09-07.

This is the closest **shared-ancestry** upstream revision, not the upstream commit nearest the fork's date. The current upstream `main` has diverged, so using it would add unrelated CPython changes to the comparison. The 35 fork commits do change build integration (`configure`, `Makefile.pre.in`, `Modules/makesetup`, and module setup files), so the control is not byte-identical to the fork with Rust removed. Record the diff and verify relevant public stdlib sources for each workload before attributing a result to a Rust implementation.

## Proposed control build

The experiment-only `rust-cpython/upstream.sources.lock.json` pins the upstream archive at 44,189,176 bytes and SHA-256 `7b8b68534a75aee0003457d42bf9e77a29bb948544cd993a3e059df811eecc7f`, measured from the exact codeload commit URL. `rust-cpython/upstream_control.py` uses the shared verified cache and safe extraction, but has separate source, build, stage, log, and result paths. It does not add a source to the fork's one-input lock or change root production pins, packaging, or release targets. `fetch --source-only` verifies only the archive; plain `fetch` also provisions the locked LLVM toolchain before an offline `build`.

Mirror the current fork recipe in `rust-cpython/build.py` and `build_no_rust.py`: native arm64 macOS 26 host; locked LLVM 23.1.2 clang/binutils/`llvm-profdata`, Xcode 26.6 SDK 26.5 and Apple linker, GNU Make 4.4.1, and the same `bootstrap.lock.json` CPU/deployment settings. Configure out of tree with `--enable-shared --with-lto=thin --enable-optimizations --enable-experimental-jit=no --with-tail-call-interp=no --without-ensurepip`; use GIL-enabled release ABI, `CFLAGS`/`CXXFLAGS=-O3 -mcpu=apple-m1 -fPIC -mmacosx-version-min=26.0`, matching SDK `CPPFLAGS`/`PY_CPPFLAGS`, deployment `LDFLAGS`, `PROFILE_TASK="-m test --pgo -j <same worker count>"`, and locked `LLVM_PROFDATA`. Match `PKG_CONFIG_PATH` and available native dependency versions, `SOURCE_DATE_EPOCH`, `PYTHONHASHSEED`, clean build/install locations, and the offline macOS sandbox. Disable Cargo only where the fork's build system requires it; vanilla upstream has no Rust workspace to build. Check upstream `configure --help` at this commit before carrying flags into a script, then save effective `CONFIG_ARGS`, `sysconfig` flags, tool and SDK identities, PGO task/workers/profile identity, dependency/module inventories, GIL state, and build logs for both sides. Some flag or module parity may prove impossible; report each mismatch rather than treating the builds as matched.

Keep three roles distinct. The immediate attribution control for a zlib change is the **prior accepted Rust-enabled fork with platform zlib**. `rust-cpython/build_no_rust.py` is the **same-source no-Rust control**: it extracts the pinned fork archive, hides Cargo, checks `HAVE_CARGO=no` and `_base64` absence, and records that fork SHA. The new vanilla build is the **upstream control** with the upstream SHA and is the primary overall CPython improvement and memory gate in `rust-for-cpython.md`. Use the same host, inputs, workload counts, and paired measurement method, with process-memory and allocation support added before claiming upstream resource parity.

## Build evidence and remaining comparison

The user's instruction to proceed authorizes this isolated control pin. The
archive was fetched and verified, and the extracted tree's `configure --help`
advertised all required options. Three focused control tests passed. The
coordinator then fetched and verified the official LLVM archive and
attestation, cloned the verified cache into this worktree, and passed
`doctor`. The full nine-worker PGO build succeeded offline in the isolated
worktree. Its report is `data/upstream-build-20260924.json`; the stage and
logs remain in that worktree.

The built interpreter reports CPython 3.16.0a0, GIL-enabled ABI, ThinLTO,
`--enable-optimizations`, `PROFILE_TASK="-m test --pgo -j 9"`, and the same
effective compiler and optimization flags as the existing Rust-enabled and
no-Rust fork builds, apart from checkout-specific paths. The source ancestry
and fork build integration remain real differences. This is a comparable
upstream control, not a proof that every module and dependency matches.
For the first zlib question, the two source trees have identical SHA-256 bytes
for `Modules/zlibmodule.c`, `Lib/gzip.py`, `Lib/zipfile/__init__.py`,
`Lib/zipimport.py`, and `Python/import.c`. All three built interpreters report
platform zlib runtime 1.2.12 before any overlay. The Rust-enabled fork alone
has `_base64`; that is an intentional control difference to account for in
broader workloads.
The build report also records SHA-256 and sizes for the merged PGO profile,
installed executable, and shared libpython. The merged profile digest for
this run is `72af2df052926ea4a755e8ba2145c380c6e202ce7fa54ac13949262b16029245`;
matching the profile task does not imply identical profile counters across
independent builds.

The upstream build used 678.55 user plus 102.69 system CPU seconds and
1,780,416,512 bytes maximum RSS (`/usr/bin/time -l`); elapsed time was
260.54 seconds. This RSS is the command's reported maximum, not a simultaneous
sum of all compiler processes. Host swap usage stayed near 380 MiB. The
verified LLVM fetch used 155.77 user plus 3.38 system CPU seconds and 79.1 MB
maximum RSS; the final `doctor` used 0.13 user plus 0.06 system CPU seconds and
35.4 MB maximum RSS. Earlier source-only fetch, extraction, and focused-test
resource observations are in the lane handoff; they are not workload results.

The next comparison needs serial quiet-host self-calibration and matched
workload runs against the fork, with per-workload source and module inventory
checks. Unique process-tree memory and compatible allocation evidence are
still missing. The ancestry and version claims were checked against the
linked GitHub comparison and source files on 2026-09-24; the local recipe and
lock requirements came from `rust-cpython/build.py`, `build_no_rust.py`,
`sources.lock.json`, `bootstrap.lock.json`, and `rust-for-cpython.md`.

A first local `zlib_decode_1m` harness run did execute both builds after a
stdlib-only wheelhouse selection bug was fixed. It reported -2.59% wall,
-1.01% CPU per decoded byte, and +14.20% peak RSS for the Rust-enabled fork
with platform zlib, and marked the RSS difference a diagnostic FAIL. Host load
was 5.12 and only three memory pairs ran. Its provenance also listed core
wheels that were not installed; that bookkeeping defect was fixed afterward.
The raw run remains in the upstream worktree under
`rust-cpython/results/upstream-vs-fork-zlib-v2/`. Treat it as an integration
check and unresolved signal, not an upstream memory verdict; repeat with
corrected provenance and quiet-host self-calibration.
The raw cross-run and subsequent upstream self-comparison are preserved and
interpreted in `upstream-zlib-control-20260924.md`.
