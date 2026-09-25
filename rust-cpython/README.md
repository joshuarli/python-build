# Rust-for-CPython coverage lane

This isolated lane builds the pinned Rust-for-CPython CPython **3.16.0a0** fork.
Its current goal is complete Python-level stdlib module coverage, defined in
[`rust-for-cpython.md`](../rust-for-cpython.md). Performance work is deferred
until that checklist is complete; see the inactive
[`rust-for-cpython-perf.md`](../rust-for-cpython-perf.md).

The production CPython 3.14.6 build, packaging, and frozen Linux recipes are
outside this lane. The lane supports native macOS arm64 and Linux x86-64.
Linux arm64 is in scope but its builder is not implemented. Windows, Intel
macOS, and all other targets are unsupported; the builder rejects them.

The verified source is `Rust-for-CPython/cpython` commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b`, pinned with its archive
and Cargo lock digests in [`sources.lock.json`](sources.lock.json). The Rust
toolchain is pinned in [`rust-toolchain.toml`](rust-toolchain.toml). The
private Cargo home is used offline after fetching. Do not update the source,
toolchain, or Cargo lock as a side effect of an experiment.

## Active commands

```sh
python3 rust-cpython/build.py doctor
python3 rust-cpython/build.py fetch
python3 rust-cpython/build.py build
python3 rust-cpython/build.py test --suite test_bz2
python3 rust-cpython/build.py clean
```

`build` now configures CPython with `--with-pydebug`, no PGO or LTO, C/C++
`-O0 -g3`, and the fork's Cargo `dev` profile. It runs offline and installs
`stage/bin/python3.16d`. `test` accepts repeated `--suite test_NAME` options
and runs only those complete CPython Python test modules or packages. It
does not run Cargo tests or the whole interpreter suite. Choose every suite
relevant to the public behavior before editing; a passing subset is not a
coverage result. Each agent's Git worktree has its own build and stage tree.

For a candidate, commit a source diff as a `.patch` file in the worktree,
then pass the same `--patch PATH` to `fetch` and `build`. `fetch` caches any
approved Cargo dependencies from the patched `Cargo.lock`; `build` checks
that lock offline. The patch digest is recorded in the generated build
report. The active builder has no PGO or benchmark mode.

## Porting and evidence

Use a maintained Rust library where its semantics fit. Consult the user
before adding dependencies. Keep CPython's Python and C-ABI boundaries
where they carry public object, callback, or exception behavior. A private
Rust extension counts only when the named public module behavior reaches it
and its full relevant Python suite passes.

Develop in a committed branch and isolated worktree. Keep candidate source
or a reproducible source patch in Git. A final checked-in result needs only
the candidate identity, supported target, exact debug build and full-suite
commands, pass/skip counts, and any pre-existing platform skips. Generated
interpreters, compiler output, and raw test logs remain ignored. Avoid
per-attempt records and coordinator bookkeeping commits.

`linux-toolchain.lock.json` pins the x86-64 LLVM and Ubuntu package inputs.
The macOS lane uses the root `bootstrap.lock.json` LLVM 23.1.2 and Xcode SDK
identity. `fetch` verifies inputs; build and install use an offline boundary
with a network-denial self-test. The Linux boundary uses user and network
namespaces; macOS uses `sandbox-exec`.
