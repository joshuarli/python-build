---
name: rust-cpython-perf
description: Coordinate the Rust-for-CPython performance hill climb in rust-for-cpython-perf.md with Codex GPT-6 Luna climber subagents at xhigh effort, the perf.py host lease, and replicated paired verdicts. Use for Codex performance work under rust-cpython/; coverage uses rust-cpython-coordinator.
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

## Current memory-only override (2026-09-30)

The user explicitly resumed work to achieve all memory goals without CPU or
wall performance requirements. During the memory phase of this run, this section supersedes the
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
The user extended the objective on2026-10-01: after every memory goal passes,
continue through all performance goals while guarding meaningful memory
regressions. Focus on algorithms and memory layout; do not write assembly or
SIMD optimizations. Any Rust crate may be adopted under the existing pinning
and license rules. The separate Claude skills remain unchanged.

## Codex models and delegation

- The coordinator and every subagent use only `gpt-6-luna` at `xhigh`
  reasoning effort, following the user's 2026-10-08 model-policy change.
  Never use another model or effort for performance work, including reviews,
  scouts, recovery, or difficult lanes. Split difficult changes into smaller
  hypotheses while keeping the same model and effort.
- This skill explicitly authorizes lane delegation. Use Codex collaboration
  tools; Claude agent definitions and hooks do not configure Codex agents.
  Create the lane branch and isolated worktree yourself before spawning.
- Call `collaboration.spawn_agent` with `model: "gpt-6-luna"`,
  `reasoning_effort: "xhigh"`, and `fork_turns: "none"` on every spawn.
  Give the child a self-contained brief, absolute primary/worktree paths,
  and the absolute path to the Codex
  [climber skill](../rust-cpython-perf-climber/SKILL.md). Tell it to read that
  skill and work only in its assigned worktree; shell calls must set `workdir`
  explicitly because agents share the initial working directory. Children
  never spawn agents. UI metadata cannot enforce model settings; explicit
  tool arguments are required.
- Use `collaboration.send_message` to update running lanes and
  `collaboration.followup_task` for available idle agents. Reconcile
  `collaboration.list_agents` with saved lane state after interruption;
  do not assume a stopped agent lost its branch or edits.

## Phases

The climb runs in two phases, in order; never start the second early.

1. **Memory phase.** Targets are module load footprint, working peak and
   eligible workload peak RSS. Every
   lane and every ACCEPT is judged on memory rows with `--memory-only`; CPU,
   wall time and host quietness cannot reject or delay memory work. The phase
   ends only when every module's load footprint and working peak are MET or
   BEYOND and a complete `@control` versus `@incumbent` comparison reads every
   workload's `peak_rss` neutral or improved. Module and workload debt remain
   unresolved goals; the debt list does not waive completion. Workload peak
   RSS is interpreter-wide memory (imports of
   Rust routes at startup and first use); brief workload memory lanes from
   `perf.py profile --workload W --tool importtime` and sample stacks,
   comparing `@control`. Brief `GOAL NOW` and `HYPOTHESIS` with memory rows only.
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
replicated regression in the active phase's metrics, INCONCLUSIVE on unstable
metrics or a gate with one run, ACCEPT on a
replicated target improvement, and NEUTRAL otherwise; a module or
workload whose outputs differ from the baseline is REJECT (except
`compileall_source` against `@control`, the documented marshal byte
difference). `--gate` requires
clean builds of committed overlays, a challenger that contains the
incumbent commit, the seven workloads in `GATE_WORKLOADS` as guards, the
memory pass, and two runs. Explore runs (no `--gate`) steer; they are
never acceptance evidence. CPU-phase comparisons also require a quiet host
(below 80% CPU idle or on battery is unquiet); memory-only comparisons do not.

Start long commands with `exec_command` using a short `yield_time_ms`.
When it returns a `session_id`, resume with `write_stdin` and inspect the
exit code and final output before proceeding. Wait at most 60 seconds per
tool call so progress updates and steering remain possible. If
`functions.exec` itself yields a cell ID, resume it with `functions.wait`;
a cell ID is not an exec session ID. Do not launch a second command because
a first command merely yielded.

## Ground truth (session start, and after any toolchain or pin change)

