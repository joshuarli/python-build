# python-build

Independent build system for the locked CPython 3.15.1 source and its native
dependencies. It produces relocatable, fully OpenSSL-free installations for
macOS arm64 and Linux x86-64/arm64. Windows, Intel macOS, other Linux
architectures, and every other target are unsupported. No glibc enters any
artifact: Linux binaries use the musl loader and statically linked musl in
the Rust extensions, with libgcc as the only other platform library.

Follow `plan.md`: finish production P1-P6 and requalify that release before
starting new Rust performance lanes. `rust-for-cpython.md` is the sole
detailed Rust campaign and performance ledger. A debt entry is not success.

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
Coverage is complete; performance work follows `rust-for-cpython.md`
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

