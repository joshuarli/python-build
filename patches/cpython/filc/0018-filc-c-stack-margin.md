Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `pycore_pythonrun.h`.
License: CPython PSF License Version 2.

Explanation: Fil-C's capability checks increase interpreter C-stack use.
The installed `test_call.test_margin_is_sufficient` measured a protected
call frame plus safety allowance of 17,260 bytes, exceeding CPython's normal
16,384-byte recursion margin. Use its existing 32,768-byte debug/sanitizer
margin for Fil-C, protecting deep recursion without changing the stack
algorithm.

Scope: `x86_64-filc-linux-musl` only. Other targets retain their margin.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: installed `test_call.test_margin_is_sufficient` and the
deep recursion tests in the full CPython regression suite.
