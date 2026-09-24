Upstream source: locked libedit 20240808-3.1, SHA-256 in
`sources.lock.json`.
Origin: local Fil-C dependency qualification in `src/readline.c`.
License: libedit BSD license as recorded in `sources.lock.json`.

Explanation: libedit's `history_truncate_file` copies the last history lines
to byte zero, discarding its `_HiStOrY_V2_` header. A subsequent
`read_history_file` rejects that file with EINVAL. Preserve the existing
header when truncating a file that has it. Plain files retain their prior
behavior. This patch is limited to the Fil-C dependency build while the
ordinary Linux dependency graph remains frozen.

Scope: `x86_64-filc-linux-musl` libedit only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
libedit 20240808-3.1 source before configure.

Regression test: installed `test_readline` history-length cases write and
then read a truncated history file; a focused byte check verifies that the
header is still present.
