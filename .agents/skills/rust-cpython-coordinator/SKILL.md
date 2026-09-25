---
name: rust-cpython-coordinator
description: Coordinate parallel Rust-for-CPython stdlib coverage ports using isolated worktrees and complete CPython Python-level test suites. Use for delegated work under rust-cpython/ or rust-for-cpython.md.
---

# Rust-for-CPython coverage coordination

This skill supersedes the general `orchestrate` skill for this lane. The root
agent owns the coverage checklist, worktree assignment, integration, and the
final coverage verdict. Keep the production CPython 3.14.6 build outside the
lane. Follow `rust-for-cpython.md`; the performance phase is deferred until
its checklist is complete.

## Assign independent modules

- Use the smallest useful fan-out, at most **six active experiment agents**.
  Prefer `gpt-6-sol` at `medium` reasoning. Give each agent a self-contained
  module brief with owned paths and complete CPython Python test suites.
- Create a unique Git worktree and branch before an editing agent starts.
  The agent runs every file command there and commits candidate source on
  that branch. Do not assign overlapping source or docs. Keep build outputs
  in that worktree; never put the only source copy under `/private/tmp` or
  an ignored directory.
- The root agent inspects and integrates one completed lane at a time. Resolve
  interactions and rerun affected complete Python suites after integration.
  Do not commit assignments, scout status, handoffs, or repeated ledgers.
  Never push without explicit user instruction.

## Coverage verdict

- Choose important modules with tractable full suites. Identify all relevant
  unchanged CPython test modules or packages before implementation. Run the
  baseline once to identify existing platform failures and expected skips.
- Prefer a maintained Rust library for the algorithm or format. Check
  compatibility, maintenance, license, and dependency closure. Consult the
  user before adding a dependency. Keep Python-visible objects, exceptions,
  callbacks, and state behavior correct.
- Use the default debug build: no PGO, no LTO, Cargo `dev`. Run only complete
  named CPython Python suites with `build.py test --suite test_NAME`. Do not
  write or run Rust tests. Do not run pyperformance, benchmarks, profiles, or
  CPU/memory comparisons during this phase.
- Count a module only when its named public behavior reaches Rust and every
  relevant Python suite passes fully on a supported native host. Ordinary
  platform skips are acceptable; feature-gap skips are not. Commit source,
  exact build/suite command, target and candidate identity, pass/skip counts,
  and a short verdict together. No per-attempt report files are needed.
- A partial or failed route remains unchecked. Keep a concise finding when
  it changes the next decision; remove abandoned scaffolding. Stage trees,
  raw compiler logs, and test logs are rebuildable and stay outside Git.
