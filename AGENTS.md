# python-build

Independent build system for the locked CPython 3.15.1 source and its native
dependencies. It produces relocatable, fully OpenSSL-free installations for
macOS arm64 and Linux x86-64/arm64. Windows, Intel macOS, other Linux
architectures, and every other target are unsupported. No glibc enters any
artifact: Linux binaries use the musl loader and statically linked musl in
the Rust extensions, with libgcc as the only other platform library.

`rust-cpython/` is a separate CPython 3.16 Rust-for-CPython coverage lane. Its
source pin does not affect this product or its production targets. Linux arm64
is not implemented in that experimental lane and must not be described as
qualified.

For delegated work on that lane, use
`.agents/skills/rust-cpython-coordinator/SKILL.md` in place of the general
`orchestrate` skill. The root agent coordinates isolated worktrees and
integration; no more than 16 coverage subagents run concurrently. The active
loop uses debug builds and complete Python-level module suites; integrated
work also runs all default-resource CPython test modules.
Coverage is complete; performance work follows `rust-for-cpython-perf.md`
through `.claude/skills/rust-cpython-perf/SKILL.md` and `rust-perf-climber`
agents. Claude sessions use Sonnet 5.5 (`claude-sonnet-5-5`) at `high` effort,
or `xhigh` for lanes named by that skill. Codex sessions use the separate
`.agents/skills/rust-cpython-perf/SKILL.md` coordinator and
`.agents/skills/rust-cpython-perf-climber/SKILL.md` lane skill, with only
`gpt-6-luna` at `xhigh` effort for the coordinator and every subagent. The
Claude model policy remains intact.
For this isolated coverage and performance lane, Rust crates may be added for
experiments without per-crate approval when version and checksum are pinned
in the committed overlay `Cargo.lock`, license is recorded in the route's
`THIRD_PARTY_LICENSES.md`, and no production dependency or platform is added.
Other new dependencies require consultation. Performance work runs
memory-first: no CPU-targeted lane starts until every module's load footprint
and working peak are MET or BEYOND and all eligible workload absolute RSS
goals pass. Debt entries remain unresolved goals. The root schedules shared
host work through the performance host lease. Memory qualification has no
CPU, timing, or quiet-host prerequisite; memory samples, floors, output
checks, replication, Rust coverage, and complete correctness checks still
bind.

## Product targets

`buildsys/product.py` derives product paths, ABI, archive names, and metadata
from the CPython source-lock entry. `buildsys/targets.py` owns production
target descriptions and target branching.

| Triple | Platform/compiler | Baseline and deployment |
| --- | --- | --- |
| `aarch64-apple-darwin` | Apple Silicon macOS 27 host; official LLVM 23.1.4 and Xcode 27 SDK | `-mcpu=apple-m1`; artifact minimum macOS 26.0 |
| `x86_64-unknown-linux-musl` | Alpine native-musl LLVM 23.1.3-r0 | `-march=broadwell` (AES, PCLMULQDQ, AVX/AVX2, BMI1/BMI2, FMA, MOVBE); loader `/lib/ld-musl-x86_64.so.1` |
| `aarch64-unknown-linux-musl` | Alpine native-musl LLVM 23.1.3-r0 | `-march=armv8-a+crypto` (AES, PMULL, SHA2, ASIMD); loader `/lib/ld-musl-aarch64.so.1` |

The macOS host floor and deployment minimum are separate constraints. Do not
claim macOS 26 runtime qualification from a macOS 27 run. Linux qualification
uses the locked Alpine image and complete APK closure in `bootstrap.lock.json`;
package acquisition is verified before the network-disabled build.

The product keeps the GIL, shared libpython, the bundled mimalloc allocator
(compiled in statically via explicit `--with-mimalloc`), private native
dependencies,
ThinLTO, macOS PGO, `-O3`, and useful headers, sysconfig, pkg-config metadata,
and `python3.15-config`. Linux PGO is disabled. JIT, BOLT, free-threaded ABI,
and the tail-call interpreter are disabled. Preserve the platform CPU
baselines and the declared dependency closure.

The product is fully OpenSSL-free: no OpenSSL source enters any dependency
graph, compiled `_ssl` and `_hashlib` are disabled in `Modules/Setup.local`,
and TLS plus hashing run on the RTLS/rustls-graviola backend built with the
pinned nightly Rust toolchain. Rust extensions use the musl dynamic CRT
(`-crt-static` is mandatory: rustc cannot emit cdylib/proc-macro artifacts
with a static CRT); no glibc symbols may appear in any payload. Do not claim a
build-time gain without a clean before-and-after measurement.

`backend/` keeps the RTLS provider patch, the hashing backend,
and the replay procedures behind the official build. Keep its Rust
dependencies out of the production locks and bootstrap. Keep its source pin,
per-architecture bootstrap lockfiles, and license record together when
refreshing the prototype.

Ships: CPython 3.15.1, shared libpython, useful standard library, extension
build metadata, and private static native dependencies.

Deliberately absent: pip, ensurepip and its wheel, venv, Tcl/Tk/X11,
`_tkinter`, tkinter, idlelib, turtle, turtldemo, `__phello__` fixtures,
`_gdbm`, release-tree regression tests, native test C-API extensions,
sampling-profiler static web assets (vendored D3/flamegraph/heatmap
JavaScript, CSS, and images; the profiling collection code ships),
and generated bytecode caches. SQLite keeps FTS3/4/5, enhanced FTS3 query
syntax, geopoly, rtree, dbstat, and loadable extensions. Applications must
explicitly enable SQLite extension loading. `compression.zstd` uses a
multithread-capable static zstd library.

