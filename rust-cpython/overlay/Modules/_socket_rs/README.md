# Socket converter bindings

The public address converters are native builtins bound to the public socket
module. `socket_bind_address_converters` creates the pair once; each callable
owns that module through its `__self__`. A retained converter therefore keeps
using its original module's family constants and `_socket_rs` helper after
another module replaces the entry in `sys.modules`.

Eligible address parsing and formatting still call the existing Rust helper.
The unchanged native converters own other coercions, invalid-address errors,
and the platform spelling of IPv4-compatible IPv6 addresses. The eager helper
import, raw `_socket` provider functions, socket types, C API, send/receive
activation, signal handling and descriptor lifecycle are unchanged.

The native callables preserve their public names, module names, docstrings,
text signatures, ordinary positional-only argument diagnostics and observable
missing-global exception names. Family guard and value comparisons preserve
operator and metaclass callbacks, including helper rebinding and class lifetime.

Replacing Python functions with builtins is an intentional representation
boundary. `types.FunctionType`, mutable function metadata, `__code__`,
`__globals__`, and artificial rebinding of the former wrappers' builtin names
(`type`, `int`, `str`, `bytes`, `len`) are not preserved. Missing owning-module
family/helper attributes do not fall through to artificial builtin globals.
The native identity and namespace fixture records this supported contract.

The proposed retained-memory reduction removes two Python function/code objects
and their fallback-alias entries. Added native code and method definitions can
offset that saving; source structure establishes no physical memory benefit.
The fixture in `tests/check_bound_address_converters.py` has not yet executed
for this source-only candidate. Compilation, full suites and memory qualification
are required before acceptance.
