# RTLS and Graviola research

## Current implementation

The isolated macOS arm64 candidate builds CPython 3.15.1 with compiled `_ssl`
and `_hashlib` explicitly disabled in `Modules/Setup.local`. OpenSSL is absent
from its native dependency graph. A separate fetch phase supplies checked,
locked Rust sources; the build runs with network access denied. The installed
`ssl` and `_hashlib` facades load their native adapters under `-I -S` after
relocation to a path containing spaces. Production remains unchanged.

The consolidated patch includes the v7d development checkpoint and the later
repairs described below. Fresh source preparation at that checkpoint matched
the candidate's executable RTLS, webpki, and rustls sources byte for byte. This is an OpenSSL-free development distribution,
not a qualified release artifact. The final stripping, pruning, archive, and
extracted-artifact qualification remain outstanding.

`policy.rs` checks the actual webpki-verified leaf, intermediates, and original
trust anchor. It validates strict extension policy, issuer identifiers, anchor
constraints, and validity. Rejected paths can yield to another verified path.
Maintained webpki and Graviola implementations perform signature verification.
`TRUSTED_FIRST` controls issuer preference; only `PARTIAL_CHAIN` permits an
explicitly trusted intermediate to terminate the path. Invalid DER cannot
become a trust anchor, and root classification checks the self-signature.

The 82-case differential corpus matches pinned OpenSSL 3.5.7 acceptance under
the same flags, including the original missing-AKI and malformed-chain defects.
The missing-CA-SKI fixture independently reaches OpenSSL verification error 86.
Duplicate critical extensions are rejected during candidate loading rather
than reference verification; the harness records this earlier rejection.
Certificate expiration includes the exact `notAfter` second. Canonical issuer
names govern issuer selection, cycle detection, self-issued path-length checks,
and CRL authority checks without changing signed bytes or keys.

Legacy RSA/SHA1 root self-signatures use x509-parser's maintained Ring-backed
verification API only during implicit-anchor classification. This restores valid
Mozilla roots without enabling SHA1 for certificate paths or TLS signatures.
The paired legacy-root test and all 82 security cases pass after this change.
A root with a corrupted self-signature remains rejected, although OpenSSL
accepts its explicitly trusted copy without checking that self-signature.
This deliberate restriction preserves the experiment's cryptographic
self-signed-anchor invariant and remains a documented compatibility difference.

Certificate and key ingestion validates complete PEM blocks and DER before
committing state. Eight paired PEM tests cover malformed footer suffixes,
allowed whitespace, surrounding text, and first-key selection. The public
`load_cert_chain()` accepts filesystem paths, matching CPython. Four paired
MemoryBIO tests cover contiguous buffers, byte counts, integer bounds, and EOF.

Offline CRL checking uses authoritative PEM CRLs loaded through `cafile` and
checks selected path certificates and anchors. Missing CRLs, revoked certificates,
invalid signatures, expiration, and future `thisUpdate` values fail verification.
`cadata` loads certificates only. Hashed-directory `.r0` CRLs, online fetching,
and delta or indirect CRLs are unsupported.

The 14-case trust-source contract passes with the real locked Mozilla bundle.
It covers explicit environment overrides, isolation flags, fallback suppression,
and hashed directories resolved at first use, including additions and removals
before lookup and retained certificates after caching. A malformed hashed file
is rejected atomically; OpenSSL can retain a valid prefix of that file.

SNI context selection preserves the initial connection's verification policy
and selects the callback context's certificates, trust sources, CRLs, cipher
and signature controls. Twelve SNI contract tests pass. Sessions, ALPN, keylog
clearing, socket I/O, and supported ECDH groups have focused upstream and
reference checks. Accepted listening sockets are wrapped with the TLS context.

`ssl_native_compat.py`, installed as `_ssl.py`, provides Python-level metadata
and certificate decoding for consumers such as CPython's own tests. It does
not restore CPython's compiled `_ssl` extension or its native object layouts.
It eagerly exports CPython 3.15.1's integer constants from `ssl_metadata.py`,
and `ssl_facade.py` builds the matching enum classes from those constants.
Backend versions and capability flags remain RTLS-specific. Kernel TLS is
unavailable: `OP_ENABLE_KTLS` is absent. The ordinary TLS `sendfile()`
fallback is still under repair.
`ssl_metadata.py` also contains the CPython protocol-message enums.


