Upstream source: CPython 3.14.6, `Modules/getpath.c` and `Modules/getpath.py`.
Origin: project-authored compatibility fix; no third-party code copied.
License: Python Software Foundation License Version 2.

Explanation: An invalid `argv[0]` such as `/dev/null` currently wins over the
executable path reported by macOS, and POSIX builds do not populate that real
path. The interpreter then cannot find its standard library during
initialization. On Linux, read `/proc/self/exe` when available; on both
supported POSIX targets, use the process-reported executable when `argv[0]`
is not executable. Valid symlink paths keep their existing prefix-resolution
behavior.

Scope: `aarch64-apple-darwin` and both Linux musl targets; no new targets or
dependencies.

Applicability check: the patch applies to the locked CPython 3.14.6 source
with no fuzz or rejected hunks.

Regression test: `buildsys/standalone_compat.py::_getpath_check` checks
startup through an external symlink and with an invalid `argv[0]` for each
target. The build-time check runs against final packaged bytes and fails
packaging if either invocation cannot start or the installed prefix is not
found.