Default TLS trust tries the platform-configured sources first. The locked
Mozilla bundle is installed from `certifi-ca` at package time and is used only
when no explicit override or available default source exists. Set
`PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE=1` to disable fallback. Trust data does not
provide online revocation checking; refresh its lock entry for each release
and relevant trust changes.

## Commands

```text
python3 build.py doctor
python3 build.py fetch --target <triple>
python3 build.py build --target <triple> [--pgo-jobs N]
python3 build.py qualify --target <triple> [--pgo-jobs N]
python3 build.py controller-test
python3 build.py compare-reference --target <triple>
python3 build.py reproduce --target aarch64-apple-darwin [--pgo-jobs N]
python3 build/uvmirror.py --tag <tag> --repo <owner/repo>
```

`build` is the development build. `qualify` uses sandbox-exec on the native
macOS host and the locked, network-disabled BuildKit path for Linux. Linux
targets build and run in native-architecture containers; do not treat
emulated timing as performance evidence. `package` validates and publishes
the completed staged build. Reference comparison and reproduction are
separate optional operations and cannot change an accepted package.

## Inputs and build records

`sources.lock.json` pins build, trust, and comparison inputs with URL,
version, SHA-256, size, role, license, and purpose. Reference-only entries
are never build inputs. `bootstrap.lock.json` pins the macOS compiler archive
and attestation, host requirements, Linux image, and complete APK closure.
`buildsys/inputs.py` verifies cached bytes and safe extraction; invalid
objects are replaced only after the downloaded bytes pass verification.

The common build record binds source and patch identities, target and CPU
baseline, dependency inputs, compiler policy and effective flags, bootstrap
identity, commands, build mode, and isolation evidence. Locked identity and
observed host paths are separate. Sealed builds must identify the enforced
network boundary; macOS sandbox containment is weaker than a container and
must be reported as such.

Recipes compose baseline, optimization, PIC, hardening, frame-pointer, and
ThinLTO policy in one place. Use the selected toolchain's actual tools and
run the LTO compile/archive/link/run fixture before expensive builds. Do not
silently drop a required compiler flag or accept stale staged output for a
different source, patch set, target, or recipe.

## Qualification and packaging

One controlled product-process runner supplies a scrubbed environment,
working directory, import policy, and timeout for product checks. Regression
qualification uses process status and complete CPython test accounting;
crashes, timeouts, interruption, missing results, zero executed tests, and
incomplete runs fail. Retries are bounded diagnostics and cannot erase the
initial failure.

The mandatory aggregate verdict checks the final extracted archive. It
includes exact interpreter and ABI identity, module inventory and exclusions,
required native accelerators, binary architecture and dependency closure,
relocation, extension and ABI3 loading, shared-library embedding, TLS,
SQLite, compression, dbm, multiprocessing, ctypes, launchers, and removal of
builder paths. Linux ELF validation requires ET_DYN interpreters, a read-only
`PT_GNU_RELRO` segment with eager binding, non-executable stacks, no writable
executable load segments, and no text relocations. It also verifies stack
protector and fortify evidence. macOS executable Mach-O images must carry
`MH_PIE`. Broad regression tests run on disposable pre-prune copies for all
three targets.

Packaging applies installed-tree fixes, runs regressions on a disposable copy,
strips and prunes the release tree, validates it, creates a deterministic
archive, extracts it under a path containing spaces, and validates those
exact bytes before transactional publication. `artifact.json` is the
canonical artifact and qualification record; `SHA256SUMS` covers published
release assets. Failed work must not replace an accepted artifact or leave a
partial release.

Comparison reads completed artifacts and writes its own results. It requires
successful, complete probes for a match. Benchmarks use the shared harness
only when explicitly requested. Reproduction is opt-in and compares two
independent clean builds, including payload entry types, modes, symlink
targets, content, archives, PGO identity, and normalized Mach-O identity.

## CI and releases

CI is manually dispatched. macOS build and smoke use `xcode-27`; Linux
qualification uses native `ubuntu-24.04` amd64 and `ubuntu-24.04-arm` runners.
Fast controller tests run before builds. Assembly validates the exact three
target set, product version, built revision, LLVM policy, qualification
verdicts, and archive digests before producing uv metadata. Smoke installs
the assembled archive bytes through a local mirror into fresh uv directories.
Release tags must resolve to the revision recorded in every artifact.

Do not add platforms, production dependencies, product versions, or change
public package/API contracts without an explicit scope decision. Do not run
formatters, linters, pre-commit hooks, or CI-only changes for unrelated work.
Do not push unless asked. Commits use Conventional Commit format.

## Optional Nix builder experiment

`flake.nix`, `nix/bootstrap.nix`, and `nix/build_image.py` form an opt-in
alternative bootstrap for the **same** locked Alpine and native-musl Rust
Docker builder, not a NixOS/glibc replacement. Keep its inputs anchored to
the existing locks and the original Dockerfiles. Do not silently substitute
Nixpkgs LLVM, Rust, or libc, introduce Nix store paths into payloads, change
production defaults, or claim release reproducibility from image provenance
alone. See `nix/README.md` for qualification and cold-fetch limitations.
