# Rust-for-CPython coverage lane

This isolated lane builds the pinned Rust-for-CPython CPython **3.16.0a0** fork.
Its current goal is 71 named public-behavior coverage targets, each gated by
the complete relevant CPython Python module suites, as defined in
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
toolchain, or Cargo lock accidentally; intentional vetted crate additions
update the overlay lockfile.

## Active commands

```sh
python3 rust-cpython/build.py doctor
python3 rust-cpython/build.py fetch
python3 rust-cpython/build.py build
python3 rust-cpython/build.py test --suite test_bz2
python3 rust-cpython/build.py test --all
python3 rust-cpython/build.py clean
```

`build` now configures CPython with `--with-pydebug`, no PGO or LTO, C/C++
`-O0 -g3`, and the fork's Cargo `dev` profile. It runs offline and installs
`stage/bin/python3.16d`. `test` accepts repeated `--suite test_NAME` options
and runs only those complete CPython Python test modules or packages.
`test --all` runs all CPython test modules under the test runner's default
resource policy on the integrated tree. Each test file has a 900-second
timeout. Neither command runs Cargo tests. Choose every suite relevant to the
public behavior before editing; a passing subset is not a coverage result.
Each agent's Git worktree has its own build and stage tree. `build --jobs N`
and `test --jobs N` let the coordinator divide CPU capacity among lanes.

For a candidate, edit real source files under `overlay/`, using paths relative
to the pinned CPython source root. The builder copies those files over a
fresh verified source extraction before Cargo fetch and build. For example,
`overlay/Modules/_bz2_rs/src/lib.rs` could hold a future Rust codec source.
Put Rust in `.rs` files, Python in `.py` files, and C integration in C or
header files. For a new extension, put its module declaration in
`overlay/Modules/Setup.local`; the builder copies it to CPython's build
directory after configure. Do not embed Rust source in
Python strings or patch hunks. An edited `Cargo.lock` is an ordinary overlay
file and `fetch` caches its approved dependencies; `build` checks it
offline. The overlay refuses changes under `Lib/test/`, keeping the CPython
suite unchanged. The generated build report records one digest for the overlay.
The active builder has no PGO or benchmark mode.

## Porting and evidence

Use a maintained Rust library where its semantics fit. Vetted Rust crates
with compatible recorded licenses and pinned `Cargo.lock` entries are
preauthorized for this isolated lane. Keep CPython's Python and C-ABI boundaries
where they carry public object, callback, or exception behavior. A private
Rust extension counts only when the named public module behavior reaches it
and its full relevant Python suite passes.
Check a public import and representative call in a CPython subinterpreter
before handing off a candidate. Single-phase private extensions can reject
loading there, so their public wrapper must use a compatible fallback or the
extension must support multi-phase loading. Assert that
`_interpreters.run_string()` returns `None`; an exception in the child is
returned as a value and can leave the parent process exit status at zero.

Develop in a committed branch and isolated worktree. Keep candidate source
in Git under `overlay/`. Put the public Rust route, crate licenses, target,
focused-suite command, and pass/skip counts in the implementation commit
message. The coordinator records the integrated full-suite result beside
the completed checklist item. Generated interpreters, compiler output, and
raw test logs remain ignored. Avoid per-attempt reports and coordinator
bookkeeping commits.

`linux-toolchain.lock.json` pins the x86-64 LLVM and Ubuntu package inputs.
The macOS lane uses the root `bootstrap.lock.json` LLVM 23.1.2 and Xcode SDK
identity. `fetch` verifies inputs; build and install use an offline boundary
with a network-denial self-test. The Linux boundary uses user and network
namespaces; macOS uses `sandbox-exec`.
