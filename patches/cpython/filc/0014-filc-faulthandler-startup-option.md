Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/faulthandler.c`.
License: CPython PSF License Version 2.

Explanation: CPython's test helpers launch subprocesses with `-X
faulthandler`. Pizfix returns ENOSYS for fatal-signal handlers, so the option
otherwise aborts interpreter startup and causes widespread unrelated test
failures. On this ABI, acknowledge the option without installing unsupported
handlers; `faulthandler.is_enabled()` remains false. An explicit
`faulthandler.enable()` still raises ENOSYS, making the missing capability
visible to applications.

Scope: `x86_64-filc-linux-musl` only. Other targets retain their original
startup behavior.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source after the earlier Fil-C patches.

Regression test: `tests/filc_runtime_smoke.py` launches `-X faulthandler`
and verifies startup plus the disabled status. The installed `test_builtin`
previously failed because its `-X faulthandler` subprocess aborted.
