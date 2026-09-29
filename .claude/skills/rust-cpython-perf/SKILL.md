---
name: rust-cpython-perf
description: Coordinate the Rust-for-CPython performance hill climb in rust-for-cpython-perf.md with Sonnet 5.5 climber subagents, the perf.py host lease, and replicated paired verdicts. Use for any performance work under rust-cpython/.
---

# Rust-for-CPython performance hill climb (coordinator)

You are the root agent. You own the control and incumbent builds in the
primary checkout, target selection, lane briefs, integration onto `main`,
gate measurements, recorded baselines, and the ledger in
`rust-for-cpython-perf.md`. Climber subagents own one hypothesis each in
an isolated worktree. The coverage rules of `rust-for-cpython.md` still
bind every change: a performance step never removes a checked item's Rust
route, edits `Lib/test/`, or weakens a module suite.

The goal is per module: for each of the 71 checklist routes, kernel CPU,
load footprint, and working peak footprint of `@incumbent` over
`@control` must reach the band 0.9x to 1.0x (see Goals in
`rust-for-cpython-perf.md`). Application workloads guard every step.

Scope: native macOS arm64 (`aarch64-apple-darwin`) only. Linux (x86_64 and
arm64) is out of scope for this phase; do not build, measure, or brief lanes
for it.

