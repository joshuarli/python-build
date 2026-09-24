Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/faulthandler.c`.
License: CPython PSF License Version 2.

Explanation: Pizfix refuses fatal-signal handler registration with ENOSYS.
When that happens, CPython's `faulthandler_enable()` returns an exception but
leaves `fatal_error.enabled` true and any earlier handlers installed. Roll
back handlers already installed and reset the enabled state on failure. This
keeps `faulthandler.is_enabled()` truthful and permits repeated attempts.

Scope: applied only for `x86_64-filc-linux-musl`. The rollback itself is a
general correctness improvement; other targets retain their original source.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source after the earlier Fil-C patches.

Regression test: `tests/filc_runtime_smoke.py` verifies ENOSYS and the disabled
state, then registers and unregisters a supported user signal.
