# Guarded URL quotation: patched full build qualification

## Result

The pinned macOS Rust-for-CPython build completed with the guarded URL
quotation source patch applied. The installed `_rust_url_quote` extension and
`urllib.parse` route passed the focused semantic checks below. This qualifies
the candidate's build and behavior; a paired performance comparison is a
separate quiet-host measurement.

This lane used branch `exp/rust-cpython-url-full-build-retry-20260924p` at base
`0e94ebb` in `/private/tmp/python-build-exp-url-full-build-retry-20260924p`.
The source archive was the locked 44,210,863-byte object with SHA-256
`965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`
and fork commit `b812b4a7b9efaca46b98544a8633b7d7e454166b`. The patch SHA-256
was `77d02738c4e4b8ebe2fcb2fbdc16a016abfc8069d7257459ff785671c9a5f4f9`;
`Cargo.lock` remained at its locked SHA-256
`55f5f3bf547d3b9e7896a5feb6d17aa3b607610c7c21d919164f0877a8d05023`.

## Patch and native build gates

Before compilation, `_extract_fresh()` created a separate, verified source
tree and `_apply_source_patches()` applied the manifest patch. A pre/post hash
assertion found all seven patch target paths changed: `Lib/urllib/parse.py`,
`Makefile.pre.in`, `Modules/Setup.stdlib.in`,
`Modules/_rust_url_quote/module.c`, `Modules/_rust_url_quote/quote.rs`,
`configure`, and `configure.ac`. The two module files were newly created.
The helper's reverse-application check passed. In particular, parser SHA-256
changed from the unpatched `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`
to `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee`.
This gate rules out the prior build's silent zero-file patch application.

Verified `.cache` and `rust-cpython/.cargo-home` were APFS-cloned from the
earlier isolated build worktree. The private `doctor` reported `ok: true`
with no problems. `python3 rust-cpython/build.py build` then configured,
compiled, and installed CPython 3.16.0a0 natively on arm64 macOS. Its
`rust-cpython/results/build.json` says `status: built` and records the patch
manifest. The configured `Modules/Setup.stdlib` selected `_rust_url_quote`;
the generated Makefile listed it among shared modules and contained the
private archive dependency and link flags. The build log contains the pinned
`rustup run nightly-2026-09-15 rustc` archive command and extension bundle
link. ThinLTO and the default nine-worker `-m test --pgo` profile task ran
through the build driver.

The installed `urllib/parse.py` has the same SHA-256
`85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee`
as the gated patched source. The installed
`lib-dynload/_rust_url_quote.cpython-316-darwin.so` has SHA-256
`5f00a07bbcc282659e1258d0509c1e117f9db185cf94f867aeb809736f616916`.
An isolated interpreter imported both from this lane's stage, confirmed
`urllib.parse._rust_url_quote is _rust_url_quote`, and returned `a%20b` for
`quote_from_bytes(b'a b', '')`.

## Semantic evidence

The existing `url-quote-lean-proof/check.py` differential harness ran through
the installed candidate interpreter. Its control parser path was substituted
in memory with the prior unpatched installed parser, whose SHA-256 was
verified as `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`.
All **2,177** public `quote_from_bytes`, `quote`, and `quote_plus` cases
matched, including exception type/message cases, byte subclasses, bytearray,
safe values, and the guard threshold. Instrumenting the extension's Python
method attribute observed exactly one native call for the eligible public
probe; the two fallback or early-exit probes made no native call.

The installed `python3.16 -I -m test test_urlparse test_urllib -j1` succeeded:
**182 tests ran, 7 skipped**. A complete registered catalog operation
processed 48 URLs and 48 keys and returned pinned input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
This single operation is a correctness smoke, not timing evidence.
`_interpreters.create()` plus `run_string()` imported both modules in a
subinterpreter and passed direct extension and public parser calls.

Both candidate and prior control installed `parse.cpython-316.pyc` files
exist with checked-hash flags `3`; each header hash matches
`importlib.util.source_hash()` of its own `parse.py`. Candidate cache SHA-256
is `5953842c30178f7269a4c94a854020b658b90bd37d3a5a2f862b4b96203365fd`
and control cache SHA-256 is
`1566ce6071cde3cd2f0aa7f9acf130122bfb54cb9bb4146c8a53737bd1b40d9a`.

## Resource accounting

`/usr/bin/time -l` supplied elapsed, user CPU, system CPU, maximum resident
set size, and swap counts for significant commands. CPU is kernel-accounted
for each command's waited process tree. Maximum RSS is the largest reported
process peak, not simultaneous aggregate or unique/proportional memory.
Short inspections, `doctor`, and cache-header checks were not timed.

| Command | Wall | User CPU | System CPU | Peak RSS | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: |
| APFS clone input cache | 0.11 s | 0.00 s | 0.09 s | 1,441,792 B | 0 |
| APFS clone Cargo cache | 0.75 s | 0.01 s | 0.62 s | 1,392,640 B | 0 |
| Fresh extraction and seven-path patch gate | 2.81 s | 1.04 s | 1.49 s | 44,007,424 B | 0 |
| Native configure, build, install, driver validation | 293.29 s | 722.93 s | 113.76 s | 1,779,793,920 B | 0 |
| Installed identity/public route | 0.04 s | 0.02 s | 0.01 s | 22,642,688 B | 0 |
| 2,177-case public differential | 0.13 s | 0.10 s | 0.01 s | 29,523,968 B | 0 |
| CPython URL tests | 0.76 s | 0.48 s | 0.11 s | 52,903,936 B | 0 |
| One catalog operation | 0.06 s | 0.03 s | 0.01 s | 25,477,120 B | 0 |
| Subinterpreter smoke | 0.04 s | 0.02 s | 0.01 s | 22,888,448 B | 0 |

The timed commands total **840.71 CPU seconds** and **297.99 seconds wall**;
their largest per-process RSS was **1,779,793,920 bytes**, within the lane's
approximately 2,000 CPU-second and 4 GB observed-peak budgets. System swap
usage was 259.88 MB before and during the build; `/usr/bin/time -l` reported
zero swaps for every timed command. These fields do not establish an
aggregate-memory ceiling or capture every short-lived subprocess peak.

**Disposition:** keep as a build-qualified, semantically passing candidate.
The paired performance and memory comparison is **pending** because an
unrelated `rustc` job was active on the host after these checks. The
coordinator owns that separate quiet-host verdict and integration decision.
