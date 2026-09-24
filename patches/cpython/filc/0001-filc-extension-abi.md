Upstream source: locked CPython 3.14.6, `configure.ac`, generated `configure`,
and `Python/dynload_shlib.c`.
Origin: project-authored ABI isolation; no third-party code copied.
License: Python Software Foundation License Version 2.

Explanation: Fil-C uses capability-bearing pointers and its own calling ABI.
CPython's ordinary Linux SOABI and its fallback `.abi3.so`/`.so` suffixes
would let import machinery mistake an ordinary C extension for a compatible
one. Give the installed sysconfig metadata and extension filenames the
`x86_64-filc-linux-musl` ABI identity. Fil-C's compiler defines
`__FILC__`; under that compiler, import machinery accepts only
the exact Fil-C SOABI suffix. The generated `configure` and its `configure.ac`
source carry the same change.

Scope: `x86_64-filc-linux-musl` only. The ordinary Linux and macOS patch sets
do not include this file.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` against the
verified CPython 3.14.6 source. Both configure files and the C import table
must match exactly.

Regression test: packaged Fil-C validation checks `SOABI`, `EXT_SUFFIX`, and
`_imp.extension_suffixes()`, loads an extension built with the recorded Fil-C
compiler, and rejects an ordinary host-compiled extension in the same module
directory.
