Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/socketmodule.c`.
License: CPython PSF License Version 2.

Explanation: This Linux host advertises RDS sockets, but the Fil-C/Pizfix
interpreter repeatedly blocks forever in `RDSTest.testPeek` on an RDS
`recvfrom`; the same socket file passes only intermittently. Do not expose
the RDS family or level constants as a supported socket API on Fil-C. TCP,
UDP, Unix, and other working socket families stay enabled and under the
full socket regression suite. The core application socket requirement is
unchanged; RDS is a distinct, unreliable kernel protocol here.

Scope: `x86_64-filc-linux-musl` only. Other targets retain RDS constants.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` after the
prior Fil-C CPython patches to verified 3.14.6 source.

Regression test: full installed `test_socket` completes without a timeout,
with only its RDS-specific classes skipped; focused socketpair and TLS
checks continue to pass.