The [hashing backend](hashing/README.md) passes complete `test_hashlib` and
`test_hmac` suites: 240 tests, 18 skips. Native extension, limited-API extension,
and shared-libpython embedding probes passed on the preceding candidate;
final extracted-artifact checks must be repeated after integration.

The v7d complete default-resource regression run executed 50,058 tests with
202 failures and 2,936 skips; 547 of 556 selected files ran, with nine
resource-denied files. Its six failing files are `test_asyncio`, `test_audit`,
`test_ftplib`, `test_ssl`, `test_support`, and `test_tools`. The makefile-folder
failures in `test_tools` match an existing product exclusion. The asyncio
subprocess test constructs an unquoted shell command from the relocated path.
The audit failure exercises unsupported finite-field DH parameters. The
remaining failures include actionable API and socket-lifecycle defects.
A preceding run had one additional process-pool failure; its isolated rerun
and the complete replay passed that file, without erasing the initial failure.

The complete `test_ssl` run now finishes: 219 tests, 30 failures, 36 errors,
and 37 skips. The earlier nonblocking-send hang is repaired. Compatibility
work continues on TLS FTP shutdown, error propagation, constructor semantics,
cipher controls, channel binding, and metadata. PyO3 currently prevents both
native adapters from loading in subinterpreters; `hashlib` then loses PBKDF2
and scrypt in a worker. Safe per-interpreter bindings are an active repair,
not a supported feature or a waived requirement.

No macOS 26 runtime or Linux qualification is claimed. No clean build-time,
peak-memory, stripped-size, or compressed-artifact comparison is complete.
The current scope is macOS arm64, and performance gates are waived by the user.
The remainder records the earlier prototype and adoption requirements.

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
The patch keeps the existing ring provider and ECH code behind WASI-specific
configuration; the Graviola dependency is limited to non-WASI targets. The
WASI target is not installed in the tested Rust toolchain, so this is source
inspection, not a WASI build result.

The Python `SSLContext` adapter subclasses CPython's standard-library context
when `_ssl` exists. The first prototype did not prove that `_ssl` could be
removed. The follow-up found and patched a concrete RTLS fallback defect: its
placeholder `_SSLSocket` was not a `socket.socket` subtype, although
`TLSSocket` calls `socket.socket.__new__`. The fallback now imports `_ssl`
first, avoids a partially initialized `ssl` import when `_ssl` is absent, and
uses a socket subtype. `run-no-ssl-contract.sh` verifies that behavior with a
disposable CPython 3.15.1 installation that has `_ssl` removed and `_hashlib`
retained.

## What the local prototype proves

On native Apple Silicon macOS 27, the patched adapter built with Rust 1.99.1,
rustls 0.23.45, `rustls-graviola` 0.4.0, and Graviola 0.4.1. The earlier
Python 3.15.0 smoke completed verified TLS 1.3 loopback exchanges between a
Graviola client and both Graviola and OpenSSL servers.

The stronger follow-up used an isolated CPython 3.15.1 build linked to the
pinned OpenSSL 3.5.7. This probe build used Apple Clang 21 without PGO; it did
not use the production LLVM 23 toolchain or release recipe. After copying it
to a disposable prefix, removing only `_ssl`, retaining `_hashlib`, installing
the RTLS extension, and adding the research `ssl_facade.py` installed as
`ssl.py`, the candidate passed:

- isolated `import ssl`, `import hashlib`, and retained `hashlib.pbkdf2_hmac`;
- TLS 1.3 client/server exchange, `urllib.request.urlopen()` HTTPS, and
  `asyncio` TLS client/server operation;
- rejection of an untrusted issuer, the wrong hostname, and an expired leaf;
- the product-style test-bundle fallback, valid `SSL_CERT_FILE`, hashed
  `SSL_CERT_DIR`, suppression by empty and invalid explicit paths, and the
  bundle opt-out.

