# Execution plan — production closeout, then Rust-for-CPython performance

Owner direction, 2026-10-29. This is the only repository-wide priority and
production closeout queue. rust-for-cpython.md remains the one detailed Rust
coverage, parity, benchmark and experiment ledger; backend/ and nix/ are
technical references, not competing campaign plans.

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
coverage; D2 parity was accepted with explicit suite deviations. The last
measured memory checkpoint reported approximately 25 module debts and six
workload peak-RSS debts after the accepted http.client improvement. CPU
optimization has not started. Retain the exact historical data and confidence
intervals in rust-for-cpython.md; do not treat this as a new measurement.

**Sequence:** finish P1-P6 with current receipts, requalify the resulting
production release, then resume R0-R4. Non-invasive preparation is allowed in
parallel. An unavailable host, rejected attempt or missing evidence is
BLOCKED, not an accepted exception to a goal.

The 2026-10-29/30 overnight memory run was a one-session override and has
ended; resume at P1. Order of attack: P1 (local, release-blocking), P4 (code
only), P5, P3, then P2 and P6. P2 runs on this macOS 27 host.
rust-for-cpython.md "Resume here" holds the parked Rust-phase calls.

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
  includes the Berkeley DB `LICENSE` and the Sleepycat source offer. Open: a
  Linux x86-64 archive (no native host here); the CI release run provides it.
  Check this box when that archive lists the notices.
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
  `build-details.json`, and several extension images, and every CI run
  directory includes the run id, so two CI releases will differ and each ships
  its builder path. Open: pin the CI run-directory names or map the path in the
  build (decision), Linux x86-64, and release evidence in CI.

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
  checks that readers see exactly the old or the new generation. Check this box
  when merged to main and a CI release run publishes and assembles through it.
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
  builds. Require P1-P5 accepted receipts, a fresh-current-revision
  three-platform qualification, exact uv-installed archive checksums,
  source/tag identity, full failure accounting and no stale production
  claims before publication. Then qualify and publish the final product
  revision; the old CI success cannot substitute for this new run.

Check P1-P6 only against concrete commits, exact artifact hashes, native
host information and qualification/CI links. Optional Nix bootstrap is not
equivalent to the Alpine/musl product qualification; it also does not
guarantee historical APK URLs remain fetchable.

## R — perfect Rust-for-CPython, after P closes

D1 coverage and D2 parity are accepted historical checkpoints, with
explicit test_ssl, test_support and test_unicodedata differences, not a
zero-failure upstream suite. Experimental Linux arm64 remains out of scope
until its builder is actually implemented and qualified.

- [ ] **R0 — refresh upstream parity and benchmark baselines.** Requalify
  U2 Unicode and U8 regex on native Linux x86-64; replay Mac suites and
  attributed deviations. Handle the parked U7 newer-upstream rebase as
  a coordinated wave, first addressing lock/fetch, marshal-writer and
  overlay conflicts. Qualify any new pin on both supported native hosts;
  never silently change reference controls. Recalibrate the pristine
  control and incumbent, then refresh all 71 routes and eligible workloads.
- [ ] **R1 — eliminate ALL memory debt before any CPU optimization.** Use
  perf.py memory-only paired gates: every module load/working memory
  metric MET or BEYOND and every eligible application peak RSS neutral
  or improved versus control. Outputs must match, two independent runs,
  floors, clean builds, all relevant CPython suites and the seven
  application guards must pass. CPU/wall and host quietness cannot block
  memory-only acceptance. Prioritize SSL working peak, HMAC load,
  datetime and startup/Django residency by measured mechanism. Two
  failed hypotheses park that approach, not the unresolved objective.
  No UNCLEAR/OVER, debt-list waiver or mismatched output counts as done.
- [ ] **R2 — meet per-route CPU goals without losing memory.** Only after
  full R1 completion, run quiet-host replicated CPU gates. Every module
  must be MET or BEYOND on all three metrics (0.9x-1.0x accepted band;
  aim better than 0.9x). All eligible application timing, CPU and RSS
  guards must be neutral or improved; never substitute an aggregate win
  for a regressed route or workload. Keep all Rust-routed behavior.
- [ ] **R3 — optimized release-grade qualification.** Repeat the accepted
  changes with matched -O3/ThinLTO builds (PGO only if the owner reopens it), complete correctness and
  own-GIL subinterpreter tests on native hosts. Separate CPU/timing,
  process memory and allocation passes; self-calibrate, alternate paired
  rounds and verify identical outputs. Compare with upstream and
  python-build-standalone only with compatible Python versions, compiler
  policies and CPU baselines.
- [ ] **R4 — final hardening and evidence.** Resolve or intentionally
  reject remaining behavior differences without weakening tests, close
  per-route and workload verdicts, revalidate ABI/security/licenses
  and write the final reproducible report. Promoting experimental Rust
  into production is an independent product decision.

## Agent rules

Do not add a second performance plan or ledger; use rust-for-cpython.md,
the existing perf.py/perf_verdict.py gate logic and the host lease. One
profile-backed, falsifiable hypothesis per lane. New attempts after
neutral/rejected lanes need a different mechanism. Never remove a public
Rust route or relax suite/benchmark thresholds just to hit a score.
A stopped/blocked run can be honestly reported as incomplete; it never
becomes a completed performance goal.
