# Optional URL unquote native build qualification, 2026-09-25

## Outcome

**The opt-in source builds and installs successfully.** One full `python3 rust-cpython/build.py build --url-unquote` attempt exited zero under the lane's offline macOS recipe. The installed `urllib.parse` imports the opt-in parser and private `_rust_url_quote` extension from this worktree's stage; the extension exposes `unquote_ascii`. Both complete catalog URL workload digests matched their registered values in one-operation probes. This qualifies build and installed selection, while broad public behavior qualification remains open.

The worktree was `/private/tmp/python-build-exp-url-unquote-build-20260925a` at base `cdc5387`, branch `exp/url-unquote-build-20260925a`. No shared build code, patch, manifest, dependency, production target, formatter, linter, hook, or remote was changed. The build's normal `-m test --pgo -j 9` profile task ran as part of CPython's `--enable-optimizations` recipe; no separate test command or suite was run.

## Host, locked inputs, and fresh source

Host preflight found native arm64 macOS, 32 GiB physical memory, 167 GiB available filesystem space, and 243.88 MiB host swap in use. The process list showed no competing compiler, PGO job, or benchmark. `bootstrap.lock.json` specifies Xcode 26.6 with SDK 26.5; `xcodebuild` and `xcrun` reported those exact identities. The pinned Rust nightly was `nightly-2026-09-15`; LLVM was the verified official 23.1.2 archive. Initial `doctor` found the source and LLVM caches absent from this isolated worktree. They and the 34 MiB private Cargo home were copied with APFS clone copies from the prior isolated URL build lane; a second `doctor` verified the pinned source archive and LLVM cache and reported `ok: true` with no problems. The source archive was 44,210,863 bytes with SHA-256 `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`; `Cargo.lock` matched `55f5f3bf547d3b9e7896a5feb6d17aa3b607610c7c21d919164f0877a8d05023`.

Two fresh extractions under ignored `rust-cpython/work/url-unquote-preflight/` applied the default and opt-in selected patch sets outside Git discovery. The patch application routine required forward checks before applying, reverse checks afterward, and rejection of a second forward application. All 6,035 files and file symlinks were inventoried by bytes or link target. The manifest digest was `9f1ca9cb34eb645ea9dde09c152d988855976d3dd0ea5d8aa55d482adc089adf`; only these three paths differed:

