---
name: rust-cpython-perf-climber
description: Procedure for one Rust-for-CPython performance lane - profile, edit, incremental build, focused suites, explore bench, then qualify with a clean build, full suites, and a gated verdict against the incumbent. Use when a Codex coordinator delegates one isolated performance lane.
---

# Rust-for-CPython performance lane (climber)

You run one lane from the coordinator's brief: one hypothesis about one
module route (plus any application workload the brief adds), in your own
git worktree. The module's goal is kernel CPU, load footprint, and working
peak each at or below 1.0x of the pristine control, aiming for 0.9x; the
brief's `GOAL NOW` row says where it stands. You
finish with a handoff block. The coordinator integrates; you never merge,
push, or edit `main`.

All commands run from your worktree root through
`python3 rust-cpython/perf.py`. `@incumbent` is the coordinator's
accepted runtime and `@control` its pristine `perf-upstream`; the brief gives
an explicit verified `<ACCEPTED_REF>` when the accepted stage has another name.
Use that ref instead of `@incumbent` in the examples below; never rebuild or
rename a qualified accepted stage just to create the default alias. A bare
name is a build in your worktree. Use `LANE` as your candidate build name.

## Current memory-only override (2026-09-30)

The user explicitly resumed work to achieve all memory goals without CPU or
wall performance requirements. During this run, this section supersedes the
older memory-phase CPU/timing guards and quiet-host prerequisites below.
Use `perf.py bench`, `calibrate`, and `goals` with `--memory-only`. Judge
module load footprint and working peak, and workload memory only. CPU/wall
results cannot accept, reject, block setup, or delay work. Preserve the
measurement workloads, memory floors, replication, output checks, verified
clean builds, complete suites and Rust coverage. Do not wait for host quietness
for memory calibration, qualification, or completion. Completion requires
all module memory goals MET/BEYOND and all absolute workload peak RSS neutral
or improved; debt entries remain unresolved goals. The renewed run resets
its lane budget and empty-batch counter; historical evidence stays preserved.
The separate Claude skills and CPU-phase policy remain unchanged.

## Rules

- Use only `gpt-6-luna` at `xhigh` effort, following the user's 2026-10-08
  model-policy change. Do not spawn subagents or switch model or effort. Read
  the repository instructions in your assigned
  worktree. Set `workdir` to that absolute path on every shell command;
  other agents share the initial directory but own different worktrees.
- Coverage stays intact. The public behavior named in your route's
  checklist line in `rust-for-cpython.md` must still reach Rust. Do not
  route it back to C or Python, add a fast path that skips Rust for the
  measured case, or change behavior a suite does not happen to check.
  Never edit `Lib/test/` (the overlay refuses it), anything under
  `benchmarks/`, or `rust-cpython/perf_modules.py`: the workloads and module
  kernels are the measuring stick. If a kernel looks wrong for your route,
  say so under FINDINGS.
