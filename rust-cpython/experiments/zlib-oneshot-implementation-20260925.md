# One-shot zlib-rs inflate implementation, 2026-09-25

This lane adds the optional `build --zlib-oneshot` mode. The pinned zlib-rs
0.6.7 archive is built with the existing `python_build_rs_` symbol prefix and
linked into `zlib` alongside platform libz. `binascii` remains linked only to
platform libz. The new guard routes the local stream in `zlib.decompress` from
`inflateInit2_` through all `inflate` and `inflateEnd` calls to the prefixed
Rust ABI. All persistent public and private inflater streams, including copy
and dictionary operations, retain unprefixed platform calls. Deflate,
checksums, and version identity also remain on platform libz. The ordinary
build and `--zlib-hybrid` retain their existing mode selection and routing.

The source inspection used the pinned `Modules/zlibmodule.c` copy at SHA-256
`36390fc1b0bdaf7da332d732c67cbe9669bd3f6e923a3e5810b4662159a0e20c`.
Its one-shot body had one initialization, one inflate call site, and six end
call sites. All six ends now use the same backend as the initialization;
initialization's `Z_MEM_ERROR` path retains its prior behavior of reporting
failure without calling end on an uninitialized stream. Other inflate calls
remain outside that body. The source archive blob itself was unavailable in
this worktree; the source copy was from the existing pinned-source inspection
tree, and a fresh locked-archive extraction remains part of a later build.

The installed-module report requires a platform libz load command, prefixed
Rust definitions for one-shot init/inflate/end, and undefined platform
references for init/inflate/end/copy/dictionary. It rejects unprefixed zlib
definitions in the extension and checks the platform runtime version. These
symbol checks, together with the source call-site audit, distinguish the route
from the all-stream hybrid. The build report records `oneshot-inflate` as its
backend kind and the explicit wrapper route. Conflicting candidate flags fail
before fetch or build work starts.

Static checks completed: Python AST parsing; JSON parsing and SHA-256 checks
for every patch manifest entry; `git apply --check`, forward application, and
reverse application of 0002 then 0003 on a fresh copy of the pinned source
file; and exact one-shot call-site counts after patching. No full build, runtime
test, formatter, linter, benchmark, or `/usr/bin/time -l` resource run was
performed in this lane. There were no substantial commands to account for
with CPU, RSS, or swap fields. An initial patch-file creation command failed
on patch-tool syntax and produced no file; the following generated patch had
an extra diff header, which was removed before the successful checks. No
build or benchmark attempt was discarded.

The remaining risks are C ABI behavior on malformed input, final Mach-O
symbol retention, and size and performance effects. The split should remove
Rust from the source-tar workload's private streaming path, but that outcome
has not been measured. A qualified build should exercise one-shot errors and
streaming consumers, inspect the installed module, then compare source-tar,
one-shot decode, memory, and stripped size against the matched control.
