Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 port, with the target guard in CPython's
`Include/internal/pycore_faulthandler.h`.
License: CPython PSF License Version 2.

Explanation: Fil-C's musl/Pizfix libc exposes `sigaltstack` but aborts with
`bad syscall: 131` when CPython calls it. Disable
`FAULTHANDLER_USE_ALT_STACK` for Fil-C so an attempted `faulthandler.enable()`
returns the actual ENOSYS result from Pizfix's reserved fatal signals instead
of aborting. This also omits its stack-overflow recovery probe on this target.
User-signal traceback handlers remain available.

Scope: `x86_64-filc-linux-musl` only. Other targets retain their existing
sigaltstack behavior and CPython source.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to a verified
CPython 3.14.6 source tree before configure.

Regression test: `tests/filc_runtime_smoke.py` checks the ENOSYS result from
faulthandler. Before this patch it trapped in Fil-C's `sigaltstack` stub.
