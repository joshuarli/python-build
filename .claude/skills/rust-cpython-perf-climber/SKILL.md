---
name: rust-cpython-perf-climber
description: Procedure for one Rust-for-CPython performance lane - profile, edit, incremental build, focused suites, explore bench, then qualify with a clean build, full suites, and a gated verdict against the incumbent. Preloaded by the rust-perf-climber agents.
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
`perf-rust` build and `@control` its pristine `perf-upstream`; a bare name
is a build in your worktree. Use your `LANE` value as your build name.

## Rules

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
  needs them. Vetted Rust crates are allowed when pinned in the overlay
  `Cargo.lock` with a compatible license you name in the commit; any other
  new dependency is a BLOCKED finding.
- Use only `perf.py` for builds, suites, profiles, and measurements. Do not
  run `bench.py`, the coverage `build.py build`/`test`, or anything that
  loads the host during someone else's measurement. Never modify a
  `stage-perf-*` tree by hand.
- Run `build`, `test`, and `bench --gate` with `run_in_background: true`
  and wait for the completion notification; do not poll with `sleep`.
  `WAIT  host lease busy` means another lane is measuring; keep editing
  or reading while you wait.
- Commit only overlay source. Never commit `rust-cpython/results/`, logs,
  or stage trees.

## Setup

1. `git rev-parse HEAD` must equal `INCUMBENT` from the brief, and
   `perf.py status` must show the primary `perf-rust` at that commit with
   `verified=True`. Otherwise stop with `RESULT: BLOCKED`.
2. `python3 rust-cpython/perf.py setup-worktree`.
3. `python3 rust-cpython/perf.py build --name <LANE> --jobs <JOBS>`.
4. `perf.py bench --baseline @incumbent --candidate <LANE> --module
   <ROUTE> [--workload <W>]`. An unchanged lane build must read NEUTRAL. If
   it reads anything else, rerun once; if it still differs, stop with
   `RESULT: BLOCKED` and the verdict table.

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

Each round tests one change:

1. Edit.
2. `perf.py build --name <LANE> --incremental`. It refuses build-system
   changes (`Makefile.pre.in`, `configure`, `Modules/Setup*`) and deleted
   overlay files; run a clean build for those.
3. Run the route's primary suite: `perf.py test --name <LANE> --suite
   test_X`. A failure means fix or discard, never measure.
4. `perf.py bench --baseline @incumbent --candidate <LANE> --module
   <ROUTE> [--workload <W>] --timing-only` (`--timing-only` skips the
   workloads' memory pass; module kernels always measure memory).
5. ACCEPT: commit the change on your branch and continue from it.
   NEUTRAL or REJECT: discard it with `git restore` on the overlay paths
   (or `git reset --hard` to your last commit). INCONCLUSIVE: rerun the
   bench once; if the host is not quiet, wait and rerun.

Check progress against the goal with `perf.py goals --candidate <LANE>
--module <ROUTE>` (two runs against `@control`). Stop exploring when every
metric reads MET (keep going toward 0.9x only while attempts remain and
changes keep reading ACCEPT), or when the attempts are spent.

## Qualify (once, on your final commit)

1. `git status --short rust-cpython/overlay` is empty.
2. Clean build: `perf.py build --name <LANE> --jobs <JOBS>`.
3. Every suite in `SUITES`: `perf.py test --name <LANE> --suite test_A
   --suite test_B ...`. All must pass. Compare skips with the checklist
   line; a new skip in your module is a failure.
4. If you touched module initialization or module state, import the public
   module and make a representative call in a subinterpreter with
   `rust-cpython/stage-perf-<LANE>/bin/python3.16`, and assert
   `_interpreters.run_string()` returns `None`.
5. Gate: `perf.py bench --baseline @incumbent --candidate <LANE> --module
   <ROUTE> [--workload <W>] --gate`. Report its DECISION as your RESULT. A
   NEUTRAL or REJECT gate after an ACCEPT explore is a real outcome: report
   it; do not rerun the gate hoping for a different draw.
6. Goal: `perf.py goals --candidate <LANE> --module <ROUTE>`; report the row.

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
Gate: python3 rust-cpython/perf.py bench --baseline @incumbent --candidate <LANE> --module <ROUTE> --gate
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
