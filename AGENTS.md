# python-build

Independent build system that compiles **CPython 3.14.6** plus its in-scope
native dependencies from locked sources and produces a relocatable,
dynamically linked installation. Astral's python-build-standalone (PBS) is a
technical reference and comparison target only: never fork, vendor, import,
or execute its build engine, and never copy its binaries into the product.
(In-code `(plan …)` comments are anchors to the retired `plan.md`; this file
is the current contract.)

## Targets (`buildsys/targets.py` is the only file that branches on target)

| Triple | Family | Toolchain | Notes |
| --- | --- | --- | --- |
| `aarch64-apple-darwin` | macos | Homebrew LLVM 23.1.0+ (`bootstrap.lock.json`) + Xcode 26.x SDK | arm64 only, `-mcpu=apple-m1`, `-mmacosx-version-min=26.0`; host must run macOS 26.0+ |
| `x86_64-unknown-linux-musl` | linux-musl | Alpine 3.24.1 container (`Dockerfile`), clang22/lld22 | `-march=x86-64`, loader `/lib/ld-musl-x86_64.so.1`; frozen, completed |
| `aarch64-unknown-linux-musl` | linux-musl | Same, via `docker build --platform linux/arm64` | `-march=armv8-a`, loader `/lib/ld-musl-aarch64.so.1`; frozen, completed |

Policy everywhere: ThinLTO (`--with-lto=thin`), PGO enabled on macOS using
CPython's `-m test --pgo -j <jobs>` profile task and the locked LLVM
`llvm-profdata`, no PGO on Linux, no BOLT/JIT/tail-call interpreter,
GIL-enabled release ABI, `-O3`. CPython's macOS PGO build omits frame
pointers because retaining them makes CPython's deep recursion regression
tests abort; other native builds keep them. Unknown
targets fail closed with `target not implemented`; build/test/package
commands require the requested target to match the running machine (no
cross-compiling).

## Product scope (enforced by `buildsys/scope.py`, asserted by validation)

Ships: exact 3.14.6 interpreter (`bin/python3.14`), shared libpython,
useful stdlib inventory, private statically-linked native deps, headers plus
`python3.14-config`/sysconfig/pkg-config metadata sufficient to build and
load a native extension with no installer present.

Deliberately absent (tested absences, not omissions): `pip`, `ensurepip`
(with its bundled wheel), `venv`; `_tkinter`, `tkinter`, `idlelib`,
`turtle`, `lib/python3.14/test` (retained through regression validation only),
generated `.pyc`/`__pycache__`, and the Tcl/Tk+X11 closure; `_gdbm` (dbm
backend is `ndbm` on macOS, Berkeley DB on Linux). macOS additionally takes
zlib, libedit, ncurses/panel from the platform (`/usr/lib`) and bundles
OpenSSL, SQLite, Expat, libffi, bzip2, xz, zstd, mpdecimal from source; it
builds no libuuid or Berkeley DB (`_uuid`/dbm use platform facilities). Linux
bundles all thirteen.

SQLite enables FTS3/4/5 (including the enhanced FTS3 query syntax), geopoly,
rtree, dbstat, and CPython's loadable-extension API; applications must still
explicitly enable extension loading on each connection. `compression.zstd`
uses the zstd multithread-capable static library on all targets.

## Commands

```text
python3 build.py doctor                                  # host/SDK/toolchain report, no side effects
python3 build.py fetch --target <triple>                 # verify + populate .cache (online; skips reference-only)
python3 build.py build --target <triple> --dev [--pgo-jobs N] # deps + CPython, non-hermetic iteration
python3 build/sealed.py [--pgo-jobs N]                    # sealed macOS qualification (sandbox-exec, offline)
docker build --platform <plat> --target sealed .         # sealed Linux qualification (BuildKit --network=none)
python3 build.py test --target <triple>                  # controller + distribution tests
python3 build.py compare-reference --target <triple>     # parity report only
python3 build.py package --target <triple>               # strip, validate, archive, write dist/ reports
python3 build.py reproduce --target aarch64-apple-darwin [--pgo-jobs N] # two clean sealed builds
python3 build/uvmirror.py --tag <tag> --repo <o/n>       # rename dist/ archives to Astral layout + uv metadata
```

`build.py` is CLI only; logic lives in `buildsys/` (shared) and `build/`
(phase drivers). `--sealed` via `build.py` is rejected with directions: the
sealed paths above own offline qualification. Keep packaging separate from
compilation so a validated tree can be repackaged without rebuilding.

