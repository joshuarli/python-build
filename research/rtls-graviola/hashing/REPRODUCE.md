# Reproduce the hashing tests

Run the experiment on native Apple Silicon macOS with Rust 1.85 or newer,
`kache`, Cargo, and a CPython 3.15.1 candidate that has `_ssl` and the native
`_hashlib` extension disabled. Keep the candidate prefix under the repository's
`.work/` directory. The script modifies only that disposable prefix.

Copy a prepared candidate prefix before installing the facade:

```sh
mkdir -p .work/tmp/hashlib-candidate
cp -cR /path/to/candidate-prefix/. .work/tmp/hashlib-candidate/
```

Build the extension, install both modules, and run the complete suites:

```sh
research/rtls-graviola/hashing/run-tests.sh \
    .work/tmp/hashlib-candidate \
    .work/tmp/rtls-no-ssl/cpython-source/Python-3.15.1
```

The script downloads locked Cargo inputs, builds with `--offline --locked`,
and installs `_hashlib.py` in `lib/python3.15/`. It installs
`_hashlib_graviola.abi3.so` in `lib/python3.15/lib-dynload/`. It checks that
the original native `_hashlib` and `_ssl` modules are absent before testing.

The recorded run used a private copy of
`.work/tmp/rtls-no-ssl.bnHJ8y/python` on CPython 3.15.1 arm64 macOS. The copy
had the original `_hashlib.cpython-315-darwin.so` removed. It retained the
builtin digest modules and `_hmac`. The command completed with 240 tests run,
18 skipped, and no failures. The Python process loaded the installed
`_hashlib.py`; `_ssl` was not present in `sys.modules`.

The skips include the private `_hashlib.HASH` type check because this facade
does not expose a shared native hash type. The default runner also skips
resource-gated tests. The pass covers CPython's Python-level hashlib and hmac
contracts. It does not qualify native `_hashlib` consumers, TLS, other
platforms, performance, or a production artifact.
