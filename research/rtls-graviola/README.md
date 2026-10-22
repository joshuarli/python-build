# RTLS and Graviola research

## Decision

Keep OpenSSL in the production distribution. Keep RTLS and Graviola in this
separate research lane until they pass the compatibility, trust-policy, and
payoff gates below. The prototype does not add a production dependency, change
the product CPU baseline, or change the product TLS API.

The current OpenSSL recipe passes `no-apps no-tests` and retains its existing
`build_sw` and `install_sw` targets. The distribution uses the static
`libssl` and `libcrypto` libraries. It does not ship OpenSSL's command-line
applications or test programs. The native arm64 Alpine production dependency
build passed with LLVM 23.1.3 and installed both libraries without an OpenSSL
command. No before-and-after timing comparison was run, so this change has no
measured build-time claim. OpenSSL documents these configuration options in its
[3.5.7 installation guide](https://github.com/openssl/openssl/blob/openssl-3.5.7/INSTALL.md).

## Why the prototype uses RTLS

The [`rust-cpython/overlay` experiment](https://github.com/joshuarli/python-build/tree/4752d8eda0cd3166bd042d994216b4f2a03137e9/rust-cpython/overlay)
demonstrates Rust-backed CPython object implementations, but its `_ssl_rs`
module delegates TLS operations to OpenSSL. Its `_hashlib_rs` and `_hmac_rs`
modules cover only part of CPython's hashing surface and retain RustCrypto
dependencies. That lane also targets a 3.16 development fork. It does not
provide a production-ready OpenSSL replacement for CPython 3.15.1.

[RTLS](https://github.com/jawah/rtls/tree/302423b49e494863d07630d50b15a9488ec85ef7)
provides a Python-level `ssl` adapter over rustls. The experiment pins its
2026.10.3 tag to commit `302423b49e494863d07630d50b15a9488ec85ef7` and replaces
the native AWS-LC provider with
[`rustls-graviola` 0.4.0](https://crates.io/crates/rustls-graviola/0.4.0),
which uses Graviola 0.4.1. The source pin, dependency changes, Rust adapter
changes, and lockfile update are in
[`rtls-graviola.patch`](rtls-graviola.patch).
The recorded licenses are in
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md). The patch removes the
RTLS AWS-LC native build crates and adds Graviola plus target support crates.
It does not measure Rust build time or extension size.

The provider exposes rustls cipher suites, key exchange groups, signature
operations, verification algorithms, and random bytes. It has no HPKE
provider. The patch therefore disables RTLS's ECH setup and returns an error
when a caller supplies ECH configuration. ECH support is an explicit gap.
The patch keeps the existing ring provider and ECH behavior for WASI builds;
the Graviola dependency is limited to non-WASI targets.

The Python `SSLContext` adapter subclasses CPython's standard-library context.
The prototype therefore does not prove that a product can remove CPython's
`_ssl`, `libssl`, or `libcrypto`. Native extensions that call OpenSSL remain
outside this Python-level adapter's compatibility boundary.

## What the local prototype proves

The Rust adapter compiled on native Apple Silicon macOS. A Python 3.15.0
process completed two verified TLS 1.3 socket exchanges using the adapter's
Graviola client. One server used the RTLS Graviola provider. The other used
the host Python's standard-library OpenSSL implementation. Each exchange
trusted RTLS's test root certificate, checked the `localhost` name, and
round-tripped a payload over loopback.

The run used Rust 1.99.1, rustls 0.23.45, `rustls-graviola` 0.4.0, and
Graviola 0.4.1. The build used `kache` as the compiler wrapper. The exact
commands are in [REPRODUCE.md](REPRODUCE.md).

This result establishes a narrow TLS handshake and socket-interoperability
path. It does not qualify CPython 3.15.1, a production toolchain, or any Linux
target. It does not establish the product's default CA selection, certificate
chain policy, or OpenSSL compatibility. No performance or archive-size result
was measured.
No amd64 verification was performed from this arm64 host; use native amd64
qualification rather than treating emulation as equivalent evidence.

## Compatibility gaps

RTLS is beta and its project prioritizes clients over servers. Its current
surface omits several CPython 3.15.1 interfaces, including signature-algorithm
and supported-group getters and setters. Session exposure and post-handshake
client authentication also differ from CPython's OpenSSL-backed module.

RTLS's [verifier configuration](https://github.com/jawah/rtls/blob/302423b49e494863d07630d50b15a9488ec85ef7/rust/src/config.rs)
maps `VERIFY_X509_TRUSTED_FIRST` and `VERIFY_X509_PARTIAL_CHAIN` to the same
trust-anchor behavior. OpenSSL assigns these flags different meanings. The
product enables strict and partial-chain verification in
`ssl.create_default_context()`, so this difference requires a certificate-path
security review before adoption.

RTLS's [context code](https://github.com/jawah/rtls/blob/302423b49e494863d07630d50b15a9488ec85ef7/src/rtls/_context.py)
loads operating-system roots through `wassima`. Its CA loading does not match
the product's OpenSSL-first source contract. It scans CA directories by file
extension rather than using OpenSSL's hashed-directory lookup. The prototype
did not test the product's rules for explicit empty or invalid `SSL_CERT_FILE`
and `SSL_CERT_DIR` values, isolated `-E` and `-I` startup, empty default files,
hashed directories, or the bundled fallback.

The product's native-extension boundary also matters. A Python package can
use an alternate `ssl` module while a binary extension still imports
`libssl`, `libcrypto`, or `_ssl` internals. A Python-level adapter does not
provide those symbols or OpenSSL-owned object layouts.

## Separate hashing investigation

Do not combine a TLS prototype with a `hashlib` replacement. CPython already
ships built-in implementations for its guaranteed digest algorithms, so an
OpenSSL-free experiment can begin by inventorying which behavior needs a
replacement. The missing surface includes PBKDF2, scrypt, OpenSSL-named
constructors, and native `_hashlib` consumers. Preserve `hmac`,
`compare_digest`, `usedforsecurity`, digest copying, and documented
constructor and keyword behavior.

The isolated `rust-cpython/overlay` `_hashlib_rs` and `_hmac_rs`
implementations are useful examples of Rust-backed Python objects, but they
target a different CPython tree and use RustCrypto. They are not Graviola
integrations and are not dependencies of this prototype. Any hashing work
should be an independent patch with its own API inventory and CPython tests.
Keep OpenSSL's public C symbols available if native consumers remain part of
the product contract.

## Other replacement routes

The OpenSSL ABI compatibility route is not ready. The
[`rustls-openssl-compat` matrix](https://github.com/rustls/rustls-openssl-compat/blob/main/MATRIX.md)
marks `SSL_read_ex` and `SSL_write_ex` as unimplemented, marks
`SSL_CTX_set_ciphersuites` as a stub, and leaves certificate and session
operations incomplete. It also retains OpenSSL `libcrypto`, so it cannot
remove OpenSSL from this distribution.

Replacing `_hashlib` alone also does not remove most OpenSSL build work.
CPython supplies guaranteed digest implementations in built-in modules, but
[`_hashopenssl.c`](https://github.com/python/cpython/blob/v3.15.1/Modules/_hashopenssl.c)
provides PBKDF2, scrypt, OpenSSL named algorithms, and a native interface used
by extensions. A replacement must preserve [`hashlib.py`](https://github.com/python/cpython/blob/v3.15.1/Lib/hashlib.py)
and `hmac` behavior without silently losing those functions.

## CPU and platform policy

Keep the current Linux baselines: `-march=x86-64` and `-march=armv8-a`. Keep
the macOS Apple M1 baseline. Do not raise them for Graviola until a complete
replacement demonstrates a material benefit and runs on the proposed floor.
Graviola documents a Broadwell-class feature requirement on x86-64. The
candidate's Rust compilation must observe the same CPU contract as its C
build, and startup must reject unsupported machines if the selected build
requires more than the product baseline.

Graviola 0.4.1 declares Rust 1.89, Rust 2024 edition, and the license
expression `Apache-2.0 OR ISC OR MIT-0`. `rustls-graviola` 0.4.0 declares Rust
1.85. The upstream project has test-vector, fuzzing, and constant-time test
work; formally verified routines cover selected cryptographic code, not the
whole TLS stack or this Python adapter. This review did not establish an
independent audit of the complete project or an upstream musl qualification
for both product architectures.

The current prototype ran only on Apple Silicon macOS. It did not build the
Linux musl targets. Its Rust compilation used the Rust compiler's default
target CPU settings, not the product's C target flags. Before proposing Linux
support, qualify native
`x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl` builds using the
locked Alpine toolchains and the approved product CPU floors. Check static
linking, runtime assumptions, architecture requirements, and unexpected
dynamic dependencies.

Graviola's [compatibility table](https://github.com/ctz/graviola/blob/v/0.4.1/COMPATIBILITY.md)
lists Broadwell as its x86-64 floor. That is a candidate constraint for a
future build, not a reason to change the product baseline today.

For a future native build, `-march=broadwell` is a candidate x86-64 minimum;
`-march=armv8-a+crypto` is a candidate Linux arm64 baseline after checking the
exact Rust and C compiler output on supported hardware. Apple M1 remains the
macOS floor. These are investigation points, not accepted product settings.
A compiler flag alone does not prove that every binary stays within its
declared CPU floor.

## Adoption gates

Keep production on OpenSSL until a candidate meets all of these conditions:

1. Preserve the CPython 3.15.1 `ssl`, `hashlib`, and `hmac` APIs that the
   distribution supports. Cover guaranteed digests, HMAC, `compare_digest`,
   PBKDF2, scrypt, copy behavior, and keyword semantics.
2. Pass the relevant CPython TLS suites for client and server operation,
   including TLS 1.2 and 1.3, ALPN, SNI, mutual TLS, certificate failures,
   hostname and IP checks, nonblocking I/O, `MemoryBIO`, orderly shutdown,
   and abrupt EOF. Resolve ECH, session resumption, and post-handshake
   authentication as explicit support decisions.
3. Match the product trust-source rules for normal and isolated startup.
   Test environment overrides, OpenSSL defaults, CA files, hashed directories,
   the bundled PEM, relocation, and the opt-out.
4. Build and run on all three production targets with the locked toolchains
   and current CPU floors. Inspect unresolved symbols, runtime dependencies,
   and native-extension behavior.
5. Measure a clean build against the `no-apps no-tests` OpenSSL baseline.
   Include dependency and interpreter build time, peak scratch space,
   stripped extension sizes, and the final compressed artifact size. Keep the
   replacement only when its compatibility cost has a measurable return.

Record every unsupported API and intentional difference before changing the
product contract. Treat test-only success as research evidence, not release
qualification.

Resume this as staged work: close the Python TLS and trust-policy gaps in an
isolated RTLS fork; qualify the Graviola provider on product Rust/C toolchains
for each target; then evaluate any independent hashing replacement. A failure
at an earlier stage should not trigger a product CPU-floor change or an
OpenSSL ABI-shim project by default.
