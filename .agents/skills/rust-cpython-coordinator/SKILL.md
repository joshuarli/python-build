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
- Keep generated `rust-cpython/work/`, `stage/`, `.cargo-home/`, logs, and
  benchmark results inside the lane's own worktree. Do not share writable
  build outputs or use the primary checkout as scratch. A common verified
  input cache is acceptable only if its publication and reads are atomic and
  content checked; otherwise copy inputs into the lane.
- The coordinator keeps a lane ledger: agent, worktree, branch/base commit,
  owned paths, question, expected evidence, status, CPU and memory budget,
  and merge order. Reassign a path only after its prior owner stops. Inspect
  the worktree diff and reports before integrating; apply one lane at a time
  and resolve interactions against the current mainline. Rebuild or remeasure
  after integration when changes can interact. Do not push without explicit
  user instruction.

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
- For workload performance, wall time still measures user-visible latency;
  CPU time measures compute consumption. Report both per logical work unit.
  A faster wall time with more CPU work or more memory is a visible tradeoff.
  Use separate uninstrumented timing, external memory, and allocation passes
  as specified in `rust-for-cpython.md`. Pair equivalent control/candidate
  work on the same quiet host and retain raw observations and noise bounds.
- `~/d/rustybench` can inform a focused Rust kernel experiment. Inspect its
  contract before use; it currently reports Linux process CPU/resource
  fields and marks the macOS resource extension unsupported. It does not
  replace end-to-end Python workload qualification. Do not add it as a
  dependency without the project's required scope decision.

## Experiment handoff

Brief each agent with the hypothesis, existing baseline, exact owned files,
worktree, allowed build activity, correctness checks, benchmark workload,
CPU/memory evidence to collect, and the condition for stopping or reverting.
Have the agent report commit or diff identity, raw results, semantic failures,
resource limits, and an explicit keep/reject/inconclusive recommendation.
The coordinator reconciles conflicting results and decides what enters the
integrated branch. Preserve rejected findings in the experiment record.
