Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/mathmodule.c`.
License: CPython PSF License Version 2.

Explanation: Pizfix's musl `fma()` returns positive zero for a nonzero
negative product that underflows when the third operand is zero. The fused
result must retain a negative zero. Correct only this observed signed-zero
case in `math.fma`; leave all other libc fma results unchanged. Remove this
workaround when a pinned Pizfix runtime fixes the case itself.

Scope: `x86_64-filc-linux-musl` only. Ordinary targets use CPython's
unmodified `math.fma` implementation.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to a verified
CPython 3.14.6 source tree before configure.

Regression test: installed CPython `test_math.test_fma_zero_result` and
`tests/filc_runtime_smoke.py` both exercise the negative underflow case.
