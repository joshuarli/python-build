---
name: rust-cpython-coordinator
description: Coordinate parallel Rust-for-CPython stdlib experiments in this repository, with isolated worktrees, resource accounting, and evidence-based integration. Use for work under rust-cpython/ or rust-for-cpython.md that delegates experiments to subagents.
---

# Rust-for-CPython experiment coordination

This skill supersedes the general `orchestrate` skill for Rust-for-CPython
experiments in this repository. The root agent is the coordinator and owns
the shared objective in `rust-for-cpython.md`, experiment selection,
worktree assignment, integration, and the final verdict. Child agents own
bounded experiments. Keep the production CPython 3.14.6 build and frozen
Linux recipes outside these lanes.

## Fan-out and ownership

- Use the smallest useful fan-out, with at most **six active experiment
  subagents**. Prefer `gpt-6-sol` at `medium` reasoning for every experiment.
  Spawn with `fork_turns: "none"` and a self-contained brief. Do not let
  children delegate further unless the coordinator explicitly assigns a
  nested budget within the same six-agent cap.
- Before spawning an editing agent, the coordinator creates a unique Git
  worktree outside the primary checkout and assigns it an absolute path and
  branch. An agent runs every file command with that worktree as `workdir`.
  Give each lane exact owned paths, its deliverable, checks, and stop condition.
  No two agents edit the same source or docs. Read-only scouting can share a
  checkout, but may not mutate it.
- Keep generated `rust-cpython/work/`, `stage/`, `.cargo-home/`, and transient
  logs inside the lane's own worktree. Do not share writable
  build outputs or use the primary checkout as scratch. A common verified
  input cache is acceptable only if its publication and reads are atomic and
  content checked; otherwise copy inputs into the lane.
- Before an expensive build with an authored source patch, check that every
  intended path actually changed in a fresh extracted tree. A successful
  `git apply` exit status can still mean zero files were patched when Git
  discovers the enclosing worktree. Verify source hashes and installed
  identities again after the build.
- Track active ownership, worktree, budget, and merge order in the coordinator's
  working context or an ignored local note. **Do not commit lane assignments,
  status updates, or scout bookkeeping.** Reassign a path only after its prior
  owner stops. Inspect a lane's diff and evidence before integrating; apply
  one lane at a time and resolve interactions against the current mainline.
  Rebuild or remeasure after integration when changes can interact. Do not
  push without explicit user instruction.

## Commit discipline

- Keep coordination lightweight. A read-only scout can report its verdict in
  a message; it needs no report file or commit merely to say that an idea was
  deferred. Commit a scout result only when it adds reusable, decision-changing
  evidence that future experiments need to reproduce.
- Prefer one coherent commit for an implementation and its decisive evidence.
  A standalone evidence commit is appropriate for a substantial benchmark or
  qualification result. Do not make separate assignment, status, handoff, and
  documentation-sync commits around the same experiment. Update the main plan
  and candidate map when a decision changes, grouping those edits with the
  relevant result when practical.
- An experiment is not finished until its source or patch, exact build and
  workload recipe, all numerical observations, and relevant failure excerpts
  are committed. Store compact data and one short verdict beside the source.
  Stage trees and compiler output can be rebuilt; they do not belong in Git.
  Do not leave the only copy of a result under `/private/tmp`, an ignored
  directory, or a discarded worktree. Preserve rejected findings concisely
  in the next substantive decision record. Do not integrate a negative
  scout's branch solely to archive ceremony.

## Resource and measurement discipline

- The six-agent limit is a ceiling, not a build concurrency target. Check
  free memory, swap pressure, CPU load, and running builds before launching
  work. Do not run published timing comparisons concurrently with another
  benchmark, compiler, PGO job, or other CPU-heavy lane on the same host.
  Queue heavy builds and benchmarks when they would interfere.
- For substantial build or benchmark commands, record **kernel-accounted
  user and system CPU seconds** for the command's process tree, separately
  from elapsed time. Record peak resident and, where available, unique or
  proportional memory, plus swap and process count. Note the measurement
  method and coverage of short-lived children. Never infer CPU consumption
  from wall time or treat missing memory as zero.
- Give every attempt, including failed and discarded calibrations, a unique
  ID in checked-in compact data. Keep outcome, paired order, output identity,
  wall and kernel CPU, memory, swap, and relevant failure text directly in
  the record. Put the shared command and environment once in the recipe;
  do not repeat absolute worktree paths or `stdout_path`/`stderr_path` fields
  per attempt. For `benchmarks/bench.py` quick or standard native runs, pass
  `--evidence rust-cpython/experiments/data/<result>.json` to export one
  compact checked-in observation file without automatic baseline snapshots.
  If a record is lost, state which attempt is missing and do not claim a
  complete lane resource cost.
- For workload performance, wall time still measures user-visible latency;
  CPU time measures compute consumption. Report both per logical work unit.
  A faster wall time with more CPU work or more memory is a visible tradeoff.
  Use separate uninstrumented timing, external memory, and allocation passes
  as specified in `rust-for-cpython.md`. Pair equivalent control/candidate
  work on the same quiet host and retain raw observations and noise bounds.
- When a candidate changes installed Python source, verify the source and
  bytecode-cache state on both sides before measuring. A stale checked-hash
  `.pyc` in a no-write environment forces source compilation at every fresh
  import and can dominate startup RSS. Regenerate valid caches for both sides
  outside measured processes, or make both sides run from source; record the
  policy and cache identities with the result. `PYTHONDONTWRITEBYTECODE=1`
  prevents writes but does not prevent existing `.pyc` reads; audit actual
  imports before claiming a source-only comparison.
- `~/d/rustybench` can inform a focused Rust kernel experiment. Its current
  `AllocProfiler` wraps `GlobalAlloc` and Rust 1.100's `Allocator`, so it can
  count global or collection-local Rust allocation requests in a separate
  diagnostic. Use the same toolchain and allocator in both arms, and keep its
  instrumented elapsed time out of speed verdicts. It currently reports Linux
  process CPU/resource fields and marks the macOS resource extension
  unsupported. It cannot count CPython C allocations or replace end-to-end
  Python workload qualification. The experiment lane pins an earlier nightly;
  do not silently change that pin or add rustybench as a dependency.

## Experiment handoff

Brief each agent with the hypothesis, existing baseline, exact owned files,
worktree, allowed build activity, correctness checks, benchmark workload,
CPU/memory evidence to collect, and the condition for stopping or reverting.
Have the agent report commit or diff identity, raw results, semantic failures,
resource limits, and an explicit keep/reject/inconclusive recommendation.
The coordinator reconciles conflicting results and decides what enters the
integrated branch. Preserve rejected findings in the experiment record.
