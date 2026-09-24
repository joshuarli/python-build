Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/readline.c`.
License: CPython PSF License Version 2.

Explanation: CPython probes whether libedit's `replace_history_entry` index
is one-based, then subtracts that offset from the count passed to
`append_history`. The two operations have different contracts: the locked
libedit's append count is exact. With an offset of one,
`append_history_file(1, ...)` passes zero and appends the entire in-memory
history. Pass the requested count directly for Fil-C.

Scope: `x86_64-filc-linux-musl` only. Ordinary targets retain their
existing readline behavior.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: installed `test_readline.TestHistoryManipulation` checks
the file contains exactly one appended history entry.
