Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `pycore_lock.h` and `lock.c`.
License: CPython PSF License Version 2.

Explanation: `_PyRawMutex` packs a stack waiter pointer and a lock bit into
`uintptr_t`. That integer discards Fil-C's pointer capability. Under thread
contention, `_PyRawMutex_UnlockSlow` casts it back and traps on the waiter's
`next` field. On Fil-C only, store the word as a pointer, use pointer atomics,
and add/remove the low-bit tag with `zorptr`/`zandptr`. The waiter list and
lock-state transitions retain CPython's existing algorithm.

Scope: `x86_64-filc-linux-musl` only. Ordinary targets retain the integer
field and integer atomic operations.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: the installed `test.test_concurrent_futures.test_wait`
worker trapped in `_PyRawMutex_UnlockSlow` before this patch. Re-run that
file under the installed regression runner, followed by the full suite.
