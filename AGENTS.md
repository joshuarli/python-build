# python-build

Independent build system for the locked CPython 3.15.1 source and its native
dependencies. It produces relocatable, fully OpenSSL-free installations for
macOS arm64 and Linux x86-64/arm64. Windows, Intel macOS, other Linux
architectures, and every other target are unsupported. No glibc enters any
artifact: Linux binaries use the musl loader and statically linked musl in
the Rust extensions, with libgcc as the only other platform library.

Follow `plan.md`. Work runs on the macOS arm64 host; Linux builds,
qualification, and CI release evidence wait for its deferred L wave after
feature work. `rust-for-cpython.md` is the sole detailed Rust campaign
ledger. A debt entry is not success.

`rust-cpython/` is a separate CPython 3.16 Rust-for-CPython research lane. Its
source pin does not affect this product or its production targets, and it no
longer waits for production closeout. Linux arm64 is not implemented in that
experimental lane and must not be described as qualified.

Delegated work on that lane uses the global `orchestrate` skill under the
charter and engineering contract in `rust-for-cpython.md`; this repository
pins no models. `rust-cpython/ROUTES.md` holds each route's suite contract,
and `rust-cpython/README.md` documents the build and `perf.py` harness. The
root schedules shared host work through the `perf.py` host lease.
For this isolated lane, Rust crates may be added for experiments without
per-crate approval when version and checksum are pinned in the committed
overlay `Cargo.lock`, license is recorded in the route's
`THIRD_PARTY_LICENSES.md`, and no production dependency or platform is added.
Other new dependencies require consultation. Performance acceptance follows
the verdict policy in `rust-for-cpython.md`: application budgets decide,
module rows diagnose, and no Rust, allocator, or CPython contract is bent to
move a metric.

## Product targets

Three production targets: `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`,
and `aarch64-unknown-linux-musl`. Target triples, CPU baselines, the shipped and
deliberately absent components, the OpenSSL-free TLS backend, and TLS trust
behavior are in [docs/product-targets.md](docs/product-targets.md). Preserve
the platform CPU baselines and the declared dependency closure.

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

Qualification checks the final extracted archive, and packaging publishes one
immutable generation atomically. Failed work must not replace an accepted
artifact or leave a partial release. The process runner, aggregate verdict,
ELF and Mach-O hardening checks, packaging steps, comparison, and
reproduction are in
[docs/qualification-and-packaging.md](docs/qualification-and-packaging.md).

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

