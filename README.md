# python-build

python-build builds a relocatable CPython 3.15.1 distribution from locked
sources for Apple Silicon macOS and x86-64/arm64 Linux musl. It keeps the GIL,
shared libpython, private native dependencies, ThinLTO, macOS PGO, and useful
extension development metadata.

The distribution excludes pip, ensurepip, venv, Tcl/Tk, `_gdbm`, regression
tests, and bytecode caches. SQLite includes FTS3/4/5, geopoly, rtree, dbstat,
and loadable extensions. `compression.zstd` supports multithreading.

## Build and qualify

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

`qualify` applies required installed-tree fixes, runs the CPython regression
suite on a disposable pre-prune copy, validates the packaged payload and
archive extraction, then publishes the archive and `artifact.json`
transactionally under `dist/<target>/`. Optional reference comparisons and
two-build reproduction are separate commands:

```sh
python3 build.py compare-reference --target aarch64-apple-darwin
python3 build.py reproduce --target aarch64-apple-darwin
```

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

## Release assembly

`build/uvmirror.py` validates the three target artifacts and their manifests,
then creates uv metadata and checksums in a new output directory. The
workflow-dispatched release path smoke-tests those exact archive bytes
through a local mirror before publishing. Release tags are bound to the
source revision recorded by the build.
