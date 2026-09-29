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
[Stopping](#stopping) holds. Follow [Unattended operation](#unattended-operation):
the run may have no one to answer, so never ask a question or wait for a
reply. Never push, delete an unmerged branch, remove a coverage route, or add
a non-crate dependency; record the blocked step as debt or a finding and go
on with other work.

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

## Phases

The climb runs in two phases, in order; never start the second early.

1. **Memory phase.** Targets are only load footprint and working peak. Every
   lane and every ACCEPT is judged on those; kernel CPU is not a target, but
   the gate still REJECTs a replicated CPU regression, so a memory win may
   not cost CPU. The phase ends when a full `perf.py goals` reads every
   module's load footprint and working peak MET or BEYOND, or the module is
   on the debt list for memory (two consecutive lanes on it integrated
   nothing). Brief `GOAL NOW` and `HYPOTHESIS` with memory rows only.
2. **CPU phase.** Starts only after the memory phase ends. Targets are kernel
   CPU per module, then the workload guards that read above `@control`.
   Memory rows become guards: a CPU win that regresses a memory metric that
   was MET is rejected by the same gate.

Until the memory phase ends, do not spawn a lane whose hypothesis is CPU, even
when an OVER CPU row is the largest ratio on the table.

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
- Run at most **8** climbers at once in the memory phase and **4** in the
  CPU phase (the repository cap is 16). Measurements serialize through the
  host lease, so extra lanes add queue time, not throughput; memory lanes
  spend most of their time in builds and suites, which is why they can run
  wider. Give each lane `--jobs` of `max(2, 9 // lanes)`. Each worktree costs
  about 3 GB; keep the disk rule in Integration step 6.
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

## Unquiet host (memory phase)

Memory metrics (load footprint, working peak) do not depend on host load the
way CPU does, so the memory phase does not wait for a quiet host, and a memory
lane may integrate on an unquiet host (the user's decision). Tell each
climber in `HYPOTHESIS`: read the memory rows even when the decision line says
`quiet=no`; use `goals --min-idle 0` and read memory rows only; never wait for
quiet during explore.

A memory lane or batch integrates on an unquiet host when all of these hold in
the gate's own table (a gate that reads INCONCLUSIVE only for `quiet=no`
qualifies):
- every target memory metric reads `improved` in both runs (a wide interval
  that reads `neutral` on one target metric is fine when the other target
  improved and the metric's point ratio is below 1.0 in both runs);
- no row of any kind (CPU, memory, workload wall, CPU, or peak) reads
  `regressed` in either run, and no output mismatch;
- the lane's clean-build suites and the `perf-merge` full suite pass.

Record such an integration as provisional in the ledger. Still require a
`quiet=yes` verdict for calibration, for `--record-baselines`, and for every
CPU-phase lane. When the memory phase ends, rerun one full `goals` and the
`@control` versus `@incumbent` gate on a quiet host (wait for it) to confirm
the provisional rows, and treat any that fail as new memory lanes.

## Unattended operation

The run may go for days with no one watching. These rules replace any step
that would wait for a person.

**Pre-authorized decisions.** Climbers and you may, without asking:
- add any Rust crate from crates.io for a lane (see the climber skill for
  pinning); record its license in the lane's `THIRD_PARTY_LICENSES.md`;
- edit `overlay/Modules/**/*.c` glue so the route's Rust code runs *instead
  of* a duplicate C path, when the public behavior still reaches Rust and the
  module's full suites pass (for example `_zstd/compressor.c` running the C
  route first and Rust on a copy);
- relaunch a lane as a new climber from a dead or stopped lane's branch: the
  harness cannot resume a stopped agent. Commit its uncommitted edits as a WIP
  commit, then brief the new lane with the branch name and "treat the WIP as
  unverified".

Never, without a person: push; remove a Rust route or weaken a suite; edit
`Lib/test/`, `benchmarks/`, or `perf_modules.py` (except fixing a kernel
gap, Lanes rule); touch `main` history other than adding commits. Record the
blocked step under the debt list or a finding and continue with other work.

**Quiet host.** In the CPU phase, and for calibration and baselines, only
verdicts with `quiet=yes` count. (Memory-phase integrations follow the Unquiet
host rule instead.) Before each such run, wait:
`python3 .claude/skills/rust-cpython-perf/wait_quiet.py 180` with
`run_in_background: true` (exit 0 = quiet, 1 = 180 minutes without a quiet
sample). Recalibrate (`calibrate --ref @control --gate`) at session start,
after every 6 hours of wall time, and after any host change; `CALIBRATION-OK`
with `quiet=yes` is required first. A verdict that reads INCONCLUSIVE only
for `quiet=no` is neither a failure nor an empty batch: keep the branch and
its worktree and re-gate later. If four consecutive waits time out, stop and
report `host never quiet` with the branches waiting for a gate. Memory
metrics steer explore runs and, under the Unquiet host rule, memory
integrations; a CPU result on an unquiet host never counts.

**State and recovery.** After every change to lanes, branches, worktrees, or
counts, rewrite `rust-cpython/results/coordinator-state.json` (ignored by Git):

```json
{"phase": "memory", "batch": 3, "lanes": [{"name": "json-mem", "agent": "<id>",
  "branch": "<branch>", "worktree": "<path>", "status": "running|waiting-gate|integrated|failed",
  "module": "json", "kind": "memory|cpu"}], "failed_lanes": {"json": 1},
  "debt": ["lzma"], "last_calibration": "<UTC time>", "notes": ""}
```

At session start and after any context loss, rebuild your picture from that
file, `git worktree list`, `git branch --list 'worktree-agent-*' 'integrate-*'`,
`perf.py status`, and the ledger, then continue. A stale worktree with no live
agent and no `waiting-gate` entry is swept: WIP-commit anything valuable to its
branch first, then remove it. Sweep at session start and before each batch.

**Failed lanes.** A lane counts as failed when its handoff is NEUTRAL, REJECT,
or BLOCKED, or its gate is INCONCLUSIVE for a reason other than `quiet=no`
(unstable metrics after a quiet re-gate); a climber that dies without a
handoff is relaunched once, then counted. A module goes on the debt list after
two consecutive failed lanes that integrated nothing. A lane that integrates
resets that module's count, even when the module is still OVER.

**UNCLEAR rows.** Rerun `goals --module M --profile rigorous` once. Still
UNCLEAR: treat it as OVER when the pooled median exceeds 1.01x and brief a
lane, otherwise as MET and note it in the ledger. Never loop on it.

**Budget and disk.** Stop and report after 150 lanes in a session. Never
spawn a lane when `df -h .` shows under 20 GB free; sweep first, and stop and
report if the sweep cannot recover space.

**Shared costs.** When a lane's FINDINGS name another route's import or
first-call cost that shows up in three or more modules (for example `_re_rs`
loading at import), brief one lane at `rust-perf-climber-xhigh` owning that
route, ahead of the per-module lanes it would help, then rerun `goals` for the
affected modules.

## Integration

Each climber returns a handoff block. Integrate only `RESULT: ACCEPT` lanes
whose gate verdict you have read in the `GATE:` file. In the memory phase, a
lane that returns `INCONCLUSIVE` only for `quiet=no` also qualifies when its
table meets the Unquiet host criteria.

1. Rebase or merge the accepted lane branches onto `main` in one batch and
   reconcile shared files. Regenerate one `Cargo.lock` when crates changed
   and inspect the package set before building. Do the merge in an
   `integrate-N` worktree, not on `main` (fast-forward `main` only after the
   batch gate ACCEPTs); when crates changed, run `python3
   rust-cpython/build.py fetch` there to populate its cargo home, and after
   integrating copy that cargo home's new crates to the primary checkout the
   same way before rebuilding `perf-rust`.
2. `perf.py build --name perf-merge`, then `perf.py test --name perf-merge
   --all`. On failure, bisect the batch at `xhigh`, drop or repair the
   interacting lane, and repeat.
3. `perf.py bench --baseline @incumbent --candidate perf-merge --gate
   --module <each lane module> [--workload <lane workloads>]`. The batch
   integrates only on ACCEPT (memory phase: or an INCONCLUSIVE for `quiet=no`
   alone whose table meets the Unquiet host criteria, recorded as provisional).
   On REJECT, bisect by lane; a lane that regresses a guard when combined
   goes back to its owner or is dropped.
4. Commit the integration on `main` (message below). Rebuild `perf-rust`
   clean at the new HEAD; `perf.py clean --name perf-merge`.
5. `perf.py goals --min-idle 0 --module <each lane module>` (memory phase; add
   `--min-idle` default in the CPU phase) and, when the host is quiet,
   `perf.py bench --baseline @control --candidate @incumbent --gate
   --all-workloads --record-baselines` (in the memory phase, defer this to the
   end-of-phase quiet confirmation), then update the ledger and the goal table in
   `rust-for-cpython-perf.md`. Commit the refreshed
   `benchmarks/baselines/rust-cp316-perf-*.json`, ledger, and goal table
   together. Run a full `perf.py goals` every third integration to catch
   cross-module drift.
   Lanes still running when `main` advances (continuous lanes): right after
   the commit, rebuild `perf-rust` and message every running climber with the
   new `INCUMBENT`, telling it to `git merge main` before Qualify (its gate
   requires a challenger that contains the incumbent commit). New lanes use
   the new `INCUMBENT`; the climber setup check accepts any `main` whose
   overlay diff against `INCUMBENT` is empty.
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

A memory-only goal stops at the end of the memory phase. The full goal ends
after the CPU phase. Stop and report when any of these holds:

- Every module reads MET or BEYOND on the phase's metrics in a full
  `perf.py goals` run (memory: load footprint and working peak; CPU phase:
  all three), or is on the debt list, and, in the CPU phase, every gate
  workload reads `neutral` or `improved` against `@control` or has had two
  failed workload lanes; or
- Two consecutive batches integrate nothing, not counting a batch whose only
  outcome was INCONCLUSIVE for `quiet=no` (those branches wait for a gate);
  or
- `host never quiet`, the lane budget, or the disk floor from Unattended
  operation.

A workload that reads above `@control` in the CPU phase gets its own lane
(for example `zlib_decode_1m` through the zlib and gzip routes); a module win
does not close it.

Report the final goal table, the `@control` versus `@incumbent` workload
table, the ledger rows added this session, open debts, and any lane
findings worth another try.
