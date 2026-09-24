Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Lib/ctypes/util.py`.
License: CPython PSF License Version 2.

Explanation: Pizfix exports `dl_iterate_phdr` but its implementation aborts
with `static_dl_iterate_phdr not implemented`. CPython probes only for the
symbol and advertises `ctypes.util.dllist`, so a valid call traps. Keep
`dllist` unavailable on the distinct Fil-C ABI until Pizfix implements the
enumeration. Other ctypes calls, callbacks, and extension loading remain
available.

Scope: `x86_64-filc-linux-musl` only. Other targets retain `dllist`.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: installed `test.test_ctypes.test_dllist` skips when the
platform capability is absent, while `buildsys/validate_filc.py` continues
to check working ctypes calls and callbacks.
