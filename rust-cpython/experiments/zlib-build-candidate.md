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
and size, and installed `zlib` and `binascii` extension hashes and sizes. Before reporting success, the
builder imports the installed module in isolated mode, round-trips a payload,
checks zlib-rs's runtime version, verifies that the module came from the stage
tree, rejects a dynamic `libz` dependency in either extension, and checks
that both extensions define zlib C ABI symbols. A missing cache input, changed lockfile,
failed build, or platform-zlib fallback fails the candidate build.

## One whole-build result, 2026-09-24

The locked fetch populated this worktree's private cache with CPython source
`965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`
and zlib-rs crate archive
`09ab8373154ca2cd2ba61b44dcf28bcb91733f1f7652ce96a502c5ae3b7ca702`.
The copied LLVM archive `d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1`
and its attestation `6c07293849e05e3cfae150a6f0ec7d2153af40f570c36a48801a82b87f74e7cb`
passed `_llvm_ready` verification in this worktree. Cargo dependencies were
fetched into the private `.cargo-home`, then the candidate build ran offline
with network denied by `sandbox-exec`.

The first invocation stopped after configure because the new guard queried
`ZLIB_LIBS`, which this CPython Makefile does not emit. The effective recipe
was correct: `MODULE_ZLIB_STATE=yes`, and `MODULE_ZLIB_LDFLAGS` and
`MODULE_BINASCII_LDFLAGS` both named the pinned static archive. The guard now
checks those effective module variables. The next invocation completed the
full PGO build and install. `/usr/bin/time -l` measured each command's
waited process family; RSS is its maximum reported process RSS, not a
simultaneous sum across all compiler children.

| Command | User CPU s | System CPU s | Elapsed s | Max RSS bytes | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Locked `fetch --zlib-rs` | 2.57 | 2.42 | 10.16 | 52,166,656 | 0 |
| First `build --zlib-rs`, stopped at guard | 52.23 | 31.54 | 112.21 | 230,096,896 | 0 |
| Completed `build --zlib-rs` | 748.89 | 120.49 | 315.58 | 1,790,361,600 | 0 |

The three command totals are 803.69 user plus 154.45 system CPU seconds,
958.14 CPU seconds. The host's swap allocation remained 356.38 MiB during
the build. The completed build used CPython source commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b`, nightly Rust
`2026-09-15`, LLVM 23.1.2, Xcode 26.6 / SDK 26.5, `-mcpu=apple-m1`,
macOS 26.0 deployment, ThinLTO, release Cargo, and
`PROFILE_TASK="-m test --pgo -j 9"`. The source patch manifest was empty;
`Modules/zlibmodule.c` retained SHA-256
`36390fc1b0bdaf7da332d732c67cbe9669bd3f6e923a3e5810b4662159a0e20c`.
The built `libz_rs.a` SHA-256 was
`354f64c7596c4b0a65813ee8bd264bb802c13a11d96677cd0f28f8c7583fad83`
(18,948,304 bytes).

The installed `zlib` reports header version `1.2.12` and runtime version
`1.3.0-zlib-rs-0.6.7`. It is 1,674,056 bytes, SHA-256
`0259414fe8a42d46169685b694781262bb616103f162a6526e0af5090f899ccd`,
and defines `zlibVersion`, `deflateInit2_`, and `inflateInit2_`. Installed
`binascii` is 1,668,928 bytes, SHA-256
`f29bd13c19a6768324a8a97ec75f274ba3d3bb2927ded0b11a5f87c4626bc1ae`,
and defines `crc32`, `adler32`, and `zlibVersion`. Each extension lists only
`/usr/lib/libSystem.B.dylib` dynamically. Both contain the static backend,
so their combined installed size is 3,342,984 bytes before distribution
stripping; a matched control size comparison remains to be done.

**Verdict:** the optional full candidate build and installed backend identity
are established. The build's own import and roundtrip passed. No separate
CPython or Cargo test suite, no no-Rust control build in this worktree, and no
timing benchmark ran. Broader semantic and performance qualification remains
open.
