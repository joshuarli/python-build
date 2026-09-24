Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Lib/ctypes/util.py`.
License: CPython PSF License Version 2.

Explanation: Linux `find_library` asks the build host's `ldconfig`, gcc,
and ld for SONAMEs. In the Debian Fil-C builder these return glibc names
such as `libc.so.6` and `libm.so.6`, which Pizfix cannot load. Resolve the
Fil-C runtime's known libc family from the bundled `sys.base_prefix/lib`
instead; unknown names return None, so host libraries are never advertised.
The lookup follows the installation when relocated.

Scope: `x86_64-filc-linux-musl` only. Other platforms use their original
lookup strategy.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` after the
prior Fil-C CPython patches to verified 3.14.6 source.

Regression test: full installed `test_ctypes` module, including callback,
errno, and libm cases; `buildsys.validate_filc.filc_ctypes_checks` also
loads bundled libc and a private Fil-C dylib after relocation.