Keep working through the loop below until a stop condition in
[Stopping](#stopping) holds. Stop to ask only when you cannot go on
without the user or before a risky step: pushing, deleting a branch that
is not merged, removing a coverage route, or adding a non-crate dependency.

## Models and effort

- Sonnet 5.5 (`claude-sonnet-5-5`) is the only authorized model for this
  lane, for the coordinator and every subagent. Run this session with
  `/model claude-sonnet-5-5` at `/effort high`. Raise the session to
  `xhigh` only while bisecting a failed integration, then return to `high`.
- Spawn only the `rust-perf-climber` (effort `high`) and
  `rust-perf-climber-xhigh` agent types. Both pin the model, effort,
  worktree isolation, and the climber skill in their definitions. Never
  pass `model` to the Agent tool: it overrides the pin, and a repository
  hook rejects it. Do not use `fork`, `general-purpose`, `Explore`, or
  `Plan` agents for this lane; they do not carry the pin.
- Choose `rust-perf-climber-xhigh` only when the lane changes C-ABI
  ownership, reference counting, GIL release, threads, or subinterpreter
  state; changes allocation strategy or the interpreter-wide
  startup/import path; or when a `high` lane on the same target came back
  NEUTRAL or INCONCLUSIVE twice. Everything else is `high`.

## Harness

`python3 rust-cpython/perf.py` is the only build, suite, profile, and
measurement entry point for this phase. Do not run `bench.py` directly or
the coverage `build.py build`/`test` during the climb: they bypass the host
lease.

| Command | Purpose |
| --- | --- |
| `build --name N [--incremental] [--jobs J]` | Clean -O2 no-PGO no-LTO build with Cargo `release`, verified per installed Rust extension; `--incremental` syncs changed overlay files only |
| `build --name perf-upstream --empty-overlay` | Pristine-fork control |
| `test --name N --suite test_X ...` / `--all` | Complete CPython suites on a perf build |
| `goals [--candidate R] [--module M ...]` | Per-module OVER/UNCLEAR/MET/BEYOND status against `@control` (two runs; all 71 routes by default) |
| `modules` | List the module kernel routes (`perf_modules.py`) |
| `profile --ref R (--module M \| --workload W) [--tool cprofile\|sample\|importtime]` | Where the time goes |
| `bench --baseline R --candidate R --module M [--workload W] [--gate]` | Paired measurement with a coded verdict |
| `calibrate --ref R --gate` | Self-compare; identical interpreters must read neutral |
| `status` | Host lease holders and every perf build with commit and flags |

References: `@control` is the primary checkout's `perf-upstream`,
`@incumbent` is its `perf-rust`, and a bare name is a build in the current
worktree. Builds, suites, and profiles share the host; `bench` and
`calibrate` hold it exclusively, and waiting measurements block new builds.
`WAIT  host lease busy` is normal. A bench refuses a stage whose bytes
changed since its build report.

Verdicts compare candidate over baseline. A metric (module kernel CPU,
load footprint, and working peak; workload wall, CPU, and peak memory) is
`improved` or `regressed` only when the
95% interval of the paired median clears a 1% floor in every independent
run; runs that disagree read `unstable`. The decision is REJECT on any
replicated regression, INCONCLUSIVE on an unquiet host (below 80% CPU idle or
on battery), unstable metrics, or a gate with one run, ACCEPT on a
replicated target improvement, and NEUTRAL otherwise; a module or
workload whose outputs differ from the baseline is REJECT (except
`compileall_source` against `@control`, the documented marshal byte
difference). `--gate` requires
clean builds of committed overlays, a challenger that contains the
incumbent commit, the seven workloads in `GATE_WORKLOADS` as guards, the
memory pass, and two runs. Explore runs (no `--gate`) steer; they are
never acceptance evidence.

Run builds, `test --all`, and gate benches with `run_in_background: true`
and wait for the completion notification; they outlast the 10-minute
foreground limit. Do not poll with `sleep`.

## Ground truth (session start, and after any toolchain or pin change)

1. `python3 rust-cpython/perf.py doctor`; `python3 rust-cpython/perf.py
   fetch` once for the Django closure. If `rust-cpython/.cargo-home` is
   missing, run `python3 rust-cpython/build.py fetch` first.
2. `perf.py status`. Rebuild `perf-upstream` with `--empty-overlay` only
   when it is missing, unverified, or the source pin or toolchain changed.
   Rebuild `perf-rust` whenever its commit is not `main` HEAD; commit or
   stash any overlay edits first so the report is clean.
3. `perf.py test --name perf-rust --all`, unless `status` already shows
   `perf-rust` as `all-passed` at `main` HEAD. It must pass with the
   recorded macOS baseline counts from `rust-for-cpython.md` (resource
   denials and platform skips only).
4. `perf.py calibrate --ref @control --gate`. Continue only on
   `CALIBRATION-OK`. On `CALIBRATION-FAILED`, the host cannot resolve the
   floor: tell the user which workloads read different and wait for a
   quieter host rather than raising the floor.
5. `perf.py goals`. Its table is the debt map: OVER modules are targets,
   largest ratio first; rerun `goals --module M` for UNCLEAR modules before
   briefing a lane. MISMATCH is a correctness finding for the user, not a
   lane.
6. `perf.py bench --baseline @control --candidate @incumbent --gate
   --all-workloads` for the application picture the guards protect.

Tell the user in two or three lines what the debt map shows before the
first batch.

## Lanes

- One lane is one hypothesis about one OVER module through its Rust route,
  for example "`json` CPU 4.6x: per-call conversion of dict items through
  a temporary Vec in `_json_rs`". Profile the incumbent first (`perf.py
  profile --ref @incumbent --module M --tool sample` for Rust stacks,
  `cprofile` for Python wrappers) so the brief names a measured cost, not a
  guess. Include an application workload target as well when one exercises
  the route.
- A lane's work on a module ends when every metric is MET; it continues
  toward 0.9x only when no OVER module is waiting for a lane.
- Reserve owned overlay paths per lane before spawning. Two lanes never
  edit the same route. Shared `overlay/Cargo.toml`, `overlay/Cargo.lock`,
  and `overlay/Modules/Setup.local` edits are allowed; you reconcile them.
- Run at most **4** climbers at once by default (the repository cap is 16).
  Measurements serialize through the host lease, so extra lanes add queue
  time, not throughput. Give each lane `--jobs` of `max(2, 9 // lanes)`.
- Climbers never edit `benchmarks/` or `rust-cpython/perf_modules.py`: they
  are the measuring stick. If a kernel misses part of its route's
  checklist behavior, fix the kernel yourself in a separate commit before
  the lane starts, rerun `goals --module M`, and say so in the ledger.
- Before spawning a batch, commit on `main` everything the lanes need and
  confirm `perf-rust` is built at `main` HEAD: worktrees branch from `main`
  and the gate check requires the challenger to contain the incumbent
  commit.

Brief each climber with exactly these fields and nothing it can look up
itself:

```text
LANE: <lane name, a-z0-9 and hyphens; also the perf build name>
TARGET: <module route; plus any application workload that exercises it>
GOAL NOW: <that module's goals row: status and cpu/load_footprint/working_peak ratios>
ROUTE: <checklist item and Rust crate, e.g. zlib / overlay/Modules/_zlib_rs>
HYPOTHESIS: <measured cost from your profile and the change expected to cut it>
OWNED PATHS: <overlay paths this lane may edit>
SUITES: <every complete suite from the checklist line, plus neighbors the change reaches>
INCUMBENT: <main HEAD commit that @incumbent was built from>
JOBS: <N>
ATTEMPTS: <explore attempts before qualifying or giving up; default 6>
```

## Integration

Each climber returns a handoff block. Integrate only `RESULT: ACCEPT`
lanes whose gate verdict you have read in the `GATE:` file.

1. Rebase or merge the accepted lane branches onto `main` in one batch and
   reconcile shared files. Regenerate one `Cargo.lock` when crates changed
   and inspect the package set before building.
2. `perf.py build --name perf-merge`, then `perf.py test --name perf-merge
   --all`. On failure, bisect the batch at `xhigh`, drop or repair the
   interacting lane, and repeat.
3. `perf.py bench --baseline @incumbent --candidate perf-merge --gate
   --module <each lane module> [--workload <lane workloads>]`. The batch
   integrates only on ACCEPT.
   On REJECT, bisect by lane; a lane that regresses a guard when combined
   goes back to its owner or is dropped.
4. Commit the integration on `main` (message below). Rebuild `perf-rust`
   clean at the new HEAD; `perf.py clean --name perf-merge`.
5. `perf.py goals --module <each lane module>` and `perf.py bench --baseline
   @control --candidate @incumbent --gate --all-workloads
   --record-baselines`, then update the ledger and the goal table in
   `rust-for-cpython-perf.md`. Commit the refreshed
   `benchmarks/baselines/rust-cp316-perf-*.json`, ledger, and goal table
   together. Run a full `perf.py goals` every third integration to catch
   cross-module drift.
6. Clean up every lane's worktree as soon as its branch is merged (or
   abandoned), in the same integration, before spawning the next batch. Each
   worktree carries its own APFS-cloned caches, Cargo home, build trees
   (`work/perf/<lane>/`), and stage prefix, so leftovers exhaust the disk.
   For each lane: `git worktree remove --force <path>` (this deletes its
   builds), `git branch -d <lane-branch>` (merged branches only), then
   `git worktree prune` and confirm with `git worktree list`. Also
   `perf.py clean --name perf-merge` in the primary checkout. Keep a
   rejected branch (not its worktree) only when its finding changes the next
   decision. Check `df -h .` at session start and after each integration; if
   free space is under 50 GB, clean stale worktrees and perf builds before
   continuing.

After each integration, tell the user in two or three lines what was
accepted, the gate ratios, and what the next batch targets.

## Records

- Lane commits carry the change, the exact gate command, and the
  `DECISION` line with the target rows from the verdict table. Integration
  commits carry the batch gate table, the `perf-merge` full-suite counts,
  and the `@control` versus `@incumbent` rows for the targets.
- `rust-for-cpython-perf.md` keeps one ledger row per integration: date,
  commit, lanes, module and workload target ratios versus the previous
  incumbent, and the modules' goal statuses versus control. Keep its goal
  table current and a short debt list of routes still OVER after two
  failed lanes. No per-attempt reports, raw logs, or
  result directories in Git; `rust-cpython/results/` stays ignored.
- A coverage port stays even when it remains slower; record that debt
  plainly. Removing a Rust route to recover speed needs the user's decision.

## Stopping

Stop and report when either holds:

- Every module reads MET or BEYOND in a full `perf.py goals` run, or is on
  the debt list after two failed lanes, and every gate workload reads
  `neutral` or `improved` against `@control`; or
- Two consecutive batches integrate nothing.

Report the final goal table, the `@control` versus `@incumbent` workload
table, the ledger rows added this session, open debts, and any lane
findings worth another try.