- Edit only your `OWNED PATHS`, plus `overlay/Cargo.toml`,
  `overlay/Cargo.lock`, or `overlay/Modules/Setup.local` when the change
  needs them. Any Rust crate from crates.io is allowed for experiments: pin
  it exactly in the overlay `Cargo.lock` (builds run `cargo fetch --locked
  --offline`), populate your worktree's own `.cargo-home` with
  `python3 rust-cpython/build.py fetch` (the only online step; it writes only
  your worktree's cargo home), record the crate, version, and license in the
  route's `THIRD_PARTY_LICENSES.md` and the commit, and run a clean build,
  since incremental builds refuse Cargo changes. Under FINDINGS, give the
  exact commands you used the first time so the coordinator can document
  them. A non-crate dependency (a C library, a system tool) is still a
  BLOCKED finding.
- In the memory phase (the brief says MEMORY ONLY), use `--memory-only`.
  Judge module load footprint, working peak and workload RSS; CPU/wall and
  host quietness cannot block setup or reject a memory candidate. All memory
  guards, output checks, replication, floors and Rust coverage remain binding.
- Use only `perf.py` for builds, suites, profiles, and measurements. Do not
  run `bench.py`, the coverage `build.py build`/`test`, or anything that
  loads the host during someone else's measurement. Never modify a
  `stage-perf-*` tree by hand.
- Start long commands with `exec_command` using a short `yield_time_ms`;
  resume returned sessions with `write_stdin`. Check the final exit code
  and output. Wait at most 60 seconds per call. If `functions.exec` yields
  a cell ID, resume it with `functions.wait` instead. `WAIT  host lease busy`
  means another lane is measuring; keep editing or reading while you wait.
- Keep commands that use the same stage sequential. Inspect a pending test,
  profile, goals, or bench command's completion before starting a build that
  replaces its stage, even when both commands would wait on the host lease.
  Build/test work on independently owned stages may overlap through shared
  leases; memory sampling remains exclusive.
- Commit only overlay source. Never commit `rust-cpython/results/`, logs,
  or stage trees.

## Setup

1. `INCUMBENT` from the brief must be an ancestor of `HEAD`, and
   `git diff --quiet INCUMBENT HEAD -- rust-cpython benchmarks` must pass
   (later commits touched only skills or docs). `perf.py status` must show
   the primary `perf-rust` at `INCUMBENT` with `verified=True`. Otherwise
   stop with `RESULT: BLOCKED`. For an explicitly assigned recovery branch,
   source differences are allowed only within OWNED PATHS and the permitted
   shared overlay files. Treat its WIP as unverified; pass native invariants
   and complete affected suites before exploratory measurement. Final
   acceptance still requires a clean committed build and every assigned suite.
2. `python3 rust-cpython/perf.py setup-worktree`. Reuse a coordinator-verified
   accepted baseline and valid calibration; do not rebuild unchanged baseline
   artifacts or refresh calibration solely because docs or fixtures changed.
3. Build a missing lane stage with `perf.py build --name <LANE> --jobs <JOBS>`.
   Reuse an existing compatible verified stage for incremental exploration.
4. When a new unchanged baseline comparison is needed, run `perf.py bench
   --baseline <ACCEPTED_REF> --candidate <LANE> --module <ROUTE> [--workload <W>]`,
   adding `--memory-only` in the memory phase. It must read NEUTRAL; preserve
   any setup discrepancy and investigate verified inputs rather than changing
   floors. A recovery branch already contains changes, so judge its targets
   after native invariants and complete affected suites pass; final clean/full
   qualification is reserved for survivors.

   A coordinator may explicitly authorize continued memory exploration after
   two unchanged comparisons regress only load footprint, when the source,
   compiler flags, and release artifacts are verified, outputs match, and
   working peak remains neutral. Record the failed setup comparisons and
   their paths; do not call them neutral. This permits exploration only: final
   acceptance requires the coordinator's batch gate built at the primary path,
   with complete suites and all regression guards. Never subtract the offset
   from a ratio or change a measurement threshold to obtain acceptance.
   In the CPU phase, the coordinator may also authorize this recovery for repeated unchanged
   startup-bound wall/CPU regressions of 1% to 3%, when all other rows and
   outputs match. The same source, policy, artifact, and primary-path gate
   requirements apply; retain the real setup verdicts.
   In the CPU phase, the coordinator may also resolve unchanged-route CPU setup drift using a
   fresh primary-path paired guard comparison with unchanged route sources
   and policy, matching outputs, and all route metrics neutral in both runs.
   Preserve both worktree rejections and that primary evidence. This permits
   exploration only; the changed route requires a primary batch memory win
   and every acceptance guard.
   For repeated unchanged startup RSS setup regressions, the coordinator may
   authorize exploration after a fresh clean primary build of the entire
   unchanged overlay and policy. All target metrics must be neutral in both
   primary runs, outputs must match, and all seven workload guards must be
   neutral under the existing replicated verdict. Preserve individual run
   results and both worktree REJECTs. No threshold or ratio changes are
   permitted; final acceptance still needs the changed candidate's primary
   memory improvement, complete suites, and every guard.

## Understand before editing

Read your route's checklist line for the Rust-owned behavior and the suite
list. Then profile your own build:

- `perf.py profile --ref <LANE> --module <ROUTE> --tool sample` for
  native stacks, including Rust symbols, while the route's kernel runs.
- `--tool cprofile` for Python wrapper and call-count costs. Compare with
  `--ref @control` to see what the C route spends on the same kernel.
- For a memory metric, read the kernel in `perf_modules.py`: load footprint
  is import plus first-call retention (extension statics, tables, caches);
  working peak is transient allocation inside the loop.
- `--workload W` profiles an application workload the same way;
  `python_startup` and `import_django` use `-X importtime`.

Confirm or correct the brief's hypothesis from the profile before the
first edit. If the measured cost is not where the brief says, adjust the
hypothesis within your route and say so in the handoff.

## Explore (at most `ATTEMPTS` rounds)

Each round tests one change. Prepare new observable regression fixtures first
and run them on the verified accepted stage before implementation; reuse
unchanged baseline evidence. No blanket packet or extra wrapper approval is a
prerequisite for ordinary authorized execution.

1. Edit.
2. `perf.py build --name <LANE> --incremental --jobs <JOBS>`. It refuses
   build-system changes (`Makefile.pre.in`, `configure`, `Modules/Setup*`) and deleted
   overlay files; run a clean build for those.
3. Run the route's primary suite: `perf.py test --name <LANE> --suite
   test_X`. A failure means fix or discard, never measure.
4. `perf.py bench --baseline <ACCEPTED_REF> --candidate <LANE> --module
   <ROUTE> [--workload <W>] --memory-only` in the memory phase; include affected
   workload RSS and known regression guards before broader sampling. CPU-phase
   timing exploration may use `--timing-only`; it is not a memory screen.
5. ACCEPT: commit the change on your branch and continue from it.
   NEUTRAL or REJECT: discard only this attempt's edits on your owned paths;
   preserve prior commits and inherited WIP. INCONCLUSIVE: rerun once.
   CPU lanes wait for a quiet host; memory lanes follow the rule below.

### Memory exploration and qualification

Use `--memory-only` for memory benches, calibration and goals. Do not wait for
quietness or judge CPU/wall rows. Preserve paired replication, memory floors,
outputs, Rust coverage and every memory regression guard. Record adverse
individual runs even when a final metric is neutral. No provisional quiet-host
confirmation is needed for a memory-only ACCEPT.

Compatible incremental builds, native invariants and complete affected suites
precede exploration. Only survivors receive final clean/full qualification;
Cargo/build-system changes refused by incremental builds still require clean
builds. Fixture-only edits do not require rebuilding an unchanged stage. Keep
same-stage commands sequential; independent source/review and build/test work
on separate stages may overlap under the host lease.

Check progress with memory-only `perf.py goals --candidate <LANE> --module
<ROUTE>` (two runs against `@control`). Finish the lane when its assigned memory
goals are MET/BEYOND or attempts are spent. A failed lane or debt entry does not
complete an unresolved memory goal. CPU-phase goals and quiet-host policy remain
unchanged.

## Qualify (once, on your final commit)

Build names resolve within the invoking worktree. If the accepted named stage
exists only in the primary checkout, the coordinator owns that comparison;
do not substitute the legacy `@incumbent` stage or copy a build report into
the lane to make its name resolve. Use the verified accepted runtime identity
in every comparison.

1. `git status --short rust-cpython/overlay` is empty.
2. Clean build: `perf.py build --name <LANE> --jobs <JOBS>`.
3. Every suite in `SUITES`: `perf.py test --name <LANE> --suite test_A
   --suite test_B ...`. All must pass. Compare skips with the checklist
   line; a new skip in your module is a failure.
4. If you touched module initialization or module state, import the public
   module and make a representative call in a subinterpreter with
   `rust-cpython/stage-perf-<LANE>/bin/python3.16`, and assert
   `_interpreters.run_string()` returns `None`.
5. Incumbent check, right before the gate: `perf.py status` shows the primary
   accepted named ref and source commit. If `git merge-base --is-ancestor <that commit>
   HEAD` fails, `git merge main`, then redo the clean build and the suites
   before gating, since the gate needs a challenger that contains it. Lane
   gates run from long worktree paths and can bias startup-bound guards
   (`import_django`, `python_startup`) by 1% to 3% against the primary-path
   incumbent; if that is the only regressed row, say so in FINDINGS and
   report the gate as is.
6. Gate: `perf.py bench --baseline <ACCEPTED_REF> --candidate <LANE> --module
   <ROUTE> [--workload <W>] --gate`, adding `--memory-only` in the memory phase.
   Report its DECISION as your RESULT. A NEUTRAL or REJECT gate after an
   ACCEPT explore is a real outcome: report
   it; do not rerun the gate hoping for a different draw.
7. Goal: `perf.py goals --candidate <LANE> --module <ROUTE>`, adding
   `--memory-only` in the memory phase; report the row.

When you change code, a real check must exercise it before you report it
done: the incremental build, the suite, and the bench above. A command
that failed to start does not count. If a check cannot run, say which one
and why instead of reporting success.

## Commit message

```text
<Imperative summary naming the route and the mechanism>

<Two to four sentences: the measured cost, the change, why it is faster.>

Route: <checklist item> (<crate>); public behavior still reaches Rust.
Crates: <added crate@version (license)> or none.
Suites: python3 rust-cpython/perf.py test --name <LANE> --suite ... -> <run>/<skipped>, 0 failures
Gate: python3 rust-cpython/perf.py bench --baseline <ACCEPTED_REF> --candidate <LANE> --module <ROUTE> --gate
<the DECISION line and the verdict table rows for targets and any non-neutral guard>
Goal: <the goals row for the route against @control>
```

## Handoff

When the work is done and checked, stop and reply with only this block.
Do not add features, workloads, docs, or refactors you were not asked for;
mention a promising follow-up under FINDINGS instead.

```text
LANE: <name>
BRANCH: <branch> @ <commit>
RESULT: ACCEPT | NEUTRAL | REJECT | INCONCLUSIVE | BLOCKED
GATE: <absolute path to the gate verdict.json, or none>
TARGETS: <entity: metric ratio [95% CI] verdict, for each target metric vs @incumbent>
GOAL: <route: status; cpu / load_footprint / working_peak ratios vs @control>
GUARDS: <any guard that was not neutral, or "all neutral">
SUITES: <command> -> <run>/<skipped>, <failures>
CHANGE: <one to three sentences>
FINDINGS: <only what changes the coordinator's next decision, or none>
```