Read the current objective, progress and ledger in `rust-for-cpython-perf.md`
first. Outstanding confirmation and baseline-refresh steps take precedence
over routine lane selection. Recover state and check disk space before scheduling work.
Use an installed Python 3.11 or newer; check `python3 --version` first.
If Apple Python is older, use an already installed interpreter explicitly,
such as `uv run --no-project --offline --python 3.14 python`, for every
harness and helper command. This is a controller interpreter, not a change
to the locked CPython source or product version.

Run doctor before fetching or building. If the locked SDK/toolchain cannot
be used, report the prerequisite failure and stop performance execution;
do not change pins, substitute a compiler, or install new system tools.
When no verified builds remain, rebuild the control and incumbent before
calibration. A historical handoff is evidence, not proof of local stages.

For outstanding provisional integrations, run memory-only `goals` on every
provisional module as well as the full workload gate against `@control`.
Check the original per-batch gate evidence to distinguish target improvements
against the previous incumbent from absolute goals against control. A
workload-only control comparison cannot establish a module improvement
against a previous incumbent; if that confirmation is needed, rebuild the
recorded previous and candidate commits in isolated worktrees and repeat
those module comparisons before marking the row confirmed. Do not infer
fresh acceptance from an absolute control comparison.

1. `python3 rust-cpython/perf.py doctor`; `python3 rust-cpython/perf.py
   fetch` once for the Django closure. If `rust-cpython/.cargo-home` is
   missing, run `python3 rust-cpython/build.py fetch` first.
2. `perf.py status`. Rebuild `perf-upstream` with `--empty-overlay` only
   when it is missing, unverified, or the source pin or toolchain changed.
   Verify the accepted named `<ACCEPTED_REF>` against its recorded runtime
   source, overlay and toolchain. Rebuild only if missing, unverified or changed;
   docs-only commits do not invalidate it. Keep candidates on their own branch.
3. `perf.py test --name <ACCEPTED_REF> --all`, unless `status` already records
   `all-passed` for that same accepted runtime identity. It must match the
   macOS baseline counts from `rust-for-cpython.md` (resource denials and
   platform skips only).
4. Require `CALIBRATION-OK`; reuse its saved receipt when measurement code,
   options and verified baseline identity are unchanged. Otherwise run
   `perf.py calibrate --ref @control --gate --memory-only` in the memory phase.
   On failure, report the differing rows and investigate inputs or sampling;
   do not raise the floor or wait for quietness as a memory prerequisite.
5. `perf.py goals --candidate <ACCEPTED_REF> --memory-only` in the memory
   phase. Its table is the debt map: OVER modules are targets, largest ratio
   first; rerun `goals --candidate <ACCEPTED_REF> --module M --memory-only`
   for UNCLEAR modules before briefing a lane. MISMATCH is a correctness finding for the user, not a
   lane.
6. `perf.py bench --baseline @control --candidate <ACCEPTED_REF> --gate
   --all-workloads --memory-only` for the memory-phase application picture.
   CPU-phase setup retains its calibration and quiet-host requirements.

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
- A lane's work on a module ends when its assigned phase metrics are MET or
  BEYOND; it continues
  toward 0.9x only when no OVER module is waiting for a lane.
- If two unchanged memory-lane comparisons regress only load footprint while
  verified source/flags match and working peak and outputs remain neutral,
  you may authorize exploration despite the setup failure. Record both verdicts
  as measured; do not correct ratios or relax acceptance guards. Such a lane
  needs a primary-path batch gate to establish acceptance. The setup failure
  alone does not count as a failed optimization hypothesis while this recovery
  is active.
- In the CPU phase, the same recovery applies after two unchanged comparisons whose only
  regressions are startup-bound workload wall/CPU rows within the documented
  1% to 3% worktree-path bias, with neutral module memory/CPU, other guards,
  and matching outputs. Verify identical source and compiler policy and each
  installed library against its own Cargo artifact. Preserve both REJECTs;
  acceptance still requires an actual primary-path batch gate.
- In the CPU phase, a replicated CPU setup difference on an unchanged route may be resolved by
  a fresh primary-path paired guard comparison. Verify unchanged route sources
  and compiler policy, matching outputs, and every route metric neutral in
  both primary runs. Preserve the worktree REJECTs and the primary evidence;
  authorize exploration only. The changed route still needs its own primary
  batch memory improvement, complete suites, and every regression guard.
