Upstream source: CPython 3.15.1, `Objects/lazyimportobject.c`, from
[`Python-3.15.1.tar.xz`](https://www.python.org/ftp/python/3.15.1/Python-3.15.1.tar.xz),
SHA-256 `673ae7232d84c894729882c8257d300ef2d26523911bfd3917ec8ce7f526f99b`,
size 35,789,408 bytes.
Origin: project-authored compatibility fix; no third-party code copied.
License: Python Software Foundation License Version 2.

Explanation: Resolving a long dotted lazy import replayed every attribute and
later reconstructed its dotted name recursively. Either walk used one C stack
frame per component and could overflow a 256 KiB stack before CPython's
recursion check ran. Collect the existing placeholder chain and replay and
format it iteratively.

Scope: CPython 3.15.1 on all production targets. No build flags or CPU
baselines change.

Applicability check: applies with zero fuzz to the locked CPython 3.15.1
source after the earlier source patches are applied.

Regression test: CPython's `test_lazy_import.test_deeply_dotted_name` resolves
a 10,000-component import on a 256 KiB stack and fails if C stack usage
overflows. It runs in the installed-product regression suite.
