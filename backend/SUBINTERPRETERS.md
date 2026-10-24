# Subinterpreter binding prototype

The prototype loads the existing Rust TLS library through `ctypes.CDLL`.
The pure Python `rtls._native` module supplies the objects used by the normal
`SSLContext`, `SSLObject`, and socket facade. It never initializes the PyO3
module or changes its subinterpreter guard.

The C interface owns only Rust values. Integer handles identify configuration,
connection, acceptor, and reply objects in a registry. Registry lookup takes an
`Arc` before releasing the registry lock. Crypto runs under the object's lock.
Freeing a handle removes registry ownership while an active operation retains
its own `Arc`. Python wrappers release handles explicitly or through
`weakref.finalize`, including interpreter teardown.

Python allocates the reply slot before entering native code. Invocation and
reply decoding share one cleanup scope, including interruption immediately
after a native call. Replies own returned handles until Python registers their finalizer and claims
ownership. Failure to allocate a buffer, decode a reply, or register a finalizer
releases the unclaimed native object. The interface checks handle validity,
argument extents, argument types, and reply capacity. Arguments and replies contain copied values. No native pointer
or borrowed Rust allocation escapes to Python. Rust panics stop at the C
boundary and produce an error. The callback error reporter is a separate
`PyDLL` function: it uses the calling interpreter's held GIL and two transient
Python object pointers, retains neither, and calls `PyErr_WriteUnraisable`.

Configuration factories, the selected-path verifier, rustls record processing,
and Graviola remain the TLS engine. Python callbacks run outside native locks.
The prototype retains initial authentication mode, verification flags, and
protocol bounds during SNI selection, while selecting replacement certificate,
trust, signature, cipher, and ALPN policy through the existing factory.

The binding is part of the consolidated RTLS overlay. Build its normal Rust
library and install the Python sources and library into a private candidate
prefix through `build-no-openssl.py`. Run:

```sh
<prefix>/bin/python3.15 research/rtls-graviola/subinterpreter_contract.py <cpython-source>/Lib/test/certdata
```

The contract injects bounded allocation failures and checks unsupported ECH
rejection. It uses the normal SSL facade to check verified TLS 1.2 and 1.3,
application data, verified chains, and untrusted-certificate rejection across
two subinterpreters. It destroys and recreates the interpreters, checks that
native ownership returns to its initial count, and repeats TLS work through
`InterpreterPoolExecutor`.

Certificate dictionaries and session metadata use the existing Rust data
representations. Explicit session reuse retains the context and verified-path
checks of the existing binding. Large writes return the actual accepted count
from bounded transfers. Random output uses bounded transfers without a total
size policy limit. Unsupported ECH fails explicitly.

Both bindings share the typed `TlsError` classification and its certificate
code, verification message, and alert metadata. Builder snapshots retain TLS
1.3 cipher selection and the initial ticket count. Connection getters expose
the maintained engine group and channel binding values. The certificate
summary model and parser remain shared with the PyO3 adapter.

The prototype is locally verified on macOS arm64. Production inputs and
defaults are unchanged. Full CPython suite qualification remains a separate
integration step.
