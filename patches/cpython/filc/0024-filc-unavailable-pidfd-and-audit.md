Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/signalmodule.c`, its
generated clinic header, and `Lib/test/audit-tests.py`.
License: CPython PSF License Version 2.

Explanation: Pizfix advertises Linux's pidfd_send_signal syscall number but
its generic syscall entry aborts. Do not expose the unsupported Python API.
An audit regression constructs an invented address by adding 40 to `id()`;
Fil-C correctly rejects that invalid pointer. Keep its real ctypes audit
checks while omitting only the invented-address call on this target.

Scope: `x86_64-filc-linux-musl` only. Other targets retain both behaviors.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: `test_signal` observes the absent unsupported API and
`test_audit:test_ctypes_call_function` still verifies real ctypes calls.
