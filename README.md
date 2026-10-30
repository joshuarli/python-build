# python-build

python-build builds a relocatable, fully OpenSSL-free CPython 3.15.1
distribution from locked sources for Apple Silicon macOS and x86-64/arm64
Linux musl. It keeps the GIL, shared libpython, private native dependencies,
ThinLTO, and useful extension development metadata. PGO is deferred. No glibc
enters any artifact: Linux binaries use the musl loader with statically
linked musl in the Rust extensions.

The distribution excludes pip, ensurepip, venv, Tcl/Tk, `_gdbm`, regression
tests, and bytecode caches. SQLite includes FTS3/4/5, geopoly, rtree, dbstat,
and loadable extensions. `compression.zstd` supports multithreading.

The next stage is the [production closeout and Rust performance plan](plan.md).
[Rust-for-CPython](rust-for-cpython.md) is an isolated research interpreter,
not the shipping CPython 3.15.1 distribution.

## Compile and qualify

Run `doctor` to inspect the host and pinned toolchain requirements. Fetch
locked inputs before compiling:

```sh
python3 build.py doctor
python3 build.py fetch --target aarch64-apple-darwin
python3 build.py build --target aarch64-apple-darwin
python3 build.py qualify --target aarch64-apple-darwin
```

Linux uses the locked Alpine image and package closure through Docker BuildKit.
The x86-64 target uses `linux/amd64`; arm64 uses `linux/arm64`. Native runners
provide qualification evidence; emulated timing is not performance evidence.
Linux artifact manifests list the target musl interpreter and platform
libraries observed in the payload. The minimal runtime qualification image
installs only the pinned Alpine `libgcc` runtime package when required.
Qualification checks the final binary bytes: Linux interpreters must be
ET_DYN, every ELF must have full RELRO with eager binding and no writable
executable load segment or text relocation, and every macOS executable must
carry `MH_PIE`.

`qualify` applies required installed-tree fixes, runs the CPython regression
suite on a disposable pre-prune copy, validates the packaged payload and
archive extraction, then publishes the archive and `artifact.json` as one
immutable generation under `dist/<target>/generations/`, selected by an
atomic `dist/<target>/ACTIVE` file (`buildsys/generations.py`); readers
verify the active generation's recorded sizes and digests. Optional reference comparisons and
two-build reproduction are separate commands:

```sh
python3 build.py compare-reference --target aarch64-apple-darwin
python3 build.py reproduce --target aarch64-apple-darwin
```

## Hardening verification

The final-byte PIE, RELRO, stack, and relocation gates passed on local `dist`
archives from revision `7919f20`: macOS arm64 archive
`17c6abab5aa980de5bbcfa48c8bf10865dc30ea907b33ab7d41f5a3c33c7a918` passed
the Mach-O validator across 79 images with no non-PIE executables; Linux arm64
archive `fcd4d2861a221286d1db38c3fdf81e60a078cb0ac3cf8d3dfb2e1e929b1ce204`
passed the ELF validator across 79 images, including ET_DYN executables, full
RELRO, a non-executable stack, and no writable-executable segments or text
relocations.

Fresh native `qualify` runs at revision `95d7ccd` also passed for macOS arm64
and Linux arm64. Their archive digests are
`3b52ab9384ce61cfb2b2580f46ed73e080ee7866a4f4a7920f952f5db28b599e` and
`14e22ab8453c14e1ba1385089fb7b325bd8565808da906b4c4391e0158e7138e`,
respectively. The macOS manifest reports no non-PIE executables among 64
Mach-O images. All 64 Linux ELF images passed PIE, RELRO, NX stack, writable-
executable segment, and text-relocation checks; stack-protector and fortify
evidence passed. Both complete regression runs had no unexpected failures.
These fresh archives were qualified in an isolated worktree and did not
replace the local `dist` files.

Those earlier local results are historical. The [2026-10-26 CI release](https://github.com/laputa-systems/python-build/actions/runs/40330042202)
passed native builds, qualification, assembly and fresh uv installation on all
three targets at `3edfbdd0`. Later revisions require new qualification.
macOS 27 is the only supported macOS release; its runtime check is [P2](plan.md).

Controller tests run with:

```sh
python3 build.py controller-test
```

## Inputs and trust

`sources.lock.json` pins CPython, native dependencies, and the Mozilla CA
bundle. `bootstrap.lock.json` pins upstream LLVM 23.1.4 on macOS, native-musl
LLVM 23.1.3-r0 on Linux, and the platform bootstrap requirements. Sealed
builds consume verified cached inputs without network access.

OpenSSL's configured trust sources take precedence. When no explicit override
or usable default source exists, Python's default TLS context loads the
packaged Mozilla bundle. `PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE=1` disables this
fallback. The bundle is pinned at package time and is not updated at runtime.

## TLS backend

TLS and hashing run on the RTLS/rustls-graviola backend with a modern
TLS 1.2/1.3-only policy. No OpenSSL source enters the product candidate (the pinned separate
reference build may use OpenSSL), and no OpenSSL or
glibc symbols remain in the payload. CPU floors are Apple M1, x86-64
Broadwell, and ARMv8-A with crypto extensions. The backend design, contracts,
replay procedures, and per-architecture qualification live in
[`backend`](backend/README.md).

## Release assembly

`build/uvmirror.py` validates the three target artifacts and their manifests,
then creates uv metadata and checksums in a new output directory. The
workflow-dispatched release path smoke-tests those exact archive bytes
through a local mirror before publishing. Release tags are bound to the
source revision recorded by the build.

## Optional Nix-backed Linux builder prototype

The [Nix bootstrap prototype](nix/README.md) uses pinned Nix inputs to
materialize the **same** Alpine/APK and native-musl Rust toolchain into Docker
build environments for amd64 and arm64. It is explicitly opt-in and does not
replace the existing build or qualification path. Native Docker validation
and full independent release qualification are still required.
