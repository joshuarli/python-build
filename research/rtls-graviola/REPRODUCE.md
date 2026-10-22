# Reproduce the RTLS and Graviola prototype

This procedure rebuilds the prototype on native Apple Silicon macOS. It keeps
the checkout and Cargo output under `.work/tmp/rtls-graviola.*`. The script
leaves that directory available for inspection.

Run:

```sh
research/rtls-graviola/run-poc.sh
```

The script checks out RTLS commit
`302423b49e494863d07630d50b15a9488ec85ef7`, applies the committed patch, and
builds with the checked-in Rust lockfile. Rust compilation uses `kache` as the
`RUSTC_WRAPPER`. The local test uses RTLS's public CPython TLS test
certificates. It verifies the test root, certificate chain, and `localhost`
name. It runs a TLS 1.3 exchange first with a Graviola server, then with the
host Python's OpenSSL server. Both listeners bind to `127.0.0.1`.

The script requires `python3.15`. The tested host used Python 3.15.0 and Rust
1.99.1. The product target is
CPython 3.15.1. This procedure tests neither the product interpreter nor its
locked Rust toolchain. It does not test Linux musl or x86-64.

The build downloads pinned source and locked Rust crates from GitHub and
crates.io. It does not access an external TLS server. The build and test output
stay in the printed `.work/tmp` directory. Remove that directory when you no
longer need it.
