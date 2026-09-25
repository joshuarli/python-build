---
name: rust-cpython-coordinator
description: Coordinate up to 16 parallel Rust-for-CPython stdlib coverage ports using isolated worktrees, real source overlays, and CPython Python-level tests. Use for delegated work under rust-cpython/ or rust-for-cpython.md.
---

# Rust-for-CPython coverage coordination

This skill supersedes `orchestrate` for this lane. The root agent owns the
checklist in `rust-for-cpython.md`, worktree assignment, shared-file merges,
full-suite integration, and coverage verdicts. Production CPython 3.14.6
is outside this lane. Performance starts only after all 71 coverage items
are complete.

## Fan out by module

- Run up to **16 module agents** concurrently. Prefer `gpt-6-luna` at
  `xhigh` for implementation. Reserve `gpt-6-sol` at `medium` or `high`
  for difficult C-ABI, concurrency, semantic, or integration problems. Give
  each agent one distinct module, public behavior, and affected CPython suites.
  Spawn with `fork_turns: "none"` and a self-contained brief. Children do not
  spawn further agents. Before spawning, reserve expected source paths and
  public behavior in the coordinator's working context; schedule coupled
  modules together or sequentially so two agents do not rewrite one route.
- Create a unique branch and Git worktree before an agent edits. Every agent
  uses its own worktree as `workdir`. Keep module-specific files under
  `rust-cpython/overlay/` and commit actual `.rs`, Python, C, and Cargo
  source there. No patch manifests, embedded source strings, or ignored
  directories as the sole copy. Register new extension crates through
  `overlay/Modules/Setup.local`; the builder copies it into the build tree.
  Shared `Cargo.toml`, `Cargo.lock`, and `Setup.local` edits may appear in
  separate branches; the root
  agent owns their final reconciliation. Agents leave the shared checklist
  untouched; the root checks items only after integrated qualification.
  When branches add crates, merge their exact manifest constraints and
  regenerate one lockfile for the combined source; inspect the changed
  package set before the integrated fetch and build.
- Share only verified immutable input cache bytes, for example by linking
  each worktree's ignored `.cache` to the warmed primary cache. Keep build,
  stage, Cargo target, logs, and test output private to each worktree.
  Schedule build jobs according to available CPUs, memory, and disk rather
  than letting 16 compilers saturate the host. Use `build --jobs N` and
  `test --jobs N` to divide capacity. Agents can edit while builds queue.
- Do not commit lane assignments, scout status, handoffs, repeated evidence
  ledgers, or generated build output. Put the focused suite verdict in the
  implementation commit message; no separate report file is needed. Remove
  completed worktrees after integration to reclaim disk. Never push without
  instruction.

## Correctness hill climb

1. Use the recorded passing full-suite baseline instead of rebuilding the
   pristine fork in every lane. Before each port, identify every relevant
   unchanged CPython test module or package. Run a pristine focused suite
   only when its expected platform skips need clarification. An agent may
   run a small subset for feedback, then
   must run the full relevant module suites with `build.py test --suite
   test_NAME` before handing off. Compare platform skips with the baseline.
2. Prefer maintained Rust libraries for formats and algorithms. Check their
   compatibility, license, maintenance, and dependency closure. Vetted Rust
   crates are preauthorized in this isolated lane when pinned in committed
   `Cargo.lock` and their compatible licenses are recorded. Other dependency
   types still require consultation. Keep public Python object, exception,
   callback, and state semantics at the CPython boundary.
3. Build only debug CPython: no PGO, LTO, benchmark, or Rust tests. Do not
   write Rust tests. A private extension or passing test subset alone gives
   no coverage credit. The named public behavior must reach Rust.
4. The root agent integrates completed module branches in a small batch,
   reconciles shared files, builds the combined interpreter, and runs
   `build.py test --all`. If it fails, isolate the interacting change and
   repair or revert it. Mark a checklist item complete only after its full
   relevant module suites **and** the integrated default-resource CPython
   suite pass.
   Baseline platform/resource skips are acceptable; new skips and claimed
   module feature skips are not.
5. In the module commit message, state Rust-owned public behavior, supported
   target, any added crate and license, exact debug build and focused-suite
   commands, pass/skip counts, and baseline platform skips. The root adds
   the integrated full-suite verdict beside each checked checklist item.
   If a route fails, retain a concise finding only when it changes the next
   decision.
   Remove abandoned scaffolding and continue with another module. Refill
   finished lanes until every checklist item is qualified; ordinary failures
   trigger repair or a different module, not a coordinator status cycle.
