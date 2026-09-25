# Zipfile central-directory headroom scout, 2026-09-25

**Decision: no native-kernel experiment yet.** The pinned source exposes a
per-entry Python parsing loop, so `ZipFile._RealGetContents` is a plausible
cost for archives with many entries. No existing profile measures its share of
a complete wheel task. The registered wheel task also reads and checks roughly
2.10 MiB of member data per archive, so a faster directory parser could have
little end-to-end effect. The registered cold import task takes a separate
`zipimport._read_directory` path and would not exercise a change confined to
`ZipFile._RealGetContents`.

## Evidence inspected

- The experiment pins Rust-for-CPython CPython 3.16.0a0 at
  `b812b4a7b9efaca46b98544a8633b7d7e454166b` in
  [`sources.lock.json`](../sources.lock.json). The extracted
  `Lib/zipfile/__init__.py` and installed copy have the same SHA-256,
  `6278152bb420f29870d46c4d975f564a215fcd31f543157242dd9470faedba61`.
  The extracted source was read only.
- [Pinned `ZipFile.__init__` and `_RealGetContents`](https://github.com/Rust-for-CPython/cpython/blob/b812b4a7b9efaca46b98544a8633b7d7e454166b/Lib/zipfile/__init__.py#L1898-L2095) call the directory reader for read and append modes. That method finds the end record, seeks and reads the central directory through the supplied file object, then loops over entries. Each entry unpacks a fixed header, decodes its name, constructs `ZipInfo`, stores extra/comment bytes, calls `ZipInfo._decodeExtra`, and updates `filelist` and `NameToInfo`. It finally sorts entries by local-header offset to set `_end_offset`. This is a plausible source of Python dispatch and object-allocation cost; source inspection does not quantify it.
- [`benchmarks/workloads/zlib.py`](../../benchmarks/workloads/zlib.py) creates a fixed method-8 wheel-shaped ZIP with 64 small modules, two 1 MiB resources, and one metadata member. `zip_read_wheel` opens it from `io.BytesIO`, checks `namelist()`, reads all 67 members by name, and compares decoded bytes. Its registered standard count is four archives, or 268 entries and 8,413,264 decoded bytes ([`registry.py`](../../benchmarks/workloads/registry.py)). The workload's unit is an extracted byte, so a directory-only speedup could be diluted by member read, decompression, checksums, and the full output comparison.
- `zipimport_cold` writes a two-member ZIP and starts one fresh interpreter per import, three times in the standard profile. The pinned [`Lib/zipimport.py`](https://github.com/Rust-for-CPython/cpython/blob/b812b4a7b9efaca46b98544a8633b7d7e454166b/Lib/zipimport.py#L295) uses its own `_read_directory` and directory cache. It does not call `ZipFile._RealGetContents`; the latter has zero direct headroom for this registered task.
- The existing [zlib probe](zlib-probe-20260924.md), [whole-build result](zlib-full-candidate-20260924.md), and [hybrid qualification](zlib-hybrid-qualification-20260924.md) report mixed or noise-limited complete ZIP timing while changing the decompression backend. They neither isolate directory parsing nor establish its CPU share. No `zip_read_wheel` directory profile was found among the checked-in experiment reports.

## Contract exposed by this boundary

An implementation would need to preserve reads, seeks, tells, exceptions, and
their order for arbitrary seekable file-like inputs, including short reads and
I/O errors. It would also need to preserve ZIP and ZIP64 end-record offsets,
prepended data, truncation and bad-signature errors, archive and per-member
comments, `metadata_encoding`, UTF-8 flag and Unicode-path extra-field
decoding, filename sanitization, ZIP64 extra-field validation, and unsupported
version errors. `ZipInfo` instances, `filelist` order, duplicate-name
`NameToInfo` overwrite behavior, and `_end_offset` overlap boundaries are
observable through `infolist()`, `getinfo()`, `open()`, and `read()`.

`ZipFile` subclasses can override `_RealGetContents`, and `ZipInfo` and its
`_decodeExtra` method are replaceable Python objects. A native parser inserted
inside the current method would cross constructor and method-call boundaries
that can have side effects. A guarded path would need explicit conditions for
those cases and for `debug` output; ordinary Python fallback alone cannot
justify a speed claim until a representative workload actually takes the
guard. Member streaming, encryption, local-header verification, decompression,
and CRC checks occur later in `open()` / `ZipExtFile`, so a directory kernel
would not subsume them.

## Smallest next diagnostic

When the host is quiet, run **one diagnostic profile** of the existing pinned
interpreter executing the unchanged registered `zip_read_wheel` with its four
iterations. Keep the fixed input digest and output check. Record `_RealGetContents`
call count, cumulative and own profiler time, and enclosing `ZipFile.__init__`,
`ZipFile.read`, `ZipExtFile.read`, and decompressor rows; retain the raw profile
and `/usr/bin/time -l` user/system CPU, elapsed time, peak RSS, and swaps.
Profiler times overlap and are instrumented location evidence, not a speed
result. If directory construction is only a small fraction of the complete
task, stop this hypothesis. If it is material, measure an uninstrumented
complete-task baseline and self-comparison noise before designing a kernel.
The two-entry cold import task should be assessed independently through
`zipimport._read_directory` if a profile points there.

This scout ran no profile, benchmark, compiler, test suite, formatter, linter,
or hook because a paired Django benchmark was active. It has no new wall,
kernel CPU, memory, or allocation measurements. File reads and this note were
the only work; no substantial timed command was run, so there is no
`/usr/bin/time -l` command record for this scout.
