# Bundled native inputs: license audit

Audited 2026-10-30 against the bytes pinned in `sources.lock.json` (each
archive re-verified against its SHA-256 before reading). Releases ship the
files named here under `share/licenses/python-build/` and a source-acquisition
record at `share/licenses/python-build/SOURCES.md`, both written by
`buildsys/notices.py` and checked by the `license_notices` qualification check
on the final extracted archive. Rust dependency notices ship under
`share/licenses/python-build/rust/` (`backend/rust_licenses.py`).

| Input | Lock license | Audit result | Shipped notice |
| --- | --- | --- | --- |
| zlib 1.3.1 | Zlib | `LICENSE` is the zlib license | `LICENSE` |
| bzip2 1.0.8 | bzip2-1.0.6 | `LICENSE` is the bzip2 license | `LICENSE` |
| xz 5.8.1 | 0BSD | liblzma is 0BSD; GPL and LGPL files cover only tools and scripts that are not built | `COPYING`, `COPYING.0BSD` |
| zstd 1.5.7 | BSD-3-Clause OR GPL-2.0-only | dual license; the product takes the BSD option | `LICENSE` |
| expat 2.8.1 | MIT | matches | `COPYING` |
| mpdecimal 4.0.0 | BSD-2-Clause | matches | `COPYRIGHT.txt` |
| libffi 3.8.0 | MIT | matches (`LICENSE-BUILDTOOLS` covers build tooling only) | `LICENSE` |
| ncurses 6.5 | MIT | X11-style `COPYING`, matches | `COPYING` |
| libedit 20240808-3.1 | BSD-3-Clause | matches | `COPYING` |
| libuuid 1.0.3 | BSD-3-Clause | `COPYING` only points to `Documentation/licenses/COPYING.BSD-3`, which the archive does not contain; the operative text is the Ts'o three-clause header in each source file | `COPYING`, header of `gen_uuid.c` |
| SQLite 3.53.1 | public-domain | no license file; the sources carry the author's copyright disclaimer | none required |
| Berkeley DB 6.0.19 | Sleepycat | see below | `LICENSE` |

CPython's own `LICENSE` ships as `lib/python3.15/LICENSE.txt`. Its
third-party acknowledgements (mimalloc, HACL\*, and the rest) live in
`Doc/license.rst`, which releases now ship as
`cpython-3.15.1-third-party-licenses.rst`.

## Berkeley DB 6.0.19

- Archive: `db-6.0.19.tar.gz`, SHA-256
  `2917c28f60903908c2ca4587ded1363b812c4e830a5326aaa77c9879d13ae18e`
  (downloaded from the locked URL and compared with the lock).
- `db-6.0.19/LICENSE` (SHA-256
  `b78815181a53241f9347c6b47d1031fd669946f863e1edc807a291354cec024b`) is
  Oracle's BSD-style Sleepycat license, copyright 1990, 2013, followed by the
  UC Regents and Harvard BSD notices and an ASM (Java bytecode, unused here)
  BSD notice. It is not the AGPL, which begins with 6.0.20. Clause 3
  requires binary redistributions to be accompanied by information on how to
  obtain the complete source of the DB software and of any accompanying
  software that uses it; the installed `SOURCES.md` provides that.
- Linkage: in the published `aarch64-unknown-linux-musl` r2 archive, 62 shared
  objects were scanned for the Berkeley DB version string and `__db_ndbm_open`;
  only `lib-dynload/_dbm.cpython-315-aarch64-linux-musl.so` contains them.
  `libpython` and the interpreter do not. The macOS `_dbm` extension links only
  `libSystem` (platform ndbm), so macOS ships no Berkeley DB. The x86-64 Linux
  archive was not rebuilt or scanned for this audit; it uses the same recipe.
- Decision: keep `_dbm` on Linux. Removing it would change the product's
  module set for no compliance gain, since the notices and source offer meet
  the license. The module is the only place the library lives, so removal
  stays a one-file change if the license posture changes.
