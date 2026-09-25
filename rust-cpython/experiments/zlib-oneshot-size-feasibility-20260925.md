# One-shot zlib-rs extension size feasibility, 2026-09-25

**Diagnostic feasibility only; defer the build experiment.** A later mixed
1–4 KiB BLOB comparison found the general one-shot route 8.41% slower in
wall time and 9.00% higher in CPU time, beyond its paired noise. A smaller
extension would not resolve that breadth regression. If the route is revised
and that regression is addressed, test a private-export, dead-stripped link of
the existing one-shot archive. Keep the pinned source, Cargo features,
compiler, optimization level, and routing fixed for that first size pair. The
existing build has enough non-debug code and data that stripping symbols alone
cannot make it close to the platform extension.

## Static evidence

The pinned `libz-rs-sys-cdylib` 0.6.7 `Cargo.toml` makes a `staticlib`. Its
release profile sets `panic = "abort"` and does not request debug information.
The lane builds `cargo build --release --locked --offline --features
custom-prefix`; `build.py` clears ambient `RUSTFLAGS`, then sets
`LIBZ_RS_SYS_PREFIX=python_build_rs_`. The pinned default features include
`c-allocator` and `std`; `custom-prefix` enables `export-symbols`. These are
deliberate ABI choices, so changing features is a second experiment, not part
of the first link comparison.

The finished archive is about 18 MiB, but the installed Mach-O is 1,676,056
bytes. The final `zlib` link uses `-bundle -undefined dynamic_lookup`, ThinLTO,
`-Wl,-export_dynamic`, `-g`, `Modules/zlibmodule.o`, `-lz`, and `libz_rs.a`.
It has no `-dead_strip` or private export list. `binascii` is linked to `-lz`
alone. The installed one-shot module has 63 globally defined
`_python_build_rs_` entry points, including deflate, checksum, and the other
inflate functions. Only `inflateInit2_`, `inflate`, and `inflateEnd` are called
through the prefixed route by `zlib.decompress`. The persistent streams and
`binascii` retain platform libz references. The 63 definitions show that the
current link retains far more of the Rust C API than the one-shot route needs;
they do not establish how much of its shared implementation can be removed.

| Installed Mach-O section/segment | One-shot candidate bytes | Separate platform stage sample bytes |
| --- | ---: | ---: |
| `__text` | 713,724 | 16,624 |
| `__TEXT` file segment | 999,424 | 32,768 |
| `__DATA_CONST` file segment | 49,152 | 16,384 |
| `__DATA` file segment | 16,384 | 16,384 |
| `__LINKEDIT` file payload | 611,096 | 17,128 |
| Whole unstripped file | 1,676,056 | 82,664 |

The candidate in this table is
`/private/tmp/python-build-exp-zlib-oneshot-build-20260925a/rust-cpython/stage/lib/python3.16/lib-dynload/zlib.cpython-316-darwin.so`
(SHA-256 `e2f9a02bffe3f7277e5766d29adfbb6ef316d3f412422918325baabecfd11a38`).
The platform sample is
`/Users/josh/d/python-build/rust-cpython/stage/lib/python3.16/lib-dynload/zlib.cpython-316-darwin.so`
(SHA-256 `5612288b143dfa1130ef645f54f30cd701c1950419260326950b2a7395d60f07`).
These are different stage trees, not the matched timing pair.

The one-shot file starts `__LINKEDIT` at offset 1,064,960. Even deleting its
entire link-edit payload while leaving code/data unchanged would leave at
least that many file bytes, about 999 KiB above the control's 65,536 bytes
before link edit. Real stripping must retain dyld metadata and a valid code
signature. Its symbol table has 12,429 entries, of which 10,288 are local,
and a 274,424-byte string table; removing debug/local symbols has plausible
headroom inside `__LINKEDIT`, but cannot erase the 713,724-byte `__text` or
the 109,784-byte `__TEXT,__const`. These are section-accounting bounds, not
predicted savings. The two builds have distinct PGO profiles, so small
control differences should not be assigned to the backend.