## Layout

`build.py`, `buildsys/` (controller, recipes, `macho.py`, `sandbox.py`,
`relocate.py`, validation, `uvmirror.py`), `build/` (phase drivers only),
`sources.lock.json`, `bootstrap.lock.json`, `Dockerfile` (Linux; macOS never
builds in it), `patches/` (each with provenance + regression link),
`tests/`, `dist/<triple>/`, `.github/` (CI + smoke toy). No `docs/` tree:
evidence lives in `dist/*.json`/`parity.md`, produced by the controller.

## Inputs, locks, cache

- `sources.lock.json`: every source with URL, version, sha256, size, role
  (`source`/`reference`/`test`), license, purpose. Digests verified before
  extraction; reference-only entries are comparison inputs, never build
  inputs. `pip` is not an input (nothing unshipped gets locked).
- `bootstrap.lock.json`: Alpine image digest + resolved apk set (Linux);
  Homebrew LLVM bottle digest, make, pkgconf, Xcode/SDK identity,
  deployment floor, CPU baseline (macOS). The macOS linker is recorded, not
  pinned: clang's driver supplies the matching `libLTO`.
- `buildsys/inputs.py`: content-addressed `.cache/objects/<sha256>.blob`,
  atomic publication, tamper/size checks on every read, `safe_extract`
  rejecting traversal/absolute/symlink-escape/device entries.
- `buildsys/deporder.py`: per-family dependency sets and order; macOS order
  is fast-failure (cheap first, OpenSSL last).
- `buildsys/patches.py`: patches apply against verified trees, fail on
  rejects; every patch needs origin, license/attribution, explanation,
  applicability check, reproducer. Do not import PBS module machinery,
  BOLT/JIT, GUI, or older-platform patches. macOS PGO is CPython's native
  `--enable-optimizations` flow with the profile task below; do not import or
  execute PBS build code.

## macOS specifics

- `buildsys/bootstrap.py`: lock loading, host verification (`problems()`),
  `lto_smoke_test` gate before any large build (ThinLTO bitcode + minos +
  arm64 checked, not just exit status). Apple `ld` is used via the clang
  driver; never silently fall back to Apple clang.
- `buildsys/cpython.py`: configure policy derived from 3.14.6's
  `configure --help`; private-prefix selection vars; `PKG_CONFIG_LIBDIR`
  narrowed so Homebrew packages cannot satisfy probes; `ndbm` dbm order;
  platform libedit; `--enable-optimizations` with
  `PROFILE_TASK="-m test --pgo -j <jobs>"`; and
  no frame pointers for the PGO interpreter, matching the pinned PBS build.
  The deep recursion suite remains a required runtime check. `build/cpython.py`
  selects locked `llvm-profdata` and writes the exact recipe, including the
  merged profile-data hash and fixed `PYTHONHASHSEED`, to
  `build/logs/cpython-build.json`;
  `--pgo-jobs N` pins the test worker count for a replay, with CPython's
  compile parallelism (one fewer than host CPUs) as the default.
  `python3 build.py reproduce --target aarch64-apple-darwin` repeats the
  sealed build from cleared work/stage trees and compares the recipe,
  profile data, and compiled Mach-O content separately. A matching locked
  recipe proves the build can be recreated from its inputs; varying PGO
  counters can still change profile bytes and machine code, so only an
  identical profile and compiled content count as byte reproducibility.
- `buildsys/sandbox.py`: `(deny network*)` profile, writes restricted to
  declared outputs (+ Darwin linker scratch), reads unrestricted, allowlist
  environment. `network_boundary_selftest` proves the denial against a
  loopback listener before/after the build. The profile permits
  `ipc-posix-sem`: denying it silently removes `SemLock` from
  `_multiprocessing` with no build error. Containment is weaker than a
  container; reports must say so.
- `buildsys/macho.py`: header/load-command parsing (arch, `LC_BUILD_VERSION`
  minos, install names, `@rpath`), `install_name_tool` edits that always
  re-sign (unsigned Mach-O does not launch on Apple Silicon).
- No `DYLD_*` in the product or its tests; system dylibs may exist only in
  the dyld shared cache, so classify load commands by name, not by file
  presence. Scrub build-only prefix/toolchain paths from consumer-facing
  sysconfig/Makefile (`buildsys/relocate.py`); shebang rewrite is the
  sh/python polyglot. A relocatable libpython means an out-of-tree embedder
  must set `PYTHONHOME` or live in-tree; record that cost, don't hide it.

