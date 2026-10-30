# Execution plan — production closeout, then Rust-for-CPython performance

Owner direction, 2026-10-29. This is the only repository-wide priority and
production closeout queue. rust-for-cpython.md remains the one detailed Rust
coverage, parity, benchmark and experiment ledger; backend/ and nix/ are
technical references, not competing campaign plans.

## Starting evidence and non-negotiable scope

The product is OpenSSL-free CPython 3.15.1 for macOS arm64, Linux x86-64 musl
and Linux arm64 musl, preserving the GIL, shared libpython, mimalloc, ThinLTO,
macOS PGO, pinned inputs/toolchains, supported extension APIs and intentional
omissions (pip, ensurepip, venv, Tcl/Tk, tests and bytecode caches).
The [2026-10-26 release workflow](https://github.com/laputa-systems/python-build/actions/runs/40330042202)
passed native three-target builds, final artifact qualification, assembly,
uv-install smoke tests and publication at 3edfbdd0. Later revisions do NOT
inherit that verdict. A macOS 26 binary deployment target has not been
runtime-qualified on macOS 26. Locked inputs alone do not prove reproducibility.

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
only), P5, P3, then P2 and P6. P2 is BLOCKED until the owner supplies real
macOS 26 arm64 hardware or a VM; do not substitute macOS 27. rust-for-cpython.md
"Resume here" holds the parked Rust-phase calls.

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
  Not yet receipted: no build has produced an archive with these files.
  Check this box when a fresh qualified archive for each target lists them.
- [ ] **P2 — prove the real deployment minimum.** Install the exact
  assembled uv archive on actual macOS 26 arm64 hardware/VM; smoke
  startup, relocation under spaces, TLS client/server, subprocess, ctypes
  and native/abi3 extensions. Verify Apple M1 CPU compatibility on
  suitable hardware rather than relying on compiler flags. Preserve native
  Alpine-musl amd64 and arm64 qualification. Save host, archive digest and
  command-level results; never substitute a macOS 27 test for macOS 26.
- [ ] **P3 — independent build reproducibility.** Use two clean sealed
  builds per native target with separate compiled outputs (shared verified
  immutable downloads are fine). Compare paths, file types, modes, symlinks,
  payload bytes, raw archive hashes and PGO identity; distinguish Mac
  signing/UUID differences from actual compiled differences without
  hiding them. Extend the optional reproduce path and require evidence
  on releases. An unchanged source lock is not enough.
- [ ] **P4 — crash-consistent publication.** buildsys.package.publish_files
  rolls back on caught exceptions; replacing archive and artifact.json
  separately is not crash-atomic. Implement immutable verified generations
  with one atomic active-generation selection, or an equivalent protocol
  that preserves dist/target and uv-mirror compatibility. Fault-inject
  process termination between steps; readers must always obtain one
  complete verified generation, never mixed archive/manifest bytes.
- [ ] **P5 — modern TLS security and compatibility.** Preserve TLS 1.2/1.3
  and zero OpenSSL in the shipped payload. Inventory ssl/hashlib/hmac APIs
  by supported, deliberate rejection, or unresolved difference; fix
  unexpected failures without expanding allowlists. Differentially fuzz
  DER/PEM/cert chains/CRLs, hostname and IP verification, SNI, MemoryBIO,
  socket shutdown/ownership and subinterpreter lifetimes. Obtain an
  independent review of verification and the custom Rust/C/Python FFI.
  Refresh the pinned Mozilla CA bundle and document no online revocation
  or legacy TLS guarantees.
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
  changes with matched -O3/PGO/ThinLTO builds, complete correctness and
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
