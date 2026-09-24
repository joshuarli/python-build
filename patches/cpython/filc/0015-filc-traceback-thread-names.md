Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Python/traceback.c`.
License: CPython PSF License Version 2.

Explanation: CPython stores a numeric thread ID in `PyThreadState.thread_id`
and casts it back to `pthread_t` when adding a thread name to a traceback.
Fil-C's `pthread_t` is a capability, so the integer has lost its authority;
passing it to Pizfix's `pthread_getname_np` traps. Omit only the optional
thread name on Fil-C. The numeric ID and Python frames are still dumped.

Scope: `x86_64-filc-linux-musl` only. Other targets retain thread names.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: `tests/filc_runtime_smoke.py` calls
`faulthandler.dump_traceback(all_threads=True)` and checks for a traceback.
The installed `test_faulthandler` had four related failures and Fil-C safety
panics before this patch.
