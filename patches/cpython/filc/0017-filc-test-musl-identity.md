Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Lib/test/support/__init__.py`.
License: CPython PSF License Version 2.

Explanation: `test.support.linked_to_musl()` delegates to
`platform.libc_ver()`, which sees no standard musl ELF loader in Fil-C's
launcher and returns false. The Fil-C product is backed by musl/Pizfix, so
the regression tests must apply their existing musl-specific expectations.
Use the distinct Fil-C SOABI to report musl with an unspecified version,
matching the existing WASM convention.

Scope: `x86_64-filc-linux-musl` installed CPython test support only. Other
targets retain their libc detection.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: installed `test__locale` and related musl-conditioned
standard-library files, plus a direct `test.support.linked_to_musl()` probe.
