# Execution plan — production closeout and Rust-for-CPython

Owner direction, 2026-10-29, amended 2026-10-31. This is the only
repository-wide priority and production closeout queue. rust-for-cpython.md
is the one detailed Rust campaign ledger; backend/ is a technical
reference, not competing campaign plans.

## Starting evidence and non-negotiable scope

The product is OpenSSL-free CPython 3.15.1 for macOS arm64, Linux x86-64 musl
and Linux arm64 musl, preserving the GIL, shared libpython, mimalloc, ThinLTO,
pinned inputs/toolchains, supported extension APIs and intentional
omissions (pip, ensurepip, venv, Tcl/Tk, tests and bytecode caches).
The [2026-10-26 release workflow](https://github.com/laputa-systems/python-build/actions/runs/40330042202)
passed native three-target builds, final artifact qualification, assembly,
uv-install smoke tests and publication at 3edfbdd0. Later revisions do NOT
inherit that verdict. That release targeted macOS 26 with PGO; the product now
targets macOS 27.0 only and defers PGO on every target (owner decision
2026-10-30). Locked inputs alone do not prove reproducibility.

Rust-for-CPython is a separate 3.16.0a0 research interpreter, not the
production 3.15.1 artifact. All 71 named public Rust routes achieved D1
coverage; D2 parity was accepted with explicit suite deviations. The
per-module memory-first climb closed on 2026-10-31 with module and workload
memory debt open and no CPU work run; its full ledger is at
`git show d17607f:rust-for-cpython.md`. Do not quote those numbers as current.

**Sequence (2026-10-31):** all work runs on this macOS arm64 host. The
open macOS production work (P5) and the Rust milestone M1 proceed in
parallel; the Rust lane no longer waits for P6. Linux builds,
qualification and CI release evidence wait for the L wave after feature
work is done, and P6 follows L. An unavailable host, rejected attempt or
missing evidence is BLOCKED, not an accepted exception to a goal.

Open state at the change: CI run 41160302125 (build at `1e09b68`) was in
flight; record its verdict here when it lands, without starting new Linux or
CI runs. The retained `.work/wt/openssl-free-modern-keys` worktree shows 260
unstaged deletions of unknown origin; the owner rules on it before anyone
cleans it.

## P — production closeout (release-blocking work)

- [ ] **P1 — verify licenses and source delivery.** Inspect LICENSE and
  bundled notices in the exact SHA-256-locked Berkeley DB 6.0.19 source
  archive. Research identifies this particular version as Sleepycat-licensed,
  unlike later AGPL releases; record proof for the bytes actually used.
  Correct lock metadata, audit all static native dependencies and the RTLS
  Cargo closure, and make required notices plus exact source/patch acquisition
  instructions accompany releases. Prove where Berkeley DB links into the
  payload (ideally only the removable _dbm module), decide whether _dbm
  should remain, and requalify any product-scope change. The metadata
  correction alone does not satisfy redistribution compliance.
  *Status 2026-10-30:* the audit and proof are in
  [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) (6.0.19 is Sleepycat;
  Berkeley DB lives only in Linux `_dbm`; `_dbm` stays). `buildsys/notices.py`
  now installs every bundled input's notices plus `SOURCES.md`, and the
  qualifier's `license_notices` check verifies them in the extracted archive.
  Receipts (local native builds at `38faf1d`; the qualifier `license_notices`
  check passed and notices plus `SOURCES.md` are listed in each archive):
  macOS arm64 archive SHA-256
  `6f4b7ca53e37fec7f3e7fe04ee4ca51780f538d7c19c0a7a00749a3d61aa21ec`
  (Apple M5 Max, macOS 27.0.1); Linux arm64 musl archive SHA-256
  `327003b2007a9529a92ebb9b8f1fd502b292d57e3665fb1b07dc0a6d0d388c46`, which
  includes the Berkeley DB `LICENSE` and the Sleepycat source offer. Open (L
  wave): a Linux x86-64 archive that lists the notices.
- [x] **P2 — prove the macOS 27 deployment minimum.** macOS 27 is the only
  supported macOS release, so its minimum and host floor coincide. Install
  the exact assembled uv archive on a macOS 27 arm64 host; smoke startup,
  relocation under spaces, TLS client/server, subprocess, ctypes and
  native/abi3 extensions. Apple M1 is the minimum hardware and is trusted
  without a hardware run (owner decision). Preserve native Alpine-musl amd64
  and arm64 qualification. Save host, archive digest and command-level
  results.
  *Receipt 2026-10-30:* macOS arm64 archive from `38faf1d`, SHA-256
  `6f4b7ca53e37fec7f3e7fe04ee4ca51780f538d7c19c0a7a00749a3d61aa21ec`,
  installed with `uv 0.13.2` from a local mirror into a directory containing
  a space on an Apple M5 Max running macOS 27.0.1; `.github/scripts/toy.py`
  passed against the uv-installed interpreter, the interpreter's LC_BUILD_VERSION
  minimum is 27.0, and the qualifier's TLS, ctypes, subprocess, extension,
  abi3 and relocation checks passed on the same host. The smoke found that uv's
  install-name rewrite invalidated our ad-hoc signature and the interpreter was
  killed at launch; images are now signed linker-style (`38faf1d`). Apple M1
  is the minimum hardware; the owner accepts the `apple-m1` baseline without
  execution on M1 hardware (2026-10-30), so it is checked by compiler flags and
  load commands only.

- [ ] **P3 — independent build reproducibility.** Use two clean sealed
  builds per native target with separate compiled outputs (shared verified
  immutable downloads are fine). Compare paths, file types, modes, symlinks,
  payload bytes and raw archive hashes; distinguish Mac
  signing/UUID differences from actual compiled differences without
  hiding them. Extend the optional reproduce path and require evidence
  on releases. An unchanged source lock is not enough.
  *Status 2026-10-30:* `build/reproduce_archives.py` compares two product
  archives (entries, modes, symlinks, content; a Mach-O difference passes only
  if it is confined to LC_UUID and the ad-hoc signature). Linux arm64 musl: two
  clean sequential builds at `38faf1d` produced byte-identical archives
  (SHA-256 `327003b2…`, 1,229 files). macOS arm64: two clean builds at `938d172`
  from the same build path reproduced compiled content in all 1,223 files; the
  only differences were 62 Mach-O images differing in UUID and signature, so
  raw archive hashes differ. Builds at different paths do not
  reproduce, on macOS or Linux: the build directory is baked into
  sysconfigdata, the pkg-config files, `python-config`, `config.c`,
  `build-details.json`, and several extension images, and CI run
  directories used to include the run id, so two CI releases would differ.
  The workflow now uses fixed run-directory names (owner delegation,
  2026-10-30), so equal-runner builds share a path; the archives still ship that
  builder path, which a later path-mapping change could remove. Open (L
  wave): Linux x86-64 and release evidence from two CI runs.

- [ ] **P4 — crash-consistent publication.** buildsys.package.publish_files
  rolls back on caught exceptions; replacing archive and artifact.json
  separately is not crash-atomic. Implement immutable verified generations
  with one atomic active-generation selection, or an equivalent protocol
  that preserves dist/target and uv-mirror compatibility. Fault-inject
  process termination between steps; readers must always obtain one
  complete verified generation, never mixed archive/manifest bytes.
  *Status 2026-10-30:* `buildsys/generations.py` publishes archive plus manifest
  as one immutable, hash-sealed generation with an atomic `ACTIVE` switch;
  build, qualify, promote, uvmirror, comparison and benchmarks use it.
  `tests/test_generations.py` kills the publisher at every filesystem step and
  checks that readers see exactly the old or the new generation. Merged to
  main. Open (L wave, unless run 41160302125 already shows it): a CI release
  run that publishes and assembles through it.
- [ ] **P5 — modern TLS security and compatibility.** Preserve TLS 1.2/1.3
  and zero OpenSSL in the shipped payload. Inventory ssl/hashlib/hmac APIs
  by supported, deliberate rejection, or unresolved difference; fix
  unexpected failures without expanding allowlists. Differentially fuzz
  DER/PEM/cert chains/CRLs, hostname and IP verification, SNI, MemoryBIO,
  socket shutdown/ownership and subinterpreter lifetimes. Obtain an
  independent review of verification and the custom Rust/C/Python FFI.
  Refresh the pinned Mozilla CA bundle and document no online revocation
  or legacy TLS guarantees.
  *Status 2026-10-30:* CA bundle refreshed (certifi 2026.10.23). Agent
  review of the hashing FFI and TLS verification code: record and fixes in
  `backend/SECURITY_REVIEW.md`. Differential run against OpenSSL: 325 of 377
  cases agree (16 of 17 chain and policy cases, 4 of 4 CRL cases); no host-name case admits a different host; the 52 differences
  are classified in `backend/DIFFERENTIAL_TLS.md`. Open: a human or external
  audit (decision), the seven remaining PEM/DER loading differences, and a larger
  fuzz corpus (SNI, socket shutdown, subinterpreters).

- [ ] **P6 — final release gate and documentation truth.** Keep cheap
  push-time lint/controller checks and manually dispatched expensive native
  builds. Require P1-P5 accepted receipts, the L wave, a fresh-current-revision
  three-platform qualification, exact uv-installed archive checksums,
  source/tag identity, full failure accounting and no stale production
  claims before publication. Then qualify and publish the final product
  revision; the old CI success cannot substitute for this new run.

Check P1-P6 only against concrete commits, exact artifact hashes, native
host information and qualification/CI links. Historical APK URLs are not
guaranteed to remain fetchable.

## L — deferred Linux gates (after feature work)

One wave on native hosts once P5 and M1 feature work is done; emulated
timing is never evidence.

- [ ] Native `x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl`
  builds and `python3 build.py qualify --target <triple>` at the release
  candidate revision.
- [ ] P1 x86-64 notice listing, P3 Linux reproduction and two CI runs, and
  the CI release run for P4.
- [ ] The Rust lane's **Needs environment** list in rust-for-cpython.md.

## R — Rust-for-CPython milestone M1

The goal is a faster research interpreter with less private code: shared
bindings and output writers, upstream compression wrappers in place of
private adapters, one deser pilot, and one application-level win on matched
optimized builds. Slices S1-S7, the engineering contract, verdict policy and
acceptance live in rust-for-cpython.md and nowhere else. PGO stays deferred
unless the owner reopens it. Promoting experimental Rust into production is
an independent product decision.

## Agent rules

Do not add a second performance plan or ledger; use rust-for-cpython.md,
perf.py/perf_verdict.py and the host lease. Delegation uses the global
`orchestrate` skill. New attempts after a rejected mechanism need a different
mechanism. Never relax suite or benchmark thresholds to hit a score. A
stopped or blocked run is reported as incomplete; it never becomes a
completed goal.
