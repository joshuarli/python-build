Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in four `Lib/test` modules.
License: CPython PSF License Version 2.

Explanation: Two C API cases deliberately read a freed object, which Fil-C
traps. A ctypes case turns a pointer return into a raw integer and then
dereferences it; Fil-C cannot recover the lost capability, so retain its
typed-pointer half. Pizfix asserts when the signal stress test races handler
replacement, so skip that one stress case while other signal tests run.
Pizfix background threads cause `os.fork()` to emit the correct Python
deprecation warning; filter that expected warning in two fork-state tests
so their actual post-fork assertions remain covered.

Scope: `x86_64-filc-linux-musl` only. Other targets keep their test behavior.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: full installed `test_capi`, `test_ctypes`, `test_signal`,
and `test_threading` modules complete. The named unsafe/stress cases are
reported as skips, and the two fork-state cases pass.