- Repeated unchanged startup RSS setup regressions may be resolved with a
  fresh clean primary build of the entire unchanged overlay and compiler
  policy. Require matching outputs, every target metric neutral in both
  primary runs, and all seven primary workload guards neutral under the
  existing replicated verdict. Preserve individual run results, including
  a guard that worsens in only one run, and both worktree REJECTs. This
  authorizes exploration only; the changed candidate still requires its
  own primary memory improvement, complete suites, and all guards.
- Reserve owned overlay paths per lane before spawning. Two lanes never
  edit the same route. Shared `overlay/Cargo.toml`, `overlay/Cargo.lock`,
  and `overlay/Modules/Setup.local` edits are allowed; you reconcile them.
- The current memory run permits up to **31 child agents plus the root
  coordinator**. The CPU-phase limit remains **4** climbers; the separate
  coverage cap and Claude policy are unchanged. Use independent source,
  baseline-fixture and review work to fill useful lanes, not repeated closed
  mechanisms. Build/test commands on separate stages may overlap through
  their shared leases; RSS measurements remain exclusive. Allocate `--jobs`
  against concurrent builders and host CPUs, not the number of reasoning
  agents. Each worktree costs about 3 GB; retain the disk rule.
- Climbers never edit `benchmarks/` or `rust-cpython/perf_modules.py`: they
  are the measuring stick. If a kernel misses part of its route's
  checklist behavior, fix the kernel yourself in a separate commit before
  the lane starts, rerun `goals --module M`, and say so in the ledger.
- New agent worktrees branch explicitly from `main`, whose overlay must match
  the verified `perf-rust` incumbent. A temporary integration branch in the
  primary checkout does not prevent filling a free slot: use `git worktree add
  <path> -b <lane-branch> main`, verify its source against the incumbent, and
  never inherit the unaccepted integration branch. Once `main` advances, wait
  for its incumbent rebuild before spawning further lanes.
- Before spawning a batch, commit on `main` everything the lanes need and
  confirm `perf-rust` is built at `main` HEAD: worktrees branch from `main`
  and the gate check requires the challenger to contain the incumbent
  commit.

After the worktree paths, Codex skill path, and model restriction, include
these domain fields in each climber brief:

```text
LANE: <lane name, a-z0-9 and hyphens; also the perf build name>
TARGET: <module route; plus any application workload that exercises it>
GOAL NOW: <MEMORY ONLY: load_footprint/working_peak status and ratios; CPU phase: all three metrics>
ROUTE: <checklist item and Rust crate, e.g. zlib / overlay/Modules/_zlib_rs>
HYPOTHESIS: <measured cost from your profile and the change expected to cut it>
OWNED PATHS: <overlay paths this lane may edit>
SUITES: <every complete suite from the checklist line, plus neighbors the change reaches>
INCUMBENT: <main HEAD commit that @incumbent was built from>
JOBS: <N>
ATTEMPTS: <explore attempts before qualifying or giving up; default 6>
```

## Memory exploration and acceptance

Use `--memory-only` for memory exploration, calibration, goals and gates.
CPU/wall rows and host quietness cannot block setup, qualification or completion.
Keep the memory floors, paired replication, output checks and coverage guards.
Acceptance requires a replicated target memory improvement with no replicated
memory regression, mismatch or unstable metric, a clean committed build and
complete correctness. Record adverse individual runs even when the final
replicated verdict is neutral. Exploration alone is not adoption.

Prepare observable regression fixtures and run them on a verified accepted
stage before implementation. Reuse unchanged baseline evidence. Explore with
compatible incremental builds, native invariants and complete affected suites;
screen known memory regressions before broader targets and workloads. Only
survivors proceed to final clean/full qualification. Cargo/build-system changes
that incremental builds refuse still require a clean build.

No blanket packet, materializer or separate wrapper approval is required for
ordinary authorized execution. Preserve exact source, stage, artifact and
receipt identity; resolve a concrete missing check rather than regenerating
unchanged evidence. Keep same-stage commands sequential. Independent source,
review, fixtures and build/test work on separate stages may overlap while the
host lease protects exclusive memory sampling.

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
- relaunch a lane as a new climber from a dead or stopped lane's branch:
  first check whether the Codex agent is still available; relaunch only
  when it cannot continue. Commit its uncommitted edits as a WIP
  commit, then brief the new lane with the branch name and "treat the WIP as
  unverified".

