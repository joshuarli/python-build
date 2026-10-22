# Reproduce the RTLS and Graviola experiments

Both replay scripts run on native Apple Silicon macOS. They verify RTLS
commit `302423b49e494863d07630d50b15a9488ec85ef7`, apply
[`rtls-graviola.patch`](rtls-graviola.patch), and build its checked-in Cargo
lockfile with Rust `1.99.1`. Cargo downloads pinned crates; neither script
connects to an external TLS server. Builds and disposable interpreters stay
under `.work/tmp`.

## Graviola socket interoperability

Run:

```sh
research/rtls-graviola/run-poc.sh
```

This builds the extension and runs `local_tls_smoke.py` with a host
`python3.15`. The smoke tests Graviola TLS 1.3 clients against both a Graviola
server and the host Python's OpenSSL server. The recorded run used Python
3.15.0. It is a provider interoperability check, not CPython 3.15.1 or
OpenSSL-removal qualification.

The scripts use `RTLS_RUST_TOOLCHAIN` (default `stable`) through rustup and
stop unless `rustc --version` is exactly `1.99.1`. If `stable` has moved,
install Rust `1.99.1` and set `RTLS_RUST_TOOLCHAIN=1.99.1`. `kache` is
optional: it is used when available unless `RUSTC_WRAPPER` is set explicitly.
Set `RUSTC_WRAPPER=` to disable compiler caching, or set it to a wrapper path
to select one. The script leaves the checkout and build tree available for
inspection.

## CPython 3.15.1 without `_ssl`

Build the native macOS product interpreter from the locked inputs, then pass
its staged install and the extracted source tree's CPython test certificates
to the replay:

```sh
python3 build.py fetch --target aarch64-apple-darwin
python3 build.py build --target aarch64-apple-darwin
research/rtls-graviola/run-no-ssl-contract.sh \
    build/stage/cpython-staged/install \
    build/work/cpython/Python-3.15.1/Lib/test/certdata
```

The script verifies the reference interpreter's exact Python and OpenSSL
versions, copies the installation into `.work/tmp`, builds RTLS for that
interpreter, removes `_ssl` from the copy, and keeps `_hashlib`. It installs
`ssl_facade.py` as the interpreter's `ssl.py` and uses one CPython test CA as
a temporary `python-build-cacert.pem`. The source installation is not changed.

`no_ssl_contract.py` runs against the pinned OpenSSL reference and the
OpenSSL-free copy. It covers socket TLS 1.3, default HTTPS, asyncio TLS,
hostname and issuer rejection, an expired leaf, a malformed chain, strict
verification of a leaf missing its Authority Key Identifier, and the
product-style trust-source cases. It generates the expired leaf locally with
the host `openssl` command and the CPython test CA key. All connections are
loopback only.

The OpenSSL reference command must exit successfully. The current RTLS
candidate is expected to exit `1`: it accepts both the strict-invalid leaf
and malformed PEM chain. That nonzero status is the recorded security gate
failure. The script runs candidate checks with both `-I` and `-E -s`, and
prints the disposable path for inspection.

The test bundle is a single CPython test CA, not the production certifi PEM.
The replay verifies CA source-selection behavior but does not establish the
production bundle contents or OpenSSL hashed-directory semantics. The RTLS
upstream `load_default_certs()` path also imports `wassima`; the experimental
facade supplies the bundled fallback separately.

No Linux musl build, x86-64 verification, production release artifact,
build-time comparison, or archive-size comparison is performed by these
commands. The checked-in patch and harness are research artifacts; the
production build keeps OpenSSL and its existing CPU baselines.
