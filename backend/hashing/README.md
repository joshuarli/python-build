# OpenSSL-free hashlib backend

This experiment replaces CPython's `_hashlib` module on native Apple Silicon
macOS. The Python facade keeps the standard digest objects from `_md5`,
`_sha1`, `_sha2`, `_sha3`, and `_blake2`. The Rust extension implements HMAC,
PBKDF2, and scrypt with RustCrypto. It supplies digest objects for
`sha512_224`, `sha512_256`, `ripemd160`, and `sm3`; the facade composes
`md5-sha1` from CPython's `_md5` and `_sha1` builtins.

`_hashlib.py` provides the constructor and name interface that `hashlib.py`
uses. Its `openssl_*` names are compatibility aliases for CPython digest
constructors. They do not call OpenSSL. The Rust extension is
`_hashlib_graviola.abi3.so`. It uses a PEP 489 module definition, per-module
exception and interpreter state, and Rust-only capsules for hash state. Its
Python API wrappers are created separately inside each interpreter. The Rust
binding uses `pyo3-ffi` directly; it does not use PyO3's global module cache,
generated function wrappers, or Python object types.

The replacement has no FIPS mode; `get_fips_mode()` therefore returns `0`.

The CPython 3.15.1 candidate passed `test_hashlib` and `test_hmac` with 240
tests run and 18 upstream skips. The same installed candidate passed
`TestHashlibSupport` with 5 tests run and 4 upstream skips. A separate driver
starts two `InterpreterPoolExecutor` workers before the backend is imported
in the main interpreter. Both workers rendezvous concurrently, then exercise
hash, HMAC, PBKDF2, scrypt, copied-state independence, and module-local
exceptions across three interpreter create/destroy cycles. The candidate
retained its Python `_ssl.py` marker shim; no source `Lib` directory shadows
the installed standard library during suite runs. Resource gated tests remain
skipped under the default test runner settings.

The facade does not expose the private native `_hashlib.HASH` type because
CPython's builtin digest modules return several distinct types. The upstream
suite's private type-instantiation check is skipped. Native extensions that
import `_hashlib.HASH`, expect OpenSSL symbols, or link `libcrypto` are outside
this experiment's contract.

This experiment does not provide OpenSSL's native `_hashlib` C API or shared
digest object types. It does not replace `_ssl` or change the product build.

Scrypt admission uses the OpenSSL 3.5.7 maxmem lower bound
`128 * r * (n + p + 2)`. The serial RustCrypto implementation's large work
buffers `B`, `V`, and `T` total `128 * r * (n + p + 1)` bytes; the requested
derived key and password and salt copies are separate allocations and are not
part of that compatibility limit.

See [REPRODUCE.md](REPRODUCE.md) for the build and test procedure.