Never, without a person: push; remove a Rust route or weaken a suite; edit
`Lib/test/`, `benchmarks/`, or `perf_modules.py` (except fixing a kernel
gap, Lanes rule); touch `main` history other than adding commits. Record the
blocked step under the debt list or a finding and continue with other work.

**Quiet host (CPU phase only).** CPU-phase acceptance, calibration and
baseline recording require `quiet=yes`. Memory work follows Memory exploration
and acceptance above and never waits for quietness. Before each CPU-phase run, wait:
`python3 .agents/skills/rust-cpython-perf/scripts/wait_quiet.py 180` as an
exec session (exit 0 = quiet, 1 = 180 minutes without a quiet sample);
resume it with bounded `write_stdin` calls. Recalibrate
(`calibrate --ref @control --gate`) at session start,
after every 6 hours of wall time, and after any host change; `CALIBRATION-OK`
with `quiet=yes` is required first. A verdict that reads INCONCLUSIVE only
for `quiet=no` is neither a failure nor an empty batch: keep the branch and
its worktree and re-gate later. If four consecutive waits time out, stop and
report `host never quiet` with the CPU branches waiting for a gate. A CPU
result on an unquiet host never counts.

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
resets that module's count, even when the module is still OVER. Debt is a
scheduling record, not a completed memory goal.

**UNCLEAR rows.** Rerun `goals --module M --profile rigorous` once. Still
UNCLEAR: treat it as OVER when the pooled median exceeds 1.01x and brief a
lane, otherwise as MET and note it in the ledger. Never loop on it.

**Budget and disk.** Stop and report after 150 lanes in a session. Never
spawn a lane when `df -h .` shows under 20 GB free; sweep first, and stop and
report if the sweep cannot recover space.

**Shared costs.** When a lane's FINDINGS name another route's import or
first-call cost that shows up in three or more modules (for example `_re_rs`
loading at import), brief one `gpt-6-luna` / `xhigh` climber lane owning that
route, ahead of the per-module lanes it would help, then rerun `goals` for the
affected modules.

## Integration

Each climber returns a handoff block. Integrate only `RESULT: ACCEPT` lanes
whose gate verdict you have read in the `GATE:` file. Memory acceptance uses
`--memory-only` and the Memory exploration and acceptance criteria; it has no
quiet-host or CPU/wall prerequisite. A lane with explicitly authorized
load-only setup recovery may also be evaluated in a primary-path batch when
its completed suites pass and its worktree gate has no regression outside
load footprint. Preserve the actual worktree decision. This is permission to
build and judge the batch, not acceptance: only the primary-path batch gate
can establish an improvement and permit integration of that lane.

1. Rebase or merge the accepted lane branches onto `main` in one batch and
   reconcile shared files. Regenerate one `Cargo.lock` when crates changed
   and inspect the package set before building. Do the merge on an
   `integrate-N` branch, not on `main` (fast-forward `main` only after the
   batch gate ACCEPTs); when crates changed, run `python3
   rust-cpython/build.py fetch` there to populate its cargo home, and after
   integrating copy that cargo home's new crates to the primary checkout the
   same way before building the next candidate.
   **Where to integrate.** Lane builds sit at long worktree paths, and gates of
   lane builds against the primary-path `@incumbent` showed a 1% to 3%
   `import_django` wall/CPU bias (a `zstd-glue` REJECT on that guard vanished
   when the same code was built and gated in the primary checkout). So build
   and gate the batch (`perf-merge`) in the primary checkout on a temporary
   `integrate-N` branch, not in a worktree; then `git checkout main && git
   merge --ff-only integrate-N`. A lane REJECT whose only regressed rows are
   1% to 3% `import_django` (or other startup-bound guards) with no
   plausible mechanism is re-decided by that primary-path batch gate.
