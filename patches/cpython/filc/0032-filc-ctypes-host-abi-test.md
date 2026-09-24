Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Lib/test/test_ctypes/test_find.py`.
License: CPython PSF License Version 2.

Explanation: This one `find_library` regression compiles a glibc ABI shared
object with the build host's gcc, puts it on LD_LIBRARY_PATH, and expects
ctypes to advertise it. A Fil-C interpreter must not advertise or load an
ordinary C ABI library. Skip that incompatible fixture; bundled Pizfix
lookup, private Fil-C dylib loading, callbacks, and the rest of ctypes
remain tested.

Scope: `x86_64-filc-linux-musl` only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` after the
prior Fil-C CPython patches to verified 3.14.6 source.

Regression test: full installed `test_ctypes` module reports this one skip
and passes all other cases; focused validation loads an actual Fil-C dylib.
