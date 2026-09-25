# One-shot zlib-rs native build qualification, 2026-09-25

**Build result: succeeded as an optional experiment.** A clean offline
`build --zlib-oneshot` installed CPython 3.16.0a0 at
`/private/tmp/python-build-exp-zlib-oneshot-build-20260925a/rust-cpython/stage`.
The builder's installed-module smoke passed. This lane did not run the CPython
test suite or a performance comparison.

## Inputs and source route

The lane cloned the pinned CPython, zlib-rs 0.6.7, LLVM archive and attestation
blobs from an earlier experiment into its own cache, then checked every blob's
SHA-256 against its lock. It copied the Cargo registry and LLVM toolchain into
the lane. No network fetch or writable compiled output was shared. `doctor`
passed with the pinned nightly-2026-09-15 Rust toolchain, LLVM 23.1.2, Xcode
26.6 and SDK 26.5. The build used the offline `sandbox-exec` network boundary
and Cargo offline mode.

A fresh extraction of locked CPython commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b` applied patches 0001–0003
with forward and reverse checks. `Modules/zlibmodule.c` changed from SHA-256
`36390fc1b0bdaf7da332d732c67cbe9669bd3f6e923a3e5810b4662159a0e20c`
to `34aeebe0492cf4ff6570f7b1a59f6cd53862383f98c73990ae3d340bcc2bca9f`.
The built source retained the latter hash. Preprocessing the mode guard
expanded the local `zlib.decompress` init/inflate/end calls to prefixed Rust
names; the persistent init/inflate/end/copy/dictionary names remained
unprefixed. The manifest SHA-256 was
`b806f42e6a54bb453cc3c99a338afcc1803beaf0cf8e604c1bb62ba820c5619b`,
and patch 0003 matched its manifest digest.

## Build attempts and resource limit

The first full build failed during parallel make. The existing URL extension
rule created `Modules/_rust_url_quote` only while building its Rust archive;
make began compiling its C object before the directory existed. The
`rust-cpython/build.py` driver now creates that build output directory after
configure and before make. The second full build succeeded. No authored source
patch or patch manifest changed in this lane.

| Timed command | Result | User + system CPU s | Elapsed s | Max process RSS bytes | Swaps |
| --- | --- | ---: | ---: | ---: | ---: |
| Copy pinned inputs | passed | 0.01 + 0.71 | 0.87 | 2,048,000 | 0 |
| Fresh-source preflight 1 | harness error | 1.04 + 1.52 | 2.92 | 43,810,816 | 0 |
| Fresh-source preflight 2 | passed | 1.05 + 2.00 | 3.45 | 40,534,016 | 0 |
| Full build 1 | directory race | 113.78 + 44.95 | 129.41 | 449,249,280 | 0 |
| Full build 2 | passed | 700.52 + 104.41 | 257.38 | 1,819,181,056 | 0 |

The first preflight's synthetic C snippet omitted a closing `#endif`; the
corrected second attempt passed. All five raw `/usr/bin/time -l` outputs are
under `rust-cpython/work/resource-logs/`, with the first build's phase logs in
`attempt-01/` and the completed build's phase logs in `rust-cpython/logs/`.
Timed commands totaled **969.99 kernel-accounted CPU seconds**, below the
1,200-second command-tree budget. The largest reported process RSS was
1,819,181,056 bytes, below the 3 GB limit. Host allocated swap remained
243.88 MiB before and after; every timed command reported zero swaps. An
initial separate SHA-256/doctor invocation (6.36 seconds elapsed) and final
read-only inspection were untimed, so 969.99 seconds is the exact timed-command
sum, not an exact total for every lane command.

`/usr/bin/time -l` reports kernel child CPU for the waited command and its
reaped descendants, including short-lived compiler processes. Its maximum
RSS is the largest process resident set, not simultaneous tree RSS. Process
count, unique memory, and proportional memory were not measured. Raw records
and paths are indexed in `data/zlib-oneshot-build-20260925.json`.

## Installed module evidence and size

The build report records `oneshot-inflate` and an installed `zlib` SHA-256 of
`e2f9a02bffe3f7277e5766d29adfbb6ef316d3f412422918325baabecfd11a38`.
The module defines prefixed Rust `inflateInit2_`, `inflate`, and `inflateEnd`;
it has undefined platform `inflateInit2_`, `inflate`, `inflateEnd`,
`inflateCopy`, and `inflateSetDictionary` references. Both `zlib` and
`binascii` load `/usr/lib/libz.1.dylib`. There are no unprefixed zlib entry
point definitions in the module. Its public header and runtime version are
both platform `1.2.12`. The exact symbol and load-command output is retained
in `rust-cpython/work/resource-logs/installed-symbols-01.log`.

| Installed unstripped extension bytes | Platform control | All-stream hybrid | One-shot candidate |
| --- | ---: | ---: | ---: |
| `zlib` | 82,664 | 1,675,688 | 1,676,056 |
| `binascii` | 93,152 | 93,216 | 93,216 |
| Combined | 175,816 | 1,768,904 | 1,769,272 |

The one-shot pair is 1,593,456 bytes larger than the matched platform pair
and 368 bytes larger than the all-stream hybrid pair. These are installed
unstripped extension sizes from the pinned fork stages, not product packaging
sizes. Paths and PGO profiles differ among builds, so small byte differences
cannot be attributed solely to the mode's code. The symbols, route check, and
built-in smoke establish build wiring; semantic edge cases and application
performance remain for separate qualification.
