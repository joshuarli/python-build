# Optional whole-build zlib-rs candidate

The Rust-for-CPython 3.16 builder now accepts `--zlib-rs` on `fetch` and
`build`. The default `build` remains the platform-zlib control. This candidate
uses the same `libz-rs-sys-cdylib` 0.6.7 archive and Cargo.lock pinned by
`rust-cpython/zlib-proof/sources.lock.json`; there is no new source pin or
dependency. Production CPython 3.14.6 is outside this experiment.

Run, when the coordinator schedules a heavy build on a quiet host:

```text
python3.14 rust-cpython/build.py fetch --zlib-rs
python3.14 rust-cpython/build.py build --zlib-rs
```

`fetch` verifies the crate archive and caches locked Cargo dependencies.
`build` freshly extracts the verified archive, checks the package name,
version, license, static library declaration, and Cargo.lock digest, then
builds its static archive with pinned nightly Rust, `--locked --offline`, and
the existing network-denial sandbox. The absolute archive path becomes
CPython configure's `ZLIB_LIBS`. This changes the link input for the existing
`Modules/zlibmodule.c`; it does not patch that C source. The builder requires
the configured Makefile to retain the archive path.

The build report at `rust-cpython/results/build.json` records the source-lock
hash, crate archive hash and size, Cargo.lock hash, built static archive hash
and size, and installed `zlib` extension hash. Before reporting success, the
builder imports the installed module in isolated mode, round-trips a payload,
checks zlib-rs's runtime version, verifies that the module came from the stage
tree, rejects a dynamic `libz` dependency, and checks that the extension
defines three zlib C ABI symbols. A missing cache input, changed lockfile,
failed build, or platform-zlib fallback fails the candidate build.

This integration has only been reviewed and syntax checked. No whole CPython
build, Cargo build, fetch, benchmark, or CPython test has run in this worktree.
The whole-build correctness and resource verdict therefore remains
**inconclusive** until the coordinator runs the candidate and no-Rust control
under the same pinned source and validates the installed tree.