## Validation and packaging (`build/package.py`, `buildsys/validate_macos.py`, `buildsys/testsuite.py`)

Package operates on the staged tree: strip (preserving exported symbols;
re-sign on macOS), validate the packaged bytes, deterministic `tar.gz`
with top-level `python/` (`SOURCE_DATE_EPOCH=1704067200`, sorted entries,
fixed owners/modes), refuse to overwrite an existing archive. `dist/`
gets the archive, `SHA256SUMS`, `inputs.json`, `components.json`,
`provenance.json` (`build_mode` sealed vs development, including the exact
macOS PGO recipe and locked `llvm-profdata` identity), `validation.json`,
`parity.json`/`parity.md`, `benchmarks.json` (+ `reproducibility.json` on
macOS).

Checks, against the installed tree with build-prefix/Homebrew scrubbed:
Mach-O arch/minos/allowlisted load commands/signatures; version 3.14.6 +
GIL/ABI/tags; module inventory with required-vs-excluded split; real
round-trips (TLS both directions, sqlite, ndbm, compression incl.
`compression.zstd`, decimal, uuid, Expat); multiprocessing queue+pool
(`SemLock` present); curses/panel/readline; ctypes both directions +
callbacks + private dylib; extension build/load and ABI3 fixture with no
installer present; C embedding via shipped shared libpython (both placement
recipes); relocation under a path with spaces; launcher scripts; broad
CPython regression suite on a disposable pre-prune install copy with narrow,
justified exclusions only; PBS-adapted distribution checks run on the final
post-prune bytes for SQLite's feature/security profile, locked OpenSSL/SQLite
versions, zstd multithreading, libc ABI tags, interpreter startup through
symlinks and unusual `argv[0]`, and Linux sysconfig/MDWE behavior. The
Windows-only SSL key-log check, GUI, `venv` path-resolution path, and glibc
Linux syscall checks are reported as out of scope. Final validation asserts
the regression package, `.pyc`, and `__pycache__` caches are absent from the
release tree. Parity rows are `match`/`intentional_difference`/`gap`/
`untested`; macOS benchmarks must record the profile task, worker count, LTO
mode, and a paired noise interval against the reference.

## Reference baseline (comparison only)

PBS release `20260610`, commit `f1d7b92`, fixed per-target
`install_only`/`install_only_stripped` archives (fingerprints were in the
retired plan appendices; current pins live in `sources.lock.json` as
`reference-pbs*`). Run reference binaries only in the isolated comparison
root, never on the bare host, and never let their bytes become inputs.

## CI and releases (`.github/workflows/build.yml`)

`workflow_dispatch` only. Matrix: `macos-26` native; `ubuntu-latest` +
`ubuntu-24.04-arm` through `Dockerfile --target sealed`, then package
inside the image with `--network none`. Caches: `.cache/objects` (keyed on
`sources.lock.json`) and BuildKit `type=gha` layers per arch; never cache
compiled outputs. `assemble` runs the scope and mirror regression tests, and
`buildsys/uvmirror.py` rejects any asset over 1.2x the corresponding pinned
Astral `20260610` `install_only_stripped` archive size. It then renames to
`cpython-3.14.6+<tag>-<triple>-install_only_stripped.tar.gz` and emits
`SHA256SUMS`, `download-metadata.json` (own release URLs), and
`smoke-metadata.json` (canonical prefix for the mirror rewrite).
Smoke (before release): `uv python install <exact key>
--python-downloads-json-url …/smoke-metadata.json` with
`UV_PYTHON_INSTALL_MIRROR=file://…`, then `.github/scripts/toy.py`
(stdlib-only) — natively on macOS, inside `alpine:3.24` for Linux.
`release` (needs all smokes) creates the GitHub **prerelease** with those
assets. CI builds are dev-mode; sealed qualification stays local.

## Working rules

- Keep the frozen Linux code and its unit tests green; macOS changes that
  alter shared behavior (recipe flags, shebangs, prefix ownership,
  component claims) must be recorded, not silent.
- Small typed Python, stdlib where practical; one dependency-order model,
  one cache, one target description. No new platforms, versions, or
  dependencies without an explicit scope decision.
- Do not run formatters/linters/pre-commit hooks; do not push unless told.