The same harness passed against the pinned OpenSSL 3.5.7 reference interpreter.
It is a focused contract probe, not a run of CPython's full `test_ssl` or
`test_asyncio.test_ssl` suites.
The RTLS candidate failed two certificate cases that OpenSSL rejected:
`VERIFY_X509_STRICT` accepted a leaf missing its Authority Key Identifier, and
`load_cert_chain()` accepted a malformed PEM certificate appended to a valid
chain. The harness exits nonzero for these cases. This is a meaningful API
feasibility result, but it fails the required certificate-policy gate.

The CPython 3.15.1 test used a local research facade and a test-only CA file
copied beside `ssl.py`; it did not use the production Mozilla bundle. Direct
RTLS `SSLContext.load_default_certs()` also fails in the candidate because
`wassima` is not installed. The facade supplies the product-style bundled
fallback for this experiment. No Linux target, production artifact,
performance result, or archive-size result was qualified. This Apple Silicon
host performed no amd64 verification.

## Compatibility gaps

RTLS is beta and its project prioritizes clients over servers. Its current
surface omits several CPython 3.15.1 interfaces, including signature-algorithm
and supported-group getters and setters. Session exposure and post-handshake
client authentication also differ from CPython's OpenSSL-backed module.

The candidate's `VERIFY_X509_STRICT` discrepancy is reproduced, not
hypothetical. CPython's 3.15.1 test certificate with a missing Authority Key
Identifier is rejected by OpenSSL 3.5.7 when strict verification is enabled;
RTLS accepts it even when the facade sets the strict flag. RTLS's
[verifier configuration](https://github.com/jawah/rtls/blob/302423b49e494863d07630d50b15a9488ec85ef7/rust/src/config.rs)
also maps `VERIFY_X509_TRUSTED_FIRST` and `VERIFY_X509_PARTIAL_CHAIN` to the
same trust-anchor behavior, although OpenSSL assigns them different meanings.
The malformed-chain case is independently reproduced: RTLS accepts an
invalid PEM item after a valid certificate and key, while OpenSSL rejects the
chain during `load_cert_chain()`.

RTLS's [context code](https://github.com/jawah/rtls/blob/302423b49e494863d07630d50b15a9488ec85ef7/src/rtls/_context.py)
loads operating-system roots through `wassima`; that module is absent from the
OpenSSL-free prefix. Its `set_default_verify_paths()` only handles
environment-specified paths, and `load_verify_locations(capath=...)` scans
filenames by extension instead of implementing OpenSSL hashed-directory
lookup. The research facade supplies the product's bundle fallback and
explicit-source precedence for the test. The harness verified file/hashed
directory inputs and empty/invalid override suppression under isolated Python
startup with both `-I` and `-E -s`, but it does not establish full OpenSSL
path-resolution parity.

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

Keep production baselines unchanged: `-march=x86-64`, `-march=armv8-a`, and
Apple M1. For future Graviola qualification, use separate candidate floors of
Broadwell-class x86-64 and ARMv8-A with crypto extensions; do not require the
candidate to run on legacy production floors that it would explicitly stop
supporting. These candidate floors do not change the production target
registry. Rust and C code must use the same declared CPU contract, and
qualification must run on hardware that satisfies it.

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

The current macOS prototype ran on Apple Silicon and did not exercise the
candidate Linux floors. `-march=broadwell` and `-march=armv8-a+crypto` remain
candidate settings to validate with the actual C and Rust compilers. A compiler
flag alone does not prove that every binary stays within its declared CPU
floor. Do not change production settings until a separate product decision.

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
4. Build and run on all three candidate targets with the locked toolchains and
   candidate CPU floors: Broadwell-class x86-64, ARMv8-A with crypto
   extensions, and Apple M1. Inspect unresolved symbols, runtime dependencies,
   and native-extension behavior. Approve any production baseline change
   separately.
5. Measure a clean build against the `no-apps no-tests` OpenSSL baseline.
   Include dependency and interpreter build time, peak scratch space,
   stripped extension sizes, and the final compressed artifact size. Keep the
   replacement only when its compatibility cost has a measurable return.

Record every unsupported API and intentional difference before changing the
product contract. Treat test-only success as research evidence, not release
qualification.

The certificate-policy gate controls production adoption. It does not stop
repairs in this isolated experiment. Production retains OpenSSL while the
candidate's certificate, trust-policy, hashing, and compatibility checks remain
incomplete. The current implementation scope is macOS arm64. Linux qualification
and performance gates are outside the current request.
