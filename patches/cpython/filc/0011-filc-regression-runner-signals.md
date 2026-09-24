Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification, limited to CPython's installed
regression runner in `Lib/test/libregrtest/setup.py`.
License: CPython PSF License Version 2.

Explanation: Pizfix does not support installing fatal-signal handlers.
`sigaction(SIGSEGV, ...)` and `signal(SIGSEGV, ...)` return ENOSYS,
so `faulthandler.enable()` raises `RuntimeError(ENOSYS, ...)`. CPython's
regression runner calls it unconditionally before running any tests. Catch
only this specific failure on the Fil-C SOABI; all other exceptions and
all other targets still fail. User-signal traceback registration remains
active. The product's faulthandler API continues to report the unsupported
fatal-signal capability truthfully.

Scope: `x86_64-filc-linux-musl` only. Other targets retain unmodified
CPython source and regression-runner behavior.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to a verified
CPython 3.14.6 source tree before configure.

Regression test: `tests/filc_runtime_smoke.py` checks the precise ENOSYS result
and working user-signal registration. An installed `python -m test test_math`
previously aborted at regression-runner startup; it now runs the test.
