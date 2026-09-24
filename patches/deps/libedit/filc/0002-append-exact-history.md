Upstream source: locked libedit 20240808-3.1, SHA-256 in `sources.lock.json`.
Origin: local Fil-C qualification in `src/readline.c` and `src/history.c`.
License: BSD-3-Clause, as carried by libedit.

Explanation: Pizfix's append-mode stream starts with a zero file position
even for a populated file. libedit uses that position to decide whether to
write the `_HiStOrY_V2_` cookie, so append_history inserted a second cookie.
Seek to end first. libedit's `H_NSAVE_FP` loop also advances once too far
for a requested positive count; write exactly the requested number of
recent entries, and none for zero. CPython's `append_history_file(1)` now
adds one entry and the resulting file remains readable.

Scope: Fil-C dependency build only; ordinary musl and macOS libedit are
unchanged.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
libedit source before configure.

Regression test: installed `test_readline:test_write_read_append` and full
`test_readline` module.
