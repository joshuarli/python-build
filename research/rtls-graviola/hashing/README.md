# OpenSSL-free hashlib backend

This experiment replaces CPython's `_hashlib` module on native Apple Silicon
macOS. The Python facade keeps the standard digest objects from `_md5`,
`_sha1`, `_sha2`, `_sha3`, and `_blake2`. The Rust extension implements HMAC,
PBKDF2, and scrypt with RustCrypto.

`_hashlib.py` provides the constructor and name interface that `hashlib.py`
uses. Its `openssl_*` names are compatibility aliases for the CPython digest
constructors. They do not call OpenSSL. The Rust extension is
`_hashlib_graviola.abi3.so`.

The Python `hashlib` and `hmac` APIs pass CPython 3.15.1's complete
`test_hashlib` and `test_hmac` suites. The recorded run passed 240 tests and
skipped 18. One skip covers `_hashlib.HASH` instantiation checks. The facade
does not expose that private native type because CPython's builtin digest
modules return several distinct types. Resource gated tests also remain
skipped under the default test runner settings.

This module does not provide OpenSSL's native `_hashlib` C API or its shared
digest object types. Native extensions that import `_hashlib.HASH`, expect
OpenSSL symbols, or link `libcrypto` are outside this experiment's contract.
It does not replace `_ssl` or change the product build.

See [REPRODUCE.md](REPRODUCE.md) for the build and test procedure.
