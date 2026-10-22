Upstream source: CPython 3.15.1, `Modules/readline.c`, from
[`Python-3.15.1.tar.xz`](https://www.python.org/ftp/python/3.15.1/Python-3.15.1.tar.xz),
SHA-256 `673ae7232d84c894729882c8257d300ef2d26523911bfd3917ec8ce7f526f99b`,
size 35,789,408 bytes.
Origin: project-authored compatibility fix; no third-party code copied.
License: Python Software Foundation License Version 2.

Explanation: libedit can write a second `_HiStOrY_V2_` cookie when appending
history. The duplicate is read as a history item and breaks CPython's
append-history tests. On non-Apple libedit builds, remove duplicate cookie
lines after successful history writes and appends while preserving the first
file header and all history entries.

Scope: `x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl` when
CPython uses the libedit compatibility path. macOS keeps its existing
libedit implementation.

Applicability check: applies with zero fuzz to the locked CPython 3.15.1
source after the earlier source patches are applied.

Regression tests: CPython's `test_readline.test_write_read_append` and
`test_readline.test_append_limited_history` exercise appended and truncated
history files. Both run in the installed-product regression suite.
