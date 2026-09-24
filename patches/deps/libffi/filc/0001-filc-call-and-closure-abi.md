Upstream source: locked libffi 3.8.0 tarball, SHA-256 in `sources.lock.json`.
Origin: Fil-C's exact-version `projects/libffi.projeny` port in the local
`~/d/fil-c` checkout at commit `acc204ec44`. The x86_64 call and closure
implementation is adapted here for the python-build static dependency.
License: libffi MIT license; Fil-C additions retain their upstream
attribution from the local Fil-C repository.

Explanation: ordinary libffi uses x86_64 assembly and executable trampolines
to call functions and implement callbacks. Fil-C's capability ABI passes a
typed argument blob through `zcall` and builds callbacks with `zclosure_new`.
This patch selects that ABI, omits the incompatible assembly source, and
keeps pointer bounds when aligning argument slots with `zmkptr`. It also
corrects a duplicated assignment in the local Fil-C 3.8.0 port.

Scope: `x86_64-filc-linux-musl` only, applied to the exact locked libffi
source. No replacement binary or source version is used.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` against the
verified libffi 3.8.0 source before configure.

Regression test: build the static library with Fil-C, compile and run a C
call/closure smoke, then exercise `ctypes` calls and callbacks from the
packaged interpreter.