| Source path | Default SHA-256 | Opt-in SHA-256 |
| --- | --- | --- |
| `Lib/urllib/parse.py` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` | `ad11741ef88e9b7175ef0e1ffb311fdee865c073194743e08eb61adee828f4dd` |
| `Modules/_rust_url_quote/module.c` | `727e5b12a8a2e0b8a81be59b86ccb5252f88b1f66c64ca1cbc05ec71448f44df` | `ffd925c31613f4be971e02afa29c891b454e0d348d62d38bf892a54db8259864` |
| `Modules/_rust_url_quote/quote.rs` | `bb9156522ea47140e52e309b501ee3222ed5466fb8b33a779a31566e184fad8c` | `7fd630546e5883e9c5c4fbfa23b2bf7b7a5411da42b866436605c2cea83a2e32` |

## Build and installed identity

`rust-cpython/results/build.json` records `source.patches.url_unquote: true`, the same manifest digest, and selected patch `0004-rust-url-unquote.patch` with SHA-256 `27c0e4c21be013830d253215db25a1f3f04566755a2d5e19e879977ceae033a7`. It records `CARGO_NET_OFFLINE=true`, a passed loopback network-boundary self-test, and `sandbox-exec` with `(deny network*)` for configure, build, and install. Cargo's prerequisite check used `--locked --offline`; the macOS sandbox is weaker containment than a container. Configure used `--with-lto=thin`, `--enable-optimizations`, `--without-ensurepip`, and the locked LLVM clang. The build log shows `llvm-profdata merge` and final `-fprofile-instr-use` compilation. The installed interpreter reports CPython 3.16.0a0, GIL enabled, arm64, and a 26.0 deployment floor.

Installed `lib/python3.16/urllib/parse.py` is 51,565 bytes with SHA-256 `ad11741ef88e9b7175ef0e1ffb311fdee865c073194743e08eb61adee828f4dd`, byte-identical to the patched build source. Installed `lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so` is 51,720 bytes with SHA-256 `dec52fdb6257198c112b0bf475ce5a414b055ad8daa7ea97f8e053c2a5ac5e71`. `file` and `otool` identify an arm64 Mach-O bundle with `LC_BUILD_VERSION` minimum 26.0 and SDK 26.5. `nm -g` reports `_PyInit__rust_url_quote`, `_quote_ascii`, and `_unquote_ascii`. A staged runtime import confirmed the parser and extension paths, the helper's presence, `unquote('%41%FF%ZZ') == 'A\ufffd%ZZ'`, and `quote_from_bytes(b'A /') == 'A%20/'`.

With `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=1`, and the staged interpreter, one complete `catalog_search_form` operation processed 48 records, 48 requests, 48 query parses, and 480 parsed fields. It returned input digest `7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f` and output digest `a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22`. One complete `catalog_url_normalize` operation processed 48 URLs and 48 keys and returned the same input digest with output digest `a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`. These are output probes, not comparative speed measurements.

## Resources and retained evidence

The table covers every timed command attempt in this lane. `/usr/bin/time -l` supplies kernel-accounted user and system CPU for each command tree, including short-lived children; its maximum RSS is the largest lifetime process peak, not unique or simultaneous memory. All raw files are retained under ignored `rust-cpython/logs/` with the shown stems and `.log`/`.time` suffixes. The full build's configure, build, install, and Cargo logs are retained there too.

| Attempt stem | Wall s | User s | System s | CPU s | Max reported RSS bytes | Swaps | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `url-unquote-preflight-20260925a` | 7.04 | 2.49 | 3.73 | 6.22 | 65,126,400 | 0 | 0 |
| `url-unquote-build-attempt-1-20260925a` | 256.80 | 696.95 | 105.45 | 802.40 | 1,785,905,152 | 0 | 0 |
| `url-unquote-installed-probe-20260925a` | 0.04 | 0.02 | 0.01 | 0.03 | 22,855,680 | 0 | 0 |
| `url-unquote-search-probe-20260925a` | 0.08 | 0.05 | 0.02 | 0.07 | 30,244,864 | 0 | 0 |
| `url-unquote-normalize-probe-20260925a` | 0.05 | 0.03 | 0.01 | 0.04 | 25,706,496 | 0 | 0 |
| **Timed total / peak** | **264.01** | **699.54** | **109.22** | **808.76** | **1,785,905,152** | **0** | **all 0** |

The lane stayed below the 1,200 kernel CPU-second and 4 GiB per-process RSS budgets. Host swap remained 243.88 MiB at the later check; `/usr/bin/time -l` reported zero swaps for each attempt. At finish, filesystem space available was 166 GiB; ignored work and stage trees occupied 1.1 GiB and 311 MiB respectively. The initial failed `doctor` and later successful `doctor`, cache clone, static Mach-O inspection, and report preparation were short, untimed read-only or input-provisioning steps, so they are excluded from the timed total. Initial `doctor` output was observed in the tool transcript, not saved to a raw file; its only failures were the absent local source and LLVM caches.

## Remaining gates

Before promoting the optional route, compare public `unquote`, `unquote_plus`, and `parse_qsl` outputs, types, identities, exceptions, and relevant state against the pinned no-Rust interpreter across byte values, malformed escapes, non-ASCII text, subclasses, bytes and bytearray, alternate codecs and errors, no-percent inputs, and long inputs. Decide whether the native route may bypass the parser's private lazy `_hextobyte` initialization and mutable private hooks; the static audit found that difference observable. Focused `test_urlparse` and `test_urllib` suites and a default-selection native control build also remain open. This lane did not perform those gates.
