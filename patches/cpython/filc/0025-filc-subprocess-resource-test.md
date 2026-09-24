Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Lib/test/test_subprocess.py`.
License: CPython PSF License Version 2.

Explanation: This one regression sets RLIMIT_NPROC to zero and asks Pizfix to
create a process with a Python preexec callback. The Fil-C runtime tries to
start a GC worker and asserts when `pthread_create` reports EAGAIN, aborting
the entire suite. Skip this artificial resource exhaustion case on Fil-C;
other subprocess, preexec, fork, and fd tests continue to run. This records
a Pizfix behavior under resource exhaustion, not a general subprocess
disablement.

Scope: `x86_64-filc-linux-musl` only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: full installed `test_subprocess` module completes, and
`test_preexec_fork_failure` is reported as exactly one skip.
