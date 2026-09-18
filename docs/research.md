# Implementation research and verified discoveries

Findings from actually building this project's dependencies and CPython
3.14.6 inside the Dockerfile-defined Alpine environment, not from reading
PBS's source in isolation. Each entry names the exact symptom, root cause,
and fix; the fixes themselves live in the referenced files.

## `$ORIGIN` cannot be baked into configure-time LDFLAGS

**Symptom**: `readelf -d` on the built `bin/python3.14` showed
`RUNPATH: [/../lib]` — an absolute path rooted at the filesystem root, not
a relative `$ORIGIN/../lib` token. Every shipped ELF had the same bug.

**Root cause**: CPython's own build consumes `LDFLAGS` twice, through two
different interpreters. Its Makefile recipes route the value through GNU
Make (which turns `$$` into a literal `$`) and then through `/bin/sh`
(which then tries to expand `$ORIGIN` as a *shell* variable — undefined,
so it disappears). Meanwhile `pip`/`setuptools` read the same raw
configure-substituted `LDFLAGS` string directly out of `_sysconfigdata_*.py`
as a plain Python string, with no shell or Make in between. No single
escaping of `$ORIGIN` survives both consumers as a literal single `$`.

**Fix**: don't fight the escaping. `buildsys/cpython.py` no longer puts an
`-rpath` in configure-time `LDFLAGS` at all. `buildsys/relocate.py` sets a
correct `$ORIGIN`-relative RPATH on every shipped ELF with `patchelf
--set-rpath` as a post-`make install` step — patchelf takes the token as a
plain argv element, so there is no shell or Make to mangle it.

## The private dependency prefix leaks into sysconfigdata

**Symptom**: even after fixing the RPATH, `_sysconfigdata_*.py`'s `LDFLAGS`,
`LDSHARED`, `CPPFLAGS`, etc. still contained `-I/work/build/prefix/include
-L/work/build/prefix/lib` — a path that only exists inside the builder
container. Plan Section 6 explicitly forbids this leaking into "consumer
compiler settings."

**Fix**: `buildsys/relocate.py::clean_sysconfig` rewrites a fixed list of
consumer-facing sysconfigdata keys (`CONSUMER_FLAG_KEYS`) and the installed
`Makefile`, stripping any `-I`/`-L`/bare token naming the private prefix.
Per-module provenance keys (`MODULE__SSL_LDFLAGS` and friends) are left
alone deliberately: they document how CPython's own stdlib modules were
built and are not part of the pip/distutils extension-build contract.

## BDB needs `--enable-dbm`, not just `db.h`

**Symptom**: `_dbm` was reported "missing" by configure even though `db.h`
was found and `DBM_LIBS`/`DBM_CFLAGS` were set correctly.

**Root cause**: CPython's `_dbm` probe links `dbm_open()`, which `db.h`
`#define`s to `__db_ndbm_open()` only when Berkeley DB was built with its
historic ndbm-compatibility interface. Our BDB recipe built the library
without that interface, so the link failed with `undefined reference to
'__db_ndbm_open'` (see `config.log`, `checking for libdb`).

**Fix**: `build/deps.py::configure_args` passes `--enable-dbm` when
building `bdb`.

## `readline` needs `--with-readline=editline`

**Symptom**: the `readline` stdlib module was "missing" despite a working
libedit build with a correct `editline/readline.h` header and `libedit.pc`.

**Root cause**: CPython 3.14's configure defaults to `--with-readline=readline`
(GNU readline) and never even probes for libedit unless told to.

**Fix**: `buildsys/cpython.py` passes `--with-readline=editline`.

## `python-config` crashes on install paths containing a space

**Symptom**: relocating the built tree to a path with a space (e.g.
`/tmp/reloc target/python`) made every `python3.14-config` invocation fail
with `cd: can't cd to /tmp/reloc`.

**Root cause**: `Misc/python-config.sh.in`'s `installed_prefix()` runs
`cd $(dirname "$1")` — the inner substitution is quoted, but the outer `cd
$(...)` is not, so the shell word-splits the result on the space before
`cd` ever sees it.

**Fix**: `patches/cpython/0001-python-config-quote-installed-prefix.patch`
(provenance and regression test alongside it in `patches/cpython/*.md` and
`tests/test_patches.py`). Verified end-to-end: `ensurepip`, `venv`, and a
`sysconfig`-driven C-extension build all work at a relocated space-path
after the patch; `python3.14-config` no longer crashes there either.

## PBS's musl reference statically links most extension modules

The reference `install_only_stripped` archive ships only **two** shared
`.so` extension modules (`_dbm`, `_tkinter`); everything else (`ssl`,
`sqlite3`, `zlib`, ...) is linked directly into the interpreter/libpython.
This project's build uses CPython's ordinary configure-driven
built-in/shared split instead (most modules as separate `.so` files under
`lib-dynload/`), which plan Section 2.3 explicitly permits as a documented
difference. It explains most of the raw size difference between the two
archives before stripping (reference 84 MB vs. this project's stripped
62 MB â€” both dominated by many small `.so` files here vs. one larger
statically-linked interpreter there).

## Two independent sealed builds were byte-identical

Two full `docker build --no-cache --target sealed` runs (cache fully
busted, so no compiled-object reuse — only the immutable
`.cache/objects/*.blob` downloads were shared, which plan 8.3 explicitly
allows) produced staged install trees with **zero** file-list or
content-hash differences across 8,319 compared files. See
`dist/reproducibility.json`.