The unstripped one-shot extension is 1,593,392 bytes above the separate
platform sample at the exact paths inspected here. The matched public-workload
comparison instead used
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/lib/python3.16/lib-dynload/zlib.cpython-316-darwin.so`
(82,760 bytes; SHA-256
`2aef4049da6abe4b4e6725f2f79f692ef8f8b3148aa87903a0d40cdef3ef50bd`).
That is a different build artifact with a different hash, 96 bytes larger
than the platform sample. The exact cause of those 96 bytes was not isolated;
the builds have distinct PGO profiles, so attributing them to zlib code would
be unsound. The matched extension gap is 1,593,296 bytes. The existing build
report separately gives a 1,593,456-byte combined `zlib` plus `binascii`
gap for its recorded pair. None is a packaged-size result.

## Candidate recipe experiment

In a fresh isolated build, preserve the current archive and all configure
inputs. Change only the generated `Modules/zlib$(EXT_SUFFIX)` link rule for
the candidate to add `-Wl,-dead_strip` and an export list containing exactly
`_PyInit_zlib` (Darwin `-Wl,-exported_symbol,_PyInit_zlib` is the proposed
syntax). Keep `-lz` before the static archive and keep `binascii` on `-lz`.
Record the complete effective link command because CPython currently injects
`-Wl,-export_dynamic`; if that option defeats the export list, remove it only
for this one extension in the same candidate recipe, never globally. An
explicit per-extension generated Makefile edit with exact old/new rule checks
is the narrow place to apply this. Do not alter the archive or the CPython
wrapper for the first comparison.

Use the identical packaging strip and re-sign procedure on matched control
and candidate copies after each link. Record both unstripped and stripped
file bytes and SHA-256, `size -m` sections, `otool -l` link-edit/symbol-table
fields, `nm` defined/undefined symbols, and `otool -L`. Stripping is a
separate packaging measurement; it must not be credited as dead-code removal.

If the linker experiment saves little code/data, a separate same-pin Cargo
probe could try `--no-default-features --features c-allocator,custom-prefix`
to omit the default `std` feature while retaining the C allocator and prefixed
ABI. This may fail to build or change panic/allocator behavior and requires a
new correctness and speed comparison. It is not evidence for the first
candidate's expected savings.

## Hazards and acceptance

Dead stripping can discard a Rust routine reached through an indirect table
or assembly reference if the linker cannot see the edge. Export filtering
must still leave `_PyInit_zlib` visible to import machinery. The module must
continue to *define* the three required prefixed Rust functions internally
even if `nm -g` no longer lists them as exports; inspect all symbols or the
link map for those definitions and their call targets. It must define no
unprefixed zlib entry points. It must retain undefined platform
`_inflateInit2_`, `_inflate`, `_inflateEnd`, `_inflateCopy`, and
`_inflateSetDictionary`, and `/usr/lib/libz.1.dylib` as a load command.
`binascii` must continue to load platform libz alone. Its imported extension
must keep the platform 1.2.12 runtime identity. Signed Mach-O bytes must
launch after stripping.

The general route must first clear the mixed 1–4 KiB BLOB regression against
the matched platform control. Then accept a link change only if the *stripped
installed* `zlib` extension is smaller than the matched stripped one-shot
control, `__text` plus the relevant
constant/data sections also shrink (showing more than symbol removal), the
one-shot and persistent-stream semantic checks pass, and the established
direct decode and synthetic small-BLOB speed gains remain outside the paired
noise intervals on a quiet host. Measure CPU time and memory as well as wall
time; current memory parity is unresolved, so a size gain cannot qualify the
candidate by itself. Reject the change if symbol separation fails, if the
mixed BLOB regression remains beyond noise, if direct decode speed
falls back inside noise, or if code/data size does not improve enough to
justify a new link exception. Report exact byte changes rather than a target
percentage. Run the size and symbol check before any expensive performance
work.

This lane ran only small read-only `ar`, `nm`, `size`, `otool`, `rg`, and file
inspection commands against the existing one-shot worktree and a sampled
platform stage. It ran no build, benchmark, test suite, formatter, linter, or
hook, and created no compiled artifacts. No substantial command required
resource accounting.
