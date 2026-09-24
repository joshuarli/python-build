Upstream source: locked CPython source-deps zstd 1.5.7 tarball, SHA-256 in
`sources.lock.json`.
Origin: local Fil-C port adaptation of the upstream zstd source; zstd is
licensed under BSD-3-Clause and GPL-2.0, with the BSD-3-Clause option used
for this build.

Explanation: `ZSTD_NO_ASM=1` excludes the standalone x86 assembly source, and
`ZSTD_DISABLE_ASM=1` selects zstd's portable C BMI2 path. Five x86 loop
alignment hints in otherwise portable C remain under generic compiler/CPU
guards. Fil-C rejects their `.p2align` inline assembly at runtime. This patch
also guards those hints with zstd's own disable-assembly switch. The
compressor's `ZSTD_selectAddr` has a separate x86 `cmova` assembly block
whose result is a pointer; Fil-C rejects pointer-returning inline assembly.
Guard it with the same switch so the existing portable conditional path is
used. The loops and compression/decompression algorithms remain enabled.

Scope: `x86_64-filc-linux-musl` only. Ordinary musl and macOS recipes retain
the locked upstream source and existing flags.

Applicability check: `patch -p1 --fuzz=0 --dry-run` on the verified source.

Regression test: build the static multithreaded zstd archive with Fil-C and
run `.github/scripts/toy.py` and the packaged distribution's zstd round-trip
checks. The toy failed at `ZSTD_decompressSequences_bmi2` with Fil-C's
unsupported `.p2align` diagnostic before this patch. The full installed
`test_zstd`, `test_tarfile`, `test_zipfile`, and `test_shutil` suites reached
the pointer-returning `cmova` path and trapped before the additional guard.
