# Linux x86_64 lane bring-up

Question: can the isolated Rust-for-CPython 3.16 lane build, validate, and
test the same pinned fork, patches, and controls on x86_64 glibc Linux, so
the macOS evidence can be repeated on a second platform?

Answer: yes, with recorded platform differences. All six lane builds
(candidate, unpatched fork, no-Rust, vanilla upstream, zlib hybrid, full
zlib-rs) completed offline with the locked LLVM 23.1.2, ThinLTO, and
CPython's `-m test --pgo` profile task. The candidate passed the Cargo
workspace tests and the targeted CPython tests. The broad regression suite
ran 50,567 tests in 496 files, and one file failed: `test_socket`, with two
vsock errors that also fail on vanilla upstream on this host (see
[Open items](#open-items)). This does not change the product: the
CPython 3.14.6 build, the frozen Linux musl recipes, and `bootstrap.lock.json`
are untouched.

## Host and inputs

| Item | Value |
| --- | --- |
| Host | Ubuntu 24.04.4 LTS on KVM, 4 vCPUs (Intel Xeon @ 2.10 GHz, 1 thread per core), 15 GiB RAM, no swap, glibc 2.39 |
| Target | `x86_64-unknown-linux-gnu`, `-march=x86-64 -fPIC -O3` |
| C toolchain | Official `LLVM-23.1.2-Linux-X64.tar.xz`, SHA-256 `b5ed9675…95b7`, 2,013,958,032 bytes; Sigstore statement SHA-256 `4e2a296c…df10`. Same tag (`llvmorg-23.1.2`), source commit (`85ac5602…47fb`), and release workflow as the macOS archive. Selectively extracted: 634 MiB prefix |
| Linker | The archive's `ld.lld` via `-fuse-ld=lld`. It needs ICU 70 (`DT_NEEDED`, `RUNPATH $ORIGIN/../lib`), which Ubuntu 24.04 lacks. Jammy `libicu70_70.1-2_amd64.deb` (SHA-256 `58a154f6…fd9a`) is pinned; its digest was checked through `Packages.gz` against the gpgv-verified jammy `InRelease` |
| Rust | `nightly-2026-09-15` (`rustc 1.100.0-nightly 574ff7d98`, LLVM 23.1.1), private Cargo home, offline |
| Host packages | Exact dpkg versions pinned in [`linux-toolchain.lock.json`](../linux-toolchain.lock.json) and checked by `doctor`; `libzstd-dev` was installed with apt |
| Sources | The locked fork and upstream archives. `codeload.github.com` is denied by this environment's egress policy, so both were rebuilt from their commits with `git archive --format=tar --prefix=<repo>-<commit>/ \| gzip -n`. Both reproduced the locked SHA-256 **byte for byte** (`965dbc9c…1467`, `7b8b6853…c7f`); `lane_linux.fetch_source` does this automatically, and a mismatch is still rejected |

`_decimal` is missing from every Linux build, controls included. The pinned
3.16 sources no longer bundle libmpdec, and Ubuntu 24.04 main has no
`libmpdec-dev`; the only candidate on this image is a third-party PPA, which
was not added. Decimal falls back to `_pydecimal`. Decimal-heavy timings are
therefore not comparable with a build that has `_decimal`.

## Build recipe and boundary

`build.py` selects the target from the host. On Linux it uses a lane-local
`LaneTarget`; the production target table is unchanged. Configure receives
`CFLAGS=-O3 -march=x86-64 -fPIC`, `LDFLAGS=-fuse-ld=lld
-Wl,-rpath,<prefix>/lib`, empty `CPPFLAGS`/`PKG_CONFIG_PATH` (the system
pkg-config path), `--enable-shared --with-lto=thin --enable-optimizations
--enable-experimental-jit=no --with-tail-call-interp=no --without-ensurepip`,
and `PROFILE_TASK=-m test --pgo -j 3` (host CPUs minus one, as on macOS).
Cargo's linker is the locked clang. The no-Rust and upstream controls
use the same flags with their own prefixes.

Configure, build, and install run under `unshare --user --map-root-user
--net`. The namespace has no interface up, not even loopback. A self-test
connects to a loopback listener owned by the builder: the probe connects
outside the namespace and fails with `ENETUNREACH` inside it. Unlike the
macOS `sandbox-exec` profile, writes are not restricted. Build reports
record this boundary.

Validation checks, on the installed bytes: the Rust `_base64` module is
x86-64 ELF, exports `PyInit__base64`, and matches `binascii` on the
representative vectors; the interpreter links `libpython3.16.so.1.0` with the
prefix runpath; **every** installed ELF's runpath is either absent or the
build's own `<prefix>/lib`; no dependency or runpath names a build-tool
location. For zlib variants, the lane checks: the platform `libz.so.1` for
`binascii` and the hybrid; prefixed `python_build_rs_inflate*` symbols
without unprefixed zlib entry points in the hybrid; and zlib-rs runtime
identity `1.3.0-zlib-rs-0.6.7` for the full backend.

## Defects found and fixed during bring-up

1. **URL patch parallel-build race.** `0001-rust-url-quote.patch` added
   `Modules/_rust_url_quote/module.c` but not the directory to configure's
   `SRCDIRS`. Out-of-tree `make -j3` compiled `module.o` before the
   archive rule's `mkdir -p` ran (`unable to open output file`). The macOS
   `-j9` builds were ordered favourably. The regenerated patch adds the
   directory to `configure` and `configure.ac`; it otherwise produces a
   byte-identical tree. The same revision replaces the hard-coded
   `rustc --target=aarch64-apple-darwin` with the fork's own
   `$(if $(CARGO_TARGET),--target=$(CARGO_TARGET))` convention (native
   builds: the host). Manifest SHA-256: `38a12dea…a2cc0`.
2. **`$ORIGIN` runpath destroyed in the Rust module.** The fork's `_base64`
   cargo rule passes `BLDSHARED_ARGS="$(BLDSHARED_ARGS)"` inside a double-quoted
   shell word, so `-Wl,-rpath,'$$ORIGIN/../lib'` became `/../lib` in that
   module only (79 other ELFs were correct). Linux now uses an absolute
   per-prefix runpath, like the macOS absolute install names. A stage-wide
   runpath check prevents regression.
3. **Inherited ignored SIGINT changed the PGO task.** A shell starts
   background jobs with SIGINT/SIGQUIT ignored (`SigIgn 0x6`), CPython then
   leaves SIGINT ignored, and `test_generators.SignalAndYieldFromTest`
   failed in the profile task. That failed the build, and it would otherwise
   have made the profile depend on how the builder was launched. The lane
   builders now restore default dispositions before running any command.
4. **Host proxy variables in the regression environment.** This session's
   `HTTPS_PROXY` made two `test_urllib` host-validation tests fail through
   `urlopen`'s proxy tunnel path. The lane's test environment now drops proxy
   variables; the sealed build environment was already an allowlist.

## Build resources

GNU `time -v`; CPU is the waited process tree (user + system seconds);
max RSS is the largest single process.

| Build (attempt) | Elapsed | User + system CPU s | Max RSS |
| --- | ---: | ---: | ---: |
| Candidate, URL + guarded zlib patches (5) | 5:23 | 941.5 + 56.1 | 1.28 GB |
| Unpatched fork, `--variant prior-fork --no-patches` (3) | 5:26 | 948.6 + 56.8 | 1.31 GB |
| No-Rust fork control (2) | 5:07 | 884.3 + 52.5 | 1.38 GB |
| Vanilla upstream merge base (2) | 5:02 | 865.0 + 51.7 | 1.28 GB |
| zlib hybrid, `--variant zlib-hybrid --zlib-hybrid` (2) | 5:08 | 889.5 + 54.7 | 1.27 GB |
| Full zlib-rs, `--variant zlib-rs --zlib-rs` (2) | 5:11 | 894.4 + 58.7 | 1.30 GB |

Earlier attempts are retained in `logs/resources/` (ignored). Candidate
attempt 1 hit the parallel-build race after 77 s. Attempt 2 compiled fully
(5:17, 924.7 + 53.4 CPU s) but failed the first, too-strict runpath check.
Attempt 3 succeeded with an `$ORIGIN` runpath and was superseded after
defect 2 was found. Attempt 4 and every build in the first control queue
failed in the profile task because of the inherited SIGINT; for example,
`build-prior-fork-2` stopped after 2:38 (401.8 + 31.2 CPU s).

## Correctness

| Check | Result |
| --- | --- |
| URL differential (`url-quote-installed-check.py` → lean `check.py`), control parser = pristine locked `Lib/urllib/parse.py` SHA-256 `178fce6b…d825` | **2,177/2,177** public cases matched; exactly one native call on the eligible probe |
| Installed candidate `urllib/parse.py` | SHA-256 `85ac4db3…acee`, identical to the macOS candidate |
| `test_urlparse test_urllib -j1` (proxy variables unset) | 182 run, 7 skipped, success (same counts as macOS) |
| Subinterpreter import + direct/public calls | Passed |
| zlib hybrid vs platform zlib 1.3, 876 encodings | **876/876** byte-equal; both sides cross-decode all 876 |
| Full zlib-rs vs platform zlib 1.3 | 666/876 byte-equal (**210 differ**, the same count as macOS against zlib 1.2.12); all cross-decode |
| `test_zlib test_gzip test_tarfile test_zipfile test_zipimport test_binascii` on hybrid and on full zlib-rs | 1,892 run, 35 skipped, success on both (macOS: 1,892 run, 39 skipped) |
| Candidate `build.py test`: Cargo workspace | Passed |
| Candidate targeted CPython tests | 3,268 run, 374 skipped, 7/7 files |
| Candidate broad regression, `-j 3` | 50,567 run, 3,036 skipped; 467 OK, `test_socket` failed (2 host vsock errors; the same on upstream), 28 skipped, 9 resource-denied |

## Installed size

| File | Installed bytes | After `llvm-strip --strip-debug` |
| --- | ---: | ---: |
| `zlib` extension, platform | 133,400 | 56,440 |
| `zlib` extension, hybrid | 5,985,976 | 1,834,816 (+1,778,376) |
| `zlib` extension, full zlib-rs | 5,983,040 | 1,831,992 (+1,775,552) |
| `_rust_url_quote` extension | 22,776 | 9,592 |
| `_base64` (Rust) extension | 416,128 | 413,952 |

The hybrid's debug-stripped growth is 1.78 MB on Linux, compared with
1.45 MB on macOS.

## Open items

- `test_socket` failed with two errors in the broad regression run:
  `ThreadedVSOCKSocketStreamTest.testStream` times out and then raises
  `OSError: [Errno 19] No such device`. This VM exposes `/dev/vsock`
  without a working vsock transport. Re-run in isolation, the candidate,
  the unpatched fork, and vanilla upstream all fail the same two errors
  (750 run, 276 skipped). It is a host limitation, not a candidate
  regression. Logs are in ignored `results/linux/test_socket-*.log`.
- Timing and memory results are recorded separately in
  [`linux-comparison-20260925.md`](linux-comparison-20260925.md).
