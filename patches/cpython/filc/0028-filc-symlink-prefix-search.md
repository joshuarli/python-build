Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/getpath.py`.
License: CPython PSF License Version 2.

Explanation: The static Fil-C launcher passes an external symlink path as
`PYTHONEXECUTABLE`. CPython must first look next to that path for a
symlink-specific `._pth` file. If none exists, searching that unrelated
directory for the installed stdlib fails before `encodings` can import.
After the `._pth` decision, search beside the resolved launcher instead.

Scope: `x86_64-filc-linux-musl` source patch only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` after the
prior Fil-C CPython patches to verified 3.14.6 source.

Regression test: `test_site`'s three symlink-specific `._pth` cases and
`test_platform:test_architecture_via_symlink` without a `._pth` file.