2. Use a unique candidate build name; `perf-merge` below is a placeholder,
   never the name of a retained accepted stage. Run `perf.py build --name
   perf-merge`; check that it printed `OK` (never chain
   a gate or suite behind an unchecked build; both refuse a failed one).
   Lanes hand-edit `overlay/Cargo.lock`, and two edits in different places
   merge textually but can leave a lock that `cargo fetch --locked` rejects
   (`cannot update the lock file`). Fix: in `work/perf/perf-merge/source/cpython-*/`
   run `env CARGO_HOME=<primary>/rust-cpython/.cargo-home <cargo-home>/bin/cargo
   metadata --offline --format-version 1` (no `--locked`), copy that
   `Cargo.lock` to `overlay/Cargo.lock`, commit it, and rebuild. Then
   `perf.py test --name perf-merge
   --all`. On failure, split the batch into smaller lane groups, drop or repair
   the interacting lane, and repeat. Keep the coordinator and lane agents at
   `gpt-6-luna` / `xhigh` throughout.
3. `perf.py bench --baseline <ACCEPTED_REF> --candidate perf-merge --gate
   --module <each lane module> [--workload <lane workloads>]`. The batch
   integrates only on ACCEPT; memory gates use `--memory-only` without
   CPU/wall or quiet-host prerequisites.
   On REJECT, bisect by lane; a lane that regresses a guard when combined
   goes back to its owner or is dropped.
4. Commit the integration on `main` (message below). Retain the already
   qualified primary candidate's named stage, report, source commit and
   verification receipts as `<ACCEPTED_REF>`. Check source ancestry and the
   verified runtime identity; do not rebuild, rename or retest solely to
   materialize a canonical `perf-rust`, and do not clean the accepted candidate.
5. `perf.py goals --candidate <ACCEPTED_REF> --memory-only --min-idle 0
   --module <each lane module>` in the memory phase; CPU-phase goals use the
   normal idle default without `--memory-only`. At memory completion, run the
   complete module goals and absolute workload memory comparison with
   `--memory-only`; no debt row or quiet-host wait waives that proof. CPU
   baseline recording retains its quiet-host requirement. Update the ledger and goal table in
   `rust-for-cpython-perf.md`. Commit the refreshed
   `benchmarks/baselines/rust-cp316-perf-*.json`, ledger, and goal table
   together. Run complete `perf.py goals --candidate <ACCEPTED_REF>
   --memory-only` every third memory integration to catch cross-module drift;
   CPU-phase goals omit `--memory-only`.
   Lanes still running when `main` advances: message each with the retained
   accepted named ref and source `INCUMBENT`, telling it to merge the source
   before Qualify if the ancestry check fails. New lanes use that same verified
   ref and source identity; docs-only commits do not require rebuilding it.
6. Clean up every lane's worktree as soon as its branch is merged (or
   abandoned), in the same integration, before spawning the next batch. Each
   worktree carries its own APFS-cloned caches, Cargo home, build trees
   (`work/perf/<lane>/`), and stage prefix, so leftovers exhaust the disk.
   For each lane: `git worktree remove --force <path>` (this deletes its
   builds), `git branch -d <lane-branch>` (merged branches only), then
   `git worktree prune` and confirm with `git worktree list`. Also
   clean only superseded candidate builds in the primary checkout. Never
   remove the retained accepted stage/report. Keep a
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

- Memory completion: a complete memory-only `perf.py goals` reads every
  module's load footprint and working peak MET/BEYOND, and a complete
  `@control` workload comparison reads every peak RSS neutral or improved.
  Debt and unresolved UNCLEAR rows do not satisfy completion. No quiet-host
  confirmation is required. Only then end or advance the memory phase.
- CPU completion: every module reads MET/BEYOND on all three metrics or is on
  the CPU debt list, and every gate workload is neutral/improved against
  `@control` or has two failed workload lanes. CPU quiet-host policy remains.
- In the CPU phase, two consecutive batches integrate nothing, excluding an
  INCONCLUSIVE result solely for `quiet=no`; or `host never quiet` is reported.
- The lane budget or disk floor from Unattended operation is reached. Report
  these operational limits separately; they do not complete unresolved goals.

A workload that reads above `@control` in the CPU phase gets its own lane
(for example `zlib_decode_1m` through the zlib and gzip routes); a module win
does not close it.

Report the final goal table, the `@control` versus `@incumbent` workload
table, the ledger rows added this session, open debts, and any lane
findings worth another try.
