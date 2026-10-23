# Native extension compatibility

This note covers native consumers of the CPython 3.15.1 TLS and hashing
modules. It distinguishes the supported CPython C API from OpenSSL symbols
that happen to be present in the reference extension binaries.

The candidate evidence uses the frozen macOS arm64 build at revision
`a0940b5`, relocated to a path with spaces. It contains the RTLS `ssl`
adapter and the Graviola hashing adapter.

## CPython extension ABI checks pass

The relocated prefix passed the existing `buildsys.validate_product` checks
for a native extension, a limited-API extension, and shared-library embedding:

| Check | Result |
| --- | --- |
| `extension_checks` | Built and imported the extension. It returned `42` and called a Python callback that returned `10`. |
| `abi3_checks` | Built and imported the limited-API extension. It returned `42`. |
| `embedding_checks` | Linked and ran the embedder. It printed `embedded 3.15.1 0.23.45`. |

These checks exercise the CPython C API through `Python.h`, `python3.15-config`,
and `libpython3.15.dylib`. They do not exercise OpenSSL entry points. The
checks do not qualify the full candidate or run the rest of
`buildsys.validate_product`.

## OpenSSL symbols are not a Python extension API

On the pinned OpenSSL 3.5.7 reference, `nm -gU` counted these global symbol
definitions in the native extension bundles:

| Reference module | All defined globals | EVP, SSL, X509, and OPENSSL names |
| --- | ---: | ---: |
| `_ssl.cpython-315-darwin.so` | 9,376 | 2,249 |
| `_hashlib.cpython-315-darwin.so` | 7,255 | 1,673 |

`otool -L` lists only `libSystem` for each bundle. The build recipe uses
`no-shared no-module`, so these OpenSSL symbols come from static code linked
into each extension. `ctypes.CDLL` opened on the `_ssl` handle resolves
`EVP_sha256`, `EVP_MD_fetch`, `SSL_CTX_new`, and `X509_get_subject_name`. The
`_hashlib` handle resolves the two `EVP` functions and
`X509_get_subject_name`. The same `EVP_sha256` and `EVP_MD_fetch` names resolve
to different addresses through the `_ssl` and `_hashlib` handles.
The modules therefore contain separate OpenSSL copies, not one shared
OpenSSL library or a supported pointer interface.

The candidate replaces the native `_ssl` and `_hashlib` modules with Python
adapters. Its `_ssl.py` and `_hashlib.py` module dictionaries publish no
`_C_API` attribute or `PyCapsule`. The native `_hashlib_graviola.abi3.so` and
`rtls._rustls.abi3.so` each define only their module initializer. Direct
`ctypes` lookup on either native module handle finds none of the tested
OpenSSL functions. The installed prefix also has no OpenSSL headers or
`libssl` and `libcrypto` archives.

The later combined development TLS binding adds six `rtls_native_*` C exports:
`claim`, `copy_reply`, `free`, `handle_count`, `invoke`, and `report_unraisable`.
The ordinary Python facade uses these owned-handle operations through `ctypes`;
they expose no OpenSSL object pointers. `nm -gU` on that build reports these
six symbols and `PyInit__rustls`, and its undefined symbols contain no `EVP_`,
`SSL_`, `X509_`, or `OPENSSL_` names. Its load commands still name only
`libiconv` and `libSystem`. Final extracted-archive checks remain outstanding.

In both native candidate modules, `LC_ID_DYLIB` uses an `@rpath` install name.
Their `LC_LOAD_DYLIB` entries name only `libiconv` and `libSystem`. Neither
module loads OpenSSL or a build-tree library.

Process-wide `dlsym` results are different from extension-handle results on
this macOS host. The host resolves some OpenSSL-named functions from
`/usr/lib/libboringssl.dylib` and `/usr/lib/libcrypto.46.dylib`; `EVP_MD_fetch`
is absent. Those host symbols are not the candidate's OpenSSL API. Consumers
must not treat a process-wide symbol lookup as evidence of OpenSSL
compatibility.

An extension that uses only `Python.h` and the documented CPython C API uses
the binary boundary covered by these checks. An extension that reads `_ssl`
object layouts, passes `SSL_CTX *`, `SSL *`, or `EVP_MD *` pointers, or
resolves OpenSSL symbols from `_ssl` or `_hashlib` depends on private
implementation details. That extension is not compatible with the
OpenSSL-free candidate. The reference modules publish no OpenSSL capsule for
such consumers.

## Independently linked applications

The CPython product builds OpenSSL as static code for its native modules. It
does not provide a shared `libssl` or `libcrypto` API for other applications.
An application that links and packages its own OpenSSL dependency remains
separate from this CPython change. A Python extension that relies on symbols
from the reference `_ssl` or `_hashlib` bundles does not have that independent
dependency and loses those symbols with the replacement.
