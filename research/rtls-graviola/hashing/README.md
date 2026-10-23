# OpenSSL-free hashlib backend

This experiment replaces CPython's `_hashlib` module on native Apple Silicon
macOS. The Python facade keeps the standard digest objects from `_md5`,
`_sha1`, `_sha2`, `_sha3`, and `_blake2`. The Rust extension implements HMAC,
PBKDF2, and scrypt with RustCrypto. It supplies digest objects for
`sha512_224`, `sha512_256`, `ripemd160`, and `sm3`; the facade composes
`md5-sha1` from CPython's `_md5` and `_sha1` builtins.

`_hashlib.py` provides the constructor and name interface that `hashlib.py`
uses. Its `openssl_*` names are compatibility aliases for the CPython digest
constructors. They do not call OpenSSL. The Rust extension is
`_hashlib_graviola.abi3.so`.

The replacement has no FIPS mode; `get_fips_mode()` therefore returns `0`.

The hash-isolated CPython 3.15.1 run passed `test_hashlib` and `test_hmac` with
240 tests run and 18 skipped. It used a disposable prefix without the Python
`_ssl.py` marker shim to isolate hashing behavior; this is not the integrated
marker-backed acceptance run. One skip covers `_hashlib.HASH` instantiation
checks. The facade does not expose that private native type because CPython's
builtin digest modules return several distinct types. Resource gated tests
also remain skipped under the default test runner settings.

This module does not provide OpenSSL's native `_hashlib` C API or its shared
digest object types. Native extensions that import `_hashlib.HASH`, expect
OpenSSL symbols, or link `libcrypto` are outside this experiment's contract.
It does not replace `_ssl` or change the product build.

Scrypt admission uses the OpenSSL 3.5.7 maxmem lower bound
`128 * r * (n + p + 2)`. The serial RustCrypto implementation's large work
buffers `B`, `V`, and `T` total `128 * r * (n + p + 1)` bytes; the requested
derived key and password and salt copies are separate allocations and are not
part of that compatibility limit.

See [REPRODUCE.md](REPRODUCE.md) for the build and test procedure.
