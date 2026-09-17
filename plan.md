Implement a small, independent build system that compiles **CPython 3.14.6** and its in-scope native dependencies from source inside the project's **Dockerfile-defined Alpine Linux x86_64 environment**, producing a relocatable, dynamically musl-linked Python installation. Deliver a locally built installation archive, its checksums and input manifests, and evidence that it works outside the build environment.

The implementation must emphasize useful compatibility with Astral's **python-build-standalone (PBS)** distributions while keeping its own build architecture simple. PBS is a technical reference and comparison target, not the implementation base. Its recipes, workarounds, source pins, and artifact fingerprints are documented in the appendices.

Read the repository's instructions, inspect existing code, preserve unrelated work, and implement the project through the completed local x86_64 milestone. Do not stop at scaffolding or a design document. Record concrete environmental limitations without claiming that unexecuted work passed.

## Current scope decision (2026-09-17)

All acquisition, compilation, controller tests, runtime validation, and packaging run in stages or containers defined by `Dockerfile`, not directly on the host. Host operations are limited to editing project files, invoking Docker, and managing local inputs/outputs. Docker is now the required execution backend; earlier no-Docker/native-host requirements are superseded.

Tcl, Tk, `_tkinter`, `tkinter`, and their solely GUI-related X11 dependency closure are excluded from the product and build inputs. Do not acquire or build Tcl/Tk, X11 libraries/protocol tools, or Xvfb. Their absence is an intentional scope difference from PBS, not an unresolved M1 gap. Preserve unrelated core capabilities and report the GUI exclusion prominently. Appendix references to Tcl/Tk/X11 describe the reference distribution only, not required project inputs.

## 1. Scope

### 1.1 Immediate milestone: M1

| Property | Required value |
| --- | --- |
| Build userspace | Dockerfile-defined Alpine Linux on native x86_64/amd64; host distro is not a build input |
| Target | `x86_64-unknown-linux-musl` |
| Interpreter | Exactly CPython 3.14.6, ordinary GIL-enabled release ABI |
| Optimization | LTO enabled; no PGO, BOLT, experimental JIT, or tail-call interpreter |
| Execution | Dockerfile-defined development and offline qualification stages/containers on the same architecture; no direct host builds/tests |
| Distribution | One relocatable installation tree, packaged as a local archive |
| Build architecture | Project-owned recipes and typed Python orchestration; standard native component build systems |
| Completion boundary | Local build, runtime validation, reference comparison, clean rebuild, and packaging |

A build that omits major standard-library capabilities, requires the builder's private libraries, or breaks pip, virtual environments, native extensions, or relocation is not a successful streamlined distribution.

### 1.2 Planned platforms

The eventual target set also includes `aarch64-unknown-linux-musl` built natively on aarch64 Alpine and `aarch64-apple-darwin` built natively on Apple Silicon macOS. Use common dependency recipes, source acquisition, packaging, and validation where they genuinely apply. Do not implement unused platform frameworks or delay M1 for either platform.

LTO is required and PGO/BOLT are excluded on every planned platform, including macOS. Future tail-call-interpreter or JIT choices must be explicit platform decisions rather than consequences of a profiling flag. Future-platform source findings and reference artifacts are included as research, not mandatory M1 downloads or builds.

### 1.3 Exclusions

No other Python versions, free-threaded or debug distributions, fully static-musl interpreter, x86-64-v2/v3/v4 variants, glibc target, Windows, Intel macOS, universal2, iOS, or embedded target is in scope. A declared bootstrap Python may have a different version because it is a build tool, not a distributed product.

A Docker daemon/BuildKit execution backend is required for M1. No emulator, cross-compiler, ARM host, or macOS host is needed. Do not bootstrap LLVM or an operating system from source. Do not build a generalized package manager, recipe language, scheduler, or container runtime.

All deliverables are local files. Do not add workflow configuration, hosted-runner integration, upload commands, remote release APIs, publication credentials, or automatic tag creation. Network access is limited to explicit input acquisition and research; build, validation, and packaging must have an offline path.

### 1.4 Independence and libc boundary

Do not fork, vendor, submodule, wrap, import, or execute PBS's build engine. Do not depend on its Python modules, generated module configuration, Rust packaging program, or multiversion dependency graph. Do not repack a PBS binary or copy its interpreter, standard library, headers, libraries, object files, or installed pip into this product.

Selective adaptation of an individual source patch is permitted when it fixes a demonstrated problem and has provenance, attribution, a narrow applicability check, and a regression test. Independence does not mean ignoring useful upstream fixes, and it does not erase their licenses.

The native build tools, build userspace, target binaries, and runtime-validation root must use musl, not glibc. Do not install `gcompat`, `libc6-compat`, a foreign glibc, or a GNU-hosted compiler binary requiring glibc. GCC, GNU make, GNU binutils, libgcc, and a musl-built libstdc++ are not glibc merely because they are GNU projects. Inspect actual runtime linkage.

## 2. Product and parity contract

### 2.1 Exact source and comparison baseline

The sole CPython target source is:

```text
version: 3.14.6
url: https://www.python.org/ftp/python/3.14.6/Python-3.14.6.tar.xz
size: 23921184
sha256: 143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63
```

Verify the downloaded bytes before extracting them. The source pin is documented in the PBS download manifest and CPython source references. [R2, R16]

Compare the product against **PBS release `20260610`**, build commit **`f1d7b92301235781d4de2493578773aaa413c0a5`**, specifically its ordinary-GIL x86_64 dynamic-musl **LTO** distribution. This is a fixed comparison baseline, not a moving latest release and not python.org's installer. Reference artifact fingerprints are in Appendix B. Use a clean verified extraction, not an installation modified by another environment manager. [R1, R2]

The goal is **close functional, ABI, portability, module-coverage, and practical-performance parity**. Matching an upstream archive hash is not required. Reference hashes authenticate comparison inputs; they are not expected output hashes.

### 2.2 Required behavior

The finished installation must provide the exact interpreter version and architecture, normal extension loading, correct ABI and packaging tags, a useful standard-library inventory, private non-platform native dependencies, relocation, pip, virtual environments, TLS verification, compression, databases, FFI, and usable extension-development metadata. Shared libpython and a tested embedding contract are required; the interpreter's own static-versus-shared libpython linkage is a documented implementation choice.

Declare the supported CPU baseline, tested musl runtime envelope, external platform/data prerequisites, dependency versions, and relevant configuration differences. Do not claim older-musl, glibc-wheel, operating-system, or performance compatibility without evidence.

### 2.3 Permitted differences and reporting

Use a musl-native Alpine compiler and libc/sysroot. A newer tested musl floor than the reference, ordinary shared-libpython linkage, configure-driven shared extension modules rather than the reference's built-in/shared split, justified dependency updates, and a different deterministic archive layout are acceptable when their effects are recorded. These permissions do not excuse missing core capabilities or undeclared runtime dependencies.

Produce both a machine-readable and a readable parity report. Each comparison row must be `match`, `intentional_difference`, `gap`, or `untested`, with evidence and consequences. Treat critical missing behavior as a gap, not as an intentional difference justified solely by convenience. Do not hide missing capabilities behind an aggregate percentage.

Prioritize correctness and ABI, then standalone functionality and module coverage, then compatibility envelope, then measured performance/size, and finally cosmetic layout similarity. Upstream timestamps, object-file archives, compressor bytes, compiler branding, and exact built-in/shared placement are not acceptance requirements.

Compare two clean builds of this project's own output, investigate inexpensive reproducibility improvements, and report remaining differences. Neither upstream byte equality nor perfect internal byte equality is an M1 gate. Input integrity, offline execution, tested functionality, and truthful reports are gates.

## 3. Implementation architecture

Use a small typed Python controller with standard-library dependencies wherever practical. A directly executable `python3 build.py ...` front door is sufficient; do not require uv, a downloaded managed interpreter, Cargo, a framework, a plugin system, or a custom package manager to launch it. Use TOML or JSON for checked-in locks/configuration and JSON for machine-readable reports. A tiny conventional `pyproject.toml` is fine, but the controller must run without a network-backed installation step.

Suggested structure, adapting to repository conventions rather than creating empty scaffolding:

```text
build.py                  # CLI only
buildsys/                 # small controller, dependency recipes, packaging, checks
sources.lock.json         # target/library source inputs and hashes
bootstrap.lock.json       # Alpine rootfs/APK/tool inputs and hashes
patches/                  # small selected patch set, provenance, regression links
tests/                    # controller tests and distribution/runtime tests
docs/research.md           # source findings and verified implementation discoveries
docs/parity.md             # current evidence and intentional differences
```

One dependency ordering model, one source acquisition implementation, one command runner, one target description, one package layout. Straightforward Python functions and a small dependency list are preferable to a generalized scheduler or a YAML recipe language. Retain native build systems for CPython and its libraries: invoke configure/make or the component's supported equivalent instead of translating their internals.

M1 should have one Dockerfile-defined Alpine executor with separate acquisition, offline build, and minimal-runtime stages. Unsupported future targets should fail with a clear “not implemented” message, not create empty artifacts, silently build amd64 under an ARM label, or dispatch into PBS. Do not create a hierarchy of unused abstract platform backends.

Suggested commands; preserve these semantics even if names change:

```text
python3 build.py doctor
python3 build.py fetch --target x86_64-unknown-linux-musl
python3 build.py build --target x86_64-unknown-linux-musl --dev
python3 build.py build --target x86_64-unknown-linux-musl --offline --sealed
python3 build.py test --target x86_64-unknown-linux-musl
python3 build.py compare-reference --target x86_64-unknown-linux-musl
python3 build.py package --target x86_64-unknown-linux-musl
python3 build.py reproduce --target x86_64-unknown-linux-musl
```

Add offline input export/import only as simple archive operations over the existing lock/cache; do not build a repository service. Keep packaging separate from compilation so a validated installation can be packaged without rebuilding it. `doctor` must show actual host/target, musl, compiler/linker, bootstrap Python, missing tools, and whether sealed execution is available. It must not silently install system packages or change host configuration.

Keep a content-derived identity for each dependency build using its source, patches, configuration, toolchain, and relevant dependency identities. Reuse completed local work only when those identities match. A clean-rebuild command must bypass compiled-output caches while allowing immutable downloaded inputs to be shared. Avoid a cache framework larger than the build logic it serves.

## 4. Inputs, provenance, and dependencies

Separate these roles explicitly: acquisition tooling; bootstrap/rootfs/toolchain; target sources and patches; generated intermediates; test-only inputs; reference-only artifacts; final payload. Record source URL, exact version or commit, SHA-256, size when known, purpose, license/source provenance, and target applicability.

The acquisition phase may use the network. Verify digests before extraction; protect against path traversal, escaping symlinks/hardlinks, absolute paths, devices, and other unsafe archive entries. Never execute unverified downloaded helpers. Persist artifacts in a content-addressed cache with atomic publication. A filename alone is not an identity. Tests should cover tampering, missing inputs, malformed locks, interrupted writes, and unsafe archives.

Source-build CPython and the non-platform libraries the distribution bundles. Alpine APK packages may bootstrap tools and the declared native libc/sysroot; do not create the deliverable by extracting Alpine's system Python package, copying PBS files, or copying undeclared runtime libraries out of `/usr/lib`. A temporary development-only dynamic link to a system dependency is acceptable for diagnosis but cannot pass standalone artifact validation.

Pin the exact Alpine branch, architecture, bootstrap rootfs or package set, APK indexes/keys, individual APK bytes, and transitive tool dependencies needed for a sealed build. A branch URL and package names are not a lock. Reconstruct the rootfs from cached verified inputs without `apk update` or remote resolution during compilation. Do not use `--allow-untrusted` as a substitute for package/input verification. Never mix edge and stable opportunistically to make a dependency appear.

Use verified origin sources where available. PBS's download file uses Astral mirrors for availability in several places; the original source URLs are often in its comments. This project must not require live Astral hosting once its inputs are acquired. Prefer publisher origin URLs or project-controlled mirrors. The CPython `cpython-source-deps` exports for zstd are source, not a forbidden PBS binary, but an alternate export's digest must match its own bytes rather than the hash of a different tarball.

Acquire only the sources, tools, test fixtures, and reference artifacts needed for the selected M1 steps; do not fetch or build components for other Python versions or future targets. Do not lock Cargo/Python third-party packaging dependencies solely because PBS used them. Compiler/Alpine/Apple SDK bootstraps are declared trust roots; recursively rebuilding all of them from source is explicitly outside M1.

## 5. Native x86_64 build pipeline

### 5.1 Toolchain and bootstrap

Start with a native Alpine Clang/LLVM/LLD toolchain near the reference LLVM generation when available on a supported locked branch. Verify the actual executable paths, resource directory, target triple, compiler runtime, libc/CRT selection, assembler, archive tools, and linker. Use an explicit LTO smoke test before launching the dependency build. Native GCC with LTO is a fallback to evaluate only if Clang imposes disproportionate complexity; such a change must be reported, not silent.

Set a baseline x86_64 ISA and record it. Keep frame pointers and a non-executable stack where supported. Use `-O3` or the explicitly documented selected optimization level for the distribution; **do not enable PGO**. Prefer Clang ThinLTO as the first explicit LTO mode if supported, then verify the effective generated flags and compare with the reference's effective mode. Avoid universal flags that contaminate third-party extension builds.

Use the stock native CPython build pipeline. Avoid forced cross mode, custom host-freezing infrastructure, or compiling against the reference's handcrafted musl unless a later compatibility requirement actually justifies it.

### 5.2 Native dependency prefix

Build dependencies into a private staged prefix, separate from the final installation. Use PIC static libraries where this keeps linkage simple. Set pkg-config search roots so dependency detection cannot find unrelated host development packages. Use supported per-library configure variables and inspect `config.log`, generated module state, and link commands. Do not guess the variable names; derive them from the exact 3.14.6 configure script.

Use CPython's normal shared extension modules as the default. Supply complete transitive static-link flags in the correct order. Check symbol visibility and dependency duplication; statically linking the same native library into multiple modules can have symbol-interposition/state implications. A small, properly relocated private DSO is preferable to brittle tricks added only to remove one dynamic library.

Get OpenSSL, SQLite, Expat, zlib, bzip2, liblzma, zstd, libffi, and mpdecimal working first; then libedit/ncurses and uuid/dbm. Tcl/Tk and its X11 closure are excluded. This ordering is an iteration strategy, **not permission to call the reduced first pass complete**. Do not silently replace libedit with readline, BDB with gdbm, Tcl/Tk 9 with an older incompatible version, or zstd support with an import skip.

Investigate native-build differences for libffi 3.3 and old BDB/X11 inputs rather than preserving them at unlimited cost. An updated source pin is acceptable after a concrete reason, behavioral/ABI tests, license review of the shipped notices, and a recorded reference difference. Avoid an independent outdated-dependency preservation project.

### 5.3 CPython configuration

Read `./configure --help` from the verified source. The intended policy is ordinary release/GIL-enabled CPython, LTO enabled, PGO/JIT/BOLT/tail-call disabled on M1, mimalloc supported, PIC and dynamic extension loading, explicit private native dependencies, and a staged non-system installation.

Use a neutral configured prefix and DESTDIR/staging consciously; test final relocation rather than compiling in the checkout path and hoping. Start with standard shared libpython if needed to obtain a trustworthy baseline. Evaluate the narrow static-interpreter backport as described in Appendix A.7. Keep `checksharedmods` and ordinary configure-module checks enabled. Missing expected modules are failures, not warnings to bury in logs.

Do not set `--with-build-python` or add cross-compilation cache overrides without a demonstrated native-build need. Use `CFLAGS_NODIST` / `LDFLAGS_NODIST` for private compiler/optimization flags where appropriate, while retaining flags needed by consumer extensions. Explicitly test the musl thread-stack policy.

### 5.4 Patch discipline

Every patch needs: exact upstream source/version; origin URL and license/attribution when adapted; explanation; scope; an applicability check; and a reproducer or regression test. Apply against a freshly verified source tree and fail on rejects or unexpected preimages. Record whether the fix is already upstreamed in a later CPython version.

Initial candidate categories, not a mandatory patch bundle:

| Candidate | Default disposition |
| --- | --- |
| Static-libpython-for-interpreter backport | Evaluate as one isolated parity improvement |
| Relative build-details / demonstrated getpath/symlink gap | Adopt only when the stock relocated build fails the corresponding test |
| Tcl/Tk relative resource lookup | Likely useful; verify actual staged resource paths |
| Musl ctypes discovery / callback behavior | Audit PBS and Alpine fixes; implement/test the needed semantics |
| Thread-stack policy | Evaluate Alpine's narrow compile/link settings on 3.14.6 |
| HACL generic-ISA issue | Inspect and test before selectively patching |
| Forced host Python / cross-configure / musl wrapper headers | Not needed for native M1 unless a real failure proves otherwise |
| Disable stdlib-module configure/checksharedmods | Do not import |
| PGO/BOLT/JIT build patches | Do not import for M1 |
| Older CPython version, other architecture, glibc compatibility patches | Do not import |
| PBS tar/Rust packaging tooling | Do not import; implement a small project-owned packaging step |

Do not call the project “clean room” while copying patches. Independence of build architecture does not erase source-code licenses or provenance obligations.

## 6. Standalone runtime and relocation

Use one normal install tree, preferably a top-level `python/` containing `bin/`, `lib/`, `include/`, and the resource/share directories actually needed. The interpreter is `bin/python3.14`, with conventional local aliases such as `python3` and `python` if included. Never replace the host's system Python or modify its `/usr`, `/lib`, or interactive shell configuration.

The Linux executable should have the normal musl loader identity for x86_64. RPATH/RUNPATH applies to shared-library discovery, **not to locating the ELF `PT_INTERP` loader**. The loader is an explicit platform prerequisite. Do not claim the tarball runs on a glibc-only machine with no musl loader, and do not add a wrapper that silently downloads or installs one. If a future design bundles its own loader, treat that as a separate compatibility decision rather than a hidden part of M1.

No unbundled OpenSSL, SQLite, Tcl/Tk, libffi, compression library, or other private runtime dependency may leak from the builder. Define a narrow external platform allowlist and validate it recursively across all ELF files. If a compiler-runtime DSO is genuinely required, either bundle it compatibly with notices or explicitly justify it as a supported platform dependency. Prefer not to make the final interpreter depend on a C++ runtime merely because the compiler itself used one.

For relocation, test the extracted tree under multiple prefixes, including paths containing spaces, and after removing access to the original installation/build paths. Test direct execution, executable symlinks, interpreter aliases, sys.prefix/base_prefix, sysconfig, python-config/pkg-config where shipped, pip, and newly created venvs. Standard existing venvs are not promised to be arbitrarily movable: distinguish creating a venv from a relocated base interpreter from relocating an already-created venv.

Consumer compiler settings must not refer to the private dependency prefix, temporary rootfs, original checkout, or absolute compiler path that only existed inside the builder. Remove private instrumentation/LTO flags from extension defaults when inappropriate, without breaking ABI settings. Prefer structured edits and explicit generated fields to global textual surgery.

Install pip offline from a pinned wheel or use a deliberately chosen, tested ensurepip policy. Ensure `python -m pip` works. Any shipped pip launcher must select this installation's interpreter after relocation, not whatever `python3` happens to be first in PATH. Test venv's ensurepip behavior independently from the base pip version; a base pip update does not automatically change CPython's bundled ensurepip wheel.

Do not preinstall setuptools into the base Python 3.14 distribution just for build tests. A separate locked wheelhouse may contain test/build backends. Do not apply Alpine's system `EXTERNALLY-MANAGED` policy to this standalone installation.

Define certificate and timezone behavior explicitly. OS trust roots, timezone data, `/etc/resolv.conf`, `/etc/hosts`, `/etc/passwd`, and terminal/display services are runtime inputs, not magical things a tarball makes disappear. Use documented system data and/or deliberately bundled data as appropriate. Test TLS verification with local fixtures, both success and failure; never disable verification to hide trust-store problems. Test OpenSSL provider/configuration lookup and ncurses terminfo after relocation. Tcl/Tk and display-service validation are excluded.

Declare the measured musl compatibility floor and CPU baseline in the manifest and local compatibility report. Run on the clean selected Alpine runtime and additional reasonably chosen musl runtimes. Do not overclaim old-musl compatibility based on absence of glibc symbols, nor infer a minimum Linux kernel without evidence.

## 7. Native execution and hermetic qualification

A qualified artifact must come from an offline build with declared filesystem and tool inputs. Native development convenience and enforced isolation are separate execution modes over the same build recipes.

Provide a convenient Docker development stage with an explicit non-hermetic label for rapid iteration. For artifact qualification, run the same recipes in Dockerfile-defined, locked Alpine stages/containers with isolated filesystem and network access. Compile and test as the unprivileged builder, never with a Docker socket or host toolchain mounted inside. Use BuildKit `RUN --network=none` or `docker run --network none` for offline execution. Do not implement an additional native-host, bubblewrap, or chroot backend.

A sealed run should expose only the declared rootfs/toolchain, verified input cache, project recipe/patch snapshot, and writable work/output directories. Avoid broad binds of host `/usr`, home, repository-parent paths, sockets, or credentials. Close inherited file descriptors and do not leak a host container socket or network socket through the boundary. Use a controlled HOME, environment allowlist, locale/timezone, umask, stable working paths, and bounded explicit parallelism. Scrub `PYTHONPATH`, `PYTHONHOME`, compiler include/library overrides, user site-packages, pip config, and other undeclared influences.

Separate online acquisition from offline build and packaging. Block external networking at the process namespace boundary; a `--offline` boolean that merely avoids the downloader is insufficient. Tests may use loopback within the isolated namespace for local TLS/socket fixtures without allowing external network access. Keep this distinction explicit.

Record the kernel, CPU features, tool versions, job count, and rootfs identity as environmental inputs/observations. A rootfs shares the host kernel and is not a VM; do not claim stronger kernel independence than demonstrated. Build-source timestamps, optimization, locale, generated data, and compression must be controlled where feasible. Do not reuse wall-clock build time inside deterministic payload files when a declared source epoch suffices.

Prove isolation with negative tests: corrupt an input; remove a required cached package; introduce a hostile HOME or fake host header/library; attempt an external network connection; make an undeclared host path inaccessible; and verify clear failure or lack of influence. Do not infer isolation from one successful build that happened not to touch the network.

When Docker or its required isolation features are unavailable, `doctor` should report the exact constraint. Do not fall back to host execution. A development container is not evidence of hermetic qualification. Do not use PBS or install glibc as a fallback.

## 8. Validation and reference comparison

Write tests for the controller and, more importantly, for the actual extracted distribution. Test the packaged/stripped installation as well as the unstripped build. Disable bytecode writes or use disposable copies during immutable artifact comparison.

### 8.1 Binary/ABI checks

Inspect every shipped ELF: executable, libpython, extension module, and private DSO. Check ELF class/machine, musl PT_INTERP where applicable, DT_NEEDED, RPATH/RUNPATH, exported symbols, unresolved dependencies, and relevant version requirements. Use actual ELF tools and controlled runtime loading, not only string searches. Reject glibc loaders, libc.so.6, GLIBC_* symbol requirements, compatibility shims, unexpected dependency paths, and x86 ISA assumptions above the declared baseline. GNU property/version sections are not automatically glibc; inspect their meaning.

Verify `sys.version_info` is exactly 3.14.6, the GIL/debug/free-threaded settings are correct, SOABI/EXT_SUFFIX and platform tags are consistent, and effective configure/build features match the manifest. Compilation with musl does not by itself prove dynamic-extension compatibility.

Build and import a small external C extension using the relocated interpreter's advertised development configuration. Exercise a limited-API/ABI3 fixture where supported and a simple C embedding executable using the provided shared libpython and python-config/pkg-config contract. Test ctypes calls in both directions, callbacks, `CDLL(None)`, library discovery, a private helper DSO, and library loading without build-only utilities installed.

### 8.2 Runtime/module coverage

Compare reference and project module inventories, distinguishing platform-unavailable, built-in, shared, test-only, and truly missing modules. At minimum exercise:

- `ssl`, `hashlib`, certificate verification, and relevant OpenSSL configuration/providers.
- `sqlite3` including important reference compile options and extension-loading policy; `dbm` backends and persistence; `decimal`; `uuid`; Expat/XML.
- `zlib`, `bz2`, `lzma`, and **`compression.zstd`**, with real round trips rather than imports only.
- `ctypes`, callbacks/closures, threading/thread-stack behavior, concurrent workers, subprocess, and multiprocessing with the start methods the platform supports.
- `readline`/libedit, curses/panel, locale behavior, terminals, `zoneinfo`, filesystem and socket operations.
- Confirm the intentional exclusion of `_tkinter`, `tkinter`, Tcl/Tk resources, and GUI-only X11 libraries from the packaged payload; record the reference difference without acquiring GUI test inputs.
- pip/ensurepip/venv, installation of a locked pure-Python wheel and a locally built native wheel offline, and consumer extension development after relocation.

Run an appropriate broad CPython regression suite from the verified source/build. Investigate failures against stock 3.14.6 and/or the reference in the same runtime. Record narrow exclusions with observed causes. Do not carry over Alpine or PBS skip lists wholesale. Tests that need a network/display/kernel feature must report an actual skip reason, not silently pass.

The runtime-validation rootfs must not contain the compiler or arbitrary development packages that hide missing libraries or make ctypes discovery work accidentally. Maintain a separate test/development root for compiling fixtures, then run those fixtures in the minimal runtime. Reference binaries are executable third-party inputs: verify hashes, run them unprivileged in a dedicated comparison root with no secrets and no external network, and never execute arbitrary scripts merely while unpacking metadata.

### 8.3 Performance and reproducibility

Benchmark the reference x86_64 musl LTO interpreter and this project's build on the same host/runtime conditions. Measure representative startup/import, interpreter execution, JSON/serialization, selected compression/hash/decimal/SQLite workloads, archive size, and installed size. A locked pyperf installation may be test-only if useful; the build controller need not depend on it.

Report methodology, warm/cold distinctions, repetitions, and uncertainty. Investigate material regressions before blaming independence or changing optimizations. Do not enforce an arbitrary universal percentage or select one favorable microbenchmark. Later macOS comparison against PBS's PGO build must prominently disclose the no-PGO policy; it is not an apples-to-apples claim of equivalent optimization.

Build twice in clean work directories, rebuilding native dependencies as well as CPython. Sharing immutable input downloads is fine; sharing prior objects does not demonstrate a clean rebuild. Compare project output hashes and file-level differences, fix straightforward nondeterminism, and keep a report. Upstream byte differences are informational. Any remaining internal nondeterminism must be described honestly rather than normalized away and labeled byte-identical.

## 9. Local artifacts

Produce one useful installable amd64 archive under `dist/`, preferably `.tar.gz`, containing a conventional top-level `python/` tree. A debug/development companion is optional when its size and purpose justify it. A full object-file archive and the reference's nine archive variants are not required. Do not create a full-archive-to-install-only conversion framework or a Rust packaging tool for cosmetic similarity.

Use a project-owned build revision and an unambiguous name, for example `cpython-3.14.6-x86_64-unknown-linux-musl-r1.tar.gz`. Do not claim the archive was issued by Astral or use its release identity as this project's identity. A build revision is local metadata; creating a Git tag or a remote release is not part of this task.

Keep the installed headers and configuration required for ordinary native-extension builds. Supply shared libpython for embedders. Decide whether a static archive and debug information belong in the main archive or an optional companion based on measured size and usefulness. Stripping must preserve required exported symbols and extension-loading behavior; run validation against the actual extracted packaged result.

Use deterministic entry order, ownership, modes, timestamps, and compressor settings. Preserve symlinks and executable permissions without marking every file executable. Select a documented source epoch and bytecode policy. Include required licenses and notices. A structured component manifest should describe what is actually shipped rather than listing every build-root tool.

The local output directory must contain:

```text
dist/
  cpython-3.14.6-x86_64-unknown-linux-musl-r1.tar.gz
  SHA256SUMS
  inputs.json              # exact source, patch, toolchain and bootstrap identities
  components.json          # shipped components and source/license provenance
  provenance.json          # build environment, commands/configuration and run identity
  validation.json          # module, ELF/ABI, runtime and relocation results
  parity.json
  parity.md
  reproducibility.json
  benchmarks.json
```

These filenames are a suggested compact layout; equivalent well-documented local reports are acceptable. Include sufficient information to reconstruct the build and relate every report to the exact archive digest. Volatile run timestamps belong in sidecar provenance, not deterministic payload files. Reports must identify failures and skipped or unexecuted checks rather than omitting them.

Write completed outputs atomically. A packaging command must not silently overwrite a qualified artifact with different bytes under the same build identity. Preserve useful failure logs and partial reports in a separate local diagnostic directory without presenting them as qualified artifacts. No credentials, upload step, or remote service is needed to finish packaging.

## 10. Implementation phases

### M1a — native interpreter and dependency build

Establish the verified CPython source, bootstrap/tool lock, private dependency prefix, and LTO smoke test. Build CPython using its conventional native configure/make path. Obtain a real musl interpreter and baseline tests. Demonstrate that the process invokes no PBS build code and copies no finished interpreter distribution into its output. The locked native Alpine bootstrap interpreter is permitted only as a build tool. Intermediate missing modules remain recorded as unfinished.

### M1b — standalone behavior and useful parity

Complete the in-scope dependency, module, and resource inventory. Implement and test relocation, pip/venv, external native extensions, embedding, callbacks, TLS, databases, compression, and terminal support. Verify that the Tcl/Tk and GUI-only closure exclusion is enforced. Evaluate individual portability fixes against actual failures. Measure the CPU/musl compatibility envelope and compare the installation with the pinned reference. Resolve material gaps before adding platforms.

### M1c — isolated build and local distribution

Reconstruct the locked Alpine build root and demonstrate offline filesystem/network boundaries with negative tests. Build all bundled native libraries and CPython in that environment, package the installation, and validate a fresh extraction in a clean runtime. Perform a clean-rebuild comparison and practical reference benchmarks. Write the archive, checksums, input/component manifests, and reports into `dist/`.

M1 ends with those local artifacts and evidence. Linux aarch64 and macOS aarch64 are roadmap targets, not prerequisites or additional implementation phases in this task.

### Working method

Implement incrementally in the repository rather than returning only a plan. Add tests before relying on lock parsing, cache identity, extraction safety, comparison classification, or qualification logic. Run targeted tests during development and the complete mandatory artifact checks before declaring M1 complete. Preserve the repository's working conventions instead of replacing them solely to match an illustrative directory tree.

Keep dependency work independent when parallel execution helps, and give shared install prefixes and generated artifacts a single clear owner. Record concrete commands, source decisions, patches, runtime findings, deviations, and unresolved issues. Do not silently expand the supported version matrix, recursively bootstrap the compiler/OS, or substitute a prebuilt distribution to bypass a difficult test.

The final implementation report must identify what actually ran, the host/toolchain/rootfs identities, validation outcomes, archive path and SHA-256, supported runtime envelope, material reference differences, and internal reproducibility findings. Distinguish implemented from executed, development-only from isolated, and assumptions from measured results. An environmental constraint is a specific limitation to report, not evidence of success.

## 11. M1 acceptance checklist

M1 is complete when all of the following are established by local evidence:

1. The packaged interpreter is exactly CPython 3.14.6, GIL-enabled, x86_64, dynamically musl-linked, LTO-enabled, and built without PGO, BOLT, JIT, or tail-call execution.
2. The project owns its build recipes and packaging, executed only through the project Dockerfile on amd64. No PBS engine or finished-Python payload, glibc compatibility layer, ARM host, or Mac is required.
3. Bundled non-platform native dependencies come from locked sources. Every runtime library is either in the artifact or explicitly admitted by a narrow tested platform contract; builder-library leakage fails validation.
4. The useful standard-library inventory, pip/venv, extension loading/development, embedding, resources, and relocation tests pass. Material reference differences are explained and justified. Unexplained missing core behavior blocks completion.
5. The CPU baseline, tested musl/runtime envelope, data prerequisites, and wheel-compatibility claims are conservative and supported by actual runs. Minimal-runtime tests cannot borrow build-root dependencies.
6. An isolated offline Docker build has been executed with verified inputs and negative isolation tests. A development-container build is not substituted for that evidence.
7. A two-clean-build comparison and practical reference parity/performance report exist. Remaining byte differences are reported; matching upstream bytes is not required.
8. A usable amd64 archive, checksums, manifests, and validation reports exist locally and correspond to the tested packaged bytes.

## 12. Future-platform design boundary

Keep actual common acquisition, dependency ordering, locking, recipe helpers, package layout, and validation reusable. Linux aarch64 should prefer native execution and change target/toolchain data plus genuinely architecture-specific handling, rather than introducing premature cross compilation.

The macOS aarch64 implementation must run natively on Apple hardware with a declared OS/SDK/tool manifest, a deliberately chosen deployment floor, relative Mach-O loader paths, and any required signatures after binary edits. Its optimization policy is LTO without PGO/BOLT. Tail-call and JIT choices must be recorded independently; JIT defaults to disabled unless a later explicit decision changes that policy. Apple SDK/OS assets are platform prerequisites, not files to redistribute by default.

Document the small target-specific interfaces that M1 actually reveals. Do not create placeholder platform implementations, promise untested compatibility, acquire future-platform inputs, or make future-platform decisions block a working amd64 artifact.

## Appendix A. Build and portability research

PBS observations in this appendix refer to commit `f1d7b92301235781d4de2493578773aaa413c0a5` and release `20260610`. CPython target behavior must be checked against the verified 3.14.6 source. The Alpine comparison recipe has its own commit and version, identified below. Source URLs and reference fingerprints are embedded in the remaining appendices.

These are source-level findings and implementation leads, not evidence that this project has already built Python or passed a benchmark. Source-manifest and release-metadata hashes require verification against downloaded bytes before use. Requirements are defined in Sections 1–12; a mechanism observed in PBS is not automatically a required mechanism here.

### A.1 Build orchestration and trust roots

PBS's top-level `build.py` dispatches Unix work into `cpython-unix/build-main.py`. The Unix Makefile and Python orchestration assemble the toolchain/dependency graph and run per-package shell recipes. `targets.yml` carries platform/compiler/flag/dependency differences. `extension-modules.yml` and generated `Modules/Setup.local` / supplementary Makefile rules control module construction. [R3–R6]

Linux builds use isolated container workspaces; macOS uses a different temporary-directory backend. This is already a shared cross-platform engine, but its generality includes many versions, architectures, and historical compatibility paths that this project does not need. Reuse the knowledge, not the engine.

At the selected pin, compilation LLVM is **22.1.3+20260410**, supplied by `indygreg/toolchain-tools`. The Linux archives are **GNU-hosted**, not musl-hosted. Upstream's musl outputs were built with those tools in Debian/glibc environments. The x86_64 builder starts from a pinned Debian Jessie image; ARM64 selects the Debian Stretch configuration, with historical package snapshots. Those builder choices explain the reference artifacts; they are not requirements for the native Alpine implementation. [R2, R6, R7]

Native Alpine Clang/LLVM packages are the appropriate initial toolchain trust roots. The cited Alpine package records are discovery leads for LLVM/Clang 22, not a locked toolchain. Resolve and verify the actual x86_64 package closure for the selected Alpine branch; do not extrapolate a package revision from another architecture. A matching compiler version string is not a matching compiler build, and exact compiler identity is not a product requirement. Avoid building LLVM from source in M1. [R18]

### A.2 Reference dependency inventory

These are **reference versions**, not an instruction to import PBS's download module or preserve every old tool. Use this information to choose and record this project's source pins. Preserve reference native-library versions initially where practical to reduce variables; a justified update or simpler ABI-equivalent implementation is allowed if recorded. Do not confuse “pinned for comparison” with “currently free of security issues.” Keep Python itself exactly 3.14.6. [R2, R6]

| Component | PBS reference version | Role / important distinction |
| --- | --- | --- |
| CPython | 3.14.6 | Only distributed interpreter version in this project |
| LLVM | 22.1.3+20260410 | PBS compiler bootstrap; Linux GNU-hosted archive is not an input here |
| musl | 1.2.2, modified | Used by reference dynamic-musl builds; this project's initial libc comes from the locked native Alpine userspace |
| musl-static entry | 1.2.5 | Separate PBS variant; not the selected dynamic-musl product |
| libffi | 3.3 for musl; 3.4.6 for macOS | Need real calls/closures/callback tests; matching version alone proves little |
| OpenSSL | 3.5.7 | `_ssl`, `_hashlib`, providers/configuration and certificate policy |
| SQLite | source number 3530100; SQLite 3.53.1 | Compile options and extensions are as important as version |
| Expat | 2.8.1 | XML modules |
| bzip2 | 1.0.8 | `_bz2` |
| xz/liblzma | 5.8.1 | `_lzma` |
| zlib | 1.3.1 | Linux zlib; macOS reference uses system zlib |
| zstd | 1.5.7, from CPython source-deps export | Python 3.14 `compression.zstd` support |
| mpdecimal | 4.0.0 | `_decimal` |
| libedit | 20240808-3.1 | Linux `readline` backend; macOS reference uses system libedit |
| ncurses | 6.5 | Curses/panel and terminal handling |
| Berkeley DB | 6.0.19 | Reference Linux `_dbm` backend; license and file-format implications |
| libuuid | 1.0.3 | PBS uses this standalone libuuid source, not an assumed util-linux version |
| Tcl / Tk | 9.0.3 / 9.0.3 | Include resource/script trees and Linux graphics closure |
| libX11 / libXau / libxcb | 1.6.12 / 1.0.11 / 1.17.0 | Linux Tk/X11 dependency family |
| xorgproto / xcb-proto | 2024.1 / 1.17.0 | Protocol/header/build inputs |
| xtrans / X11 util-macros | 1.6.0 / 1.20.2 | Additional X11 build inputs |
| libpthread-stubs | 0.5 | Determine whether actually needed for this native dependency configuration |
| pip | 26.1.2 | Installed from pinned wheel |
| autoconf / m4 | 2.72 / 1.4.19 | Regeneration tools when patches require regeneration |
| binutils / patchelf | 2.43 / 0.13.1 | PBS build/postprocessing tools, not required version choices here |

The complete dependency graph also contains build executables, scripts, native headers, generators, test-only inputs, and transitive APK packages. The table is not a hermetic lock. Derive the actual closure from the implementation. Do not blindly retain an input that only serves an unused PBS workaround, another Python version, another target, or a packaging step we are not using.

### A.3 Musl-specific behavior

PBS builds musl 1.2.2 and **removes `reallocarray()` from the headers and implementation**. The script explains that this avoids OpenSSL or another dependency acquiring that symbol requirement when deployed on older musl, including 1.2.1. It does not establish a general guarantee that arbitrary builds against modern musl run on older musl. [R8]

On native Alpine, do not modify the machine's libc, replace `/lib/ld-musl-x86_64.so.1`, or mechanically reproduce this source surgery. Initially build against the declared Alpine musl toolchain. Identify the minimum runtime this actually requires. Test a reasonably older musl runtime where feasible, and record differences from PBS. Only introduce an older, isolated target sysroot later if backward compatibility evidence warrants that complexity. A musl 1.2.x minor-version label is not a proof that no newer patch-level symbols were used.

PBS's musl target compiler is `musl-clang`, a wrapper around the GNU-hosted compiler. It removes normal Clang resource-header search paths. PBS consequently copies intrinsic headers, selected x86 headers, and `stdatomic.h` into the musl toolchain include environment. ARM64 adds `--rtlib=compiler-rt` for compiler builtins. [R5, R6]

A native musl-built Clang normally has its own correct resource headers and native CRT discovery. Test include paths, linker inputs, and a small LTO executable first. **Do not copy compiler headers into system directories just because PBS did.** Likewise, don't add ARM64 compiler-runtime flags unconditionally to amd64 or insist on compiler-rt instead of a valid musl-built libgcc without evidence.

PBS enables frame pointers for the selected Linux musl targets and requests a non-executable stack. The CPython recipe uses PIC, removes a dependency-level hidden-visibility flag before compiling CPython itself, and hides symbols from static dependency archives at link time. Preserve the intended properties with measured, appropriate flags; do not blanket-hide CPython's exported API. [R5, R6]

### A.4 CPython configuration and optimization quirks

The reference recipe combines target/build triples, a fixed `/install` prefix, private dependency include/library paths, explicit OpenSSL/system-Expat/system-mpdecimal selection, and disabled install-time ensurepip. It forces libedit on Linux, sets the Linux dbm preference to Berkeley DB, builds shared libpython, and applies a backport to statically link libpython into the interpreter. [R5]

The feature-selection details matter:

- The macOS ARM64 reference uses **PGO + LTO**, enables the tail-call interpreter, and builds the experimental JIT in `yes-off` mode.
- The two selected musl references use **LTO without PGO**. They do **not** enable tail-call execution or the JIT.
- Tail-call activation in the PBS shell recipe is guarded by a literal `CC == clang` check; the musl compiler is named `musl-clang` and does not enter it.
- JIT configuration is nested inside the PGO branch. That is PBS implementation policy, not a reason this project's feature selection should have the same coupling.
- `--enable-optimizations` in CPython means PGO; it is not a generic spelling for `-O3`. `--with-lto` is independent. Clang LTO needs compatible archive/linker tools. Choose an explicit supported LTO mode and record it, rather than inferring “full LTO” from an artifact whose name just says `lto`. [R5, R17]

PBS explicitly enables mimalloc on relevant Python versions so missing support fails rather than silently changing allocator behavior. It disables CPython's HACL SIMD-helper configure probes, with comments concerning x86 ISA requirements and ARM64 performance. It also forces `ac_cv_func_explicit_bzero=no` for 3.14+, motivated by its old-glibc compatibility policy. [R5]

For the independent musl build, preserve default interpreter semantics and allocator support, select a generic x86_64 CPU baseline, and evaluate HACL behavior. Do not copy an old-glibc probe override blindly. Do not enable `-march=native`, globally require AVX/SSE levels above the product baseline, or disable useful optional runtime-dispatched code without checking why. Where a narrow compatibility patch is necessary, give it a regression test.

No PGO/BOLT/JIT machinery is required for M1. Do not add LLVM profiling tools, JIT stencil-generation dependencies, BOLT tools, instrumentation statistics, pooled profile handling, or profile-file caches merely because they appear upstream.

### A.5 Separate host Python: why PBS has it and why M1 need not

PBS builds a dedicated host CPython and passes it using `--with-build-python`, even in some cases that are effectively native. A patch forces its use for freezing, and another exports `PYTHON_FOR_BUILD` through a helper target. Musl output built from a GNU-hosted environment is handled as cross-compilation. Additional configure-cache answers work around probes that cannot execute target binaries. [R5, R9]

On native amd64 Alpine, use CPython's normal native bootstrap/frozen-module process first. Do not force `cross_compiling=yes`, falsify `--host`/`--build`, supply obsolete cache answers, or build a second full host Python because PBS chose to. A native build may of course create the bootstrap executables CPython itself requires.

The orchestration Python is separate: use a locked native Alpine Python, with standard-library-only controller code where practical. Do not let uv, pyenv, or an invisible fallback download a PBS interpreter. For future genuine cross-compilation, introduce a build Python only when required, with its exact source/version role recorded.

### A.6 Extension-module takeover and its cost

PBS generates `Modules/Setup.local` and `Makefile.extra`, patches out much of configure's stdlib-module selection, and disables `checksharedmods` because the altered mechanism violates the checker's assumptions. Its comments explicitly acknowledge the trade-off. It compensates for additional details, such as manually linking HACL libraries, within that custom path. [R4, R5]

This project should do the opposite initially: **use CPython 3.14.6's existing configure/module machinery and keep its checks active**. Feed it a controlled dependency prefix, isolated pkg-config search paths, and explicit per-library flags supported by the actual configure script. Static third-party libraries can often be linked into ordinary shared extension modules without making every extension a built-in module. Use small `Setup.local` overrides only for demonstrated gaps; do not create a second module-description DSL.

Derive the reference module inventory and compare observable capabilities. Different built-in/shared placement is a possible intentional difference; a missing capability is not equivalent. Keep reference-only test/internal modules separate from user-facing stdlib requirements.

### A.7 Static libpython is not static libc

PBS backports `--enable-static-libpython-for-interpreter` to 3.14. The option was upstreamed for Python 3.15 in CPython PR 133313. It builds shared libpython for embedders but links the executable to static libpython. This does **not** make the interpreter fully static or remove its musl loader requirement. The selected PBS products support dynamic extension loading. [R5, R10]

A narrow backport of that option is worth evaluating for parity, without importing PBS's module-generation machinery. Start from a working conventional `--enable-shared` build if that accelerates diagnosis. Retain the backport only if it is straightforward, isolated, and passes runtime/embedding tests; otherwise record shared-libpython linkage as a deliberate difference with measurements. Never pretend the 3.15 configure option exists unpatched in stock 3.14.6.

PBS also adds an executable RPATH even when its interpreter statically contains libpython, because some third-party extensions explicitly request the shared library. Its source describes potential hazards from loading a second libpython copy via `ctypes.CDLL()` and recommends looking up already-loaded symbols with `CDLL(None)` for such use. Shared-libpython linkage avoids that particular duplicate-runtime design but has its own loader/isolation requirements. Test both normal extension loading and an embedder; do not settle this solely from a flag name. [R10]

### A.8 Relocatability: preserve the outcomes, not every rewrite

PBS contains changes for interpreter path discovery, symlinks/venvs, ctypes, Tcl/Tk resource lookup, and relative `build-details.json` paths. It edits sysconfig data, python-config, Makefiles, pkg-config metadata, and installed script shebangs. On macOS it also removes build-machine SDK paths and flags unsuitable for consumers compiling extensions. [R5, R10, R11]

Its Linux interpreter gets an `$ORIGIN/../lib` RPATH via patchelf. Its ABI3 libpython handling distinguishes musl: the source states musl does not expand `$ORIGIN` in `DT_NEEDED`, so it uses RPATH/RUNPATH there instead. **Do not adopt a glibc-only `$ORIGIN`-inside-`DT_NEEDED` trick.** For this project's actual layout, calculate origin-relative search paths for every shipped DSO that needs private dependencies; one interpreter RPATH is not a universal substitute for inspecting the complete dependency graph. Prefer correct link-time paths over postprocessing when feasible. [R10]

On macOS, PBS uses `install_name_tool`, `@rpath`, executable-/loader-relative paths, and header padding for load-command edits and signatures. It normalizes system-zlib references. Targeting macOS 11.0 is its deployment-floor policy, **not** the identity of the SDK used to compile it. That SDK and Apple toolchain are future declared inputs, not Linux build prerequisites. [R6, R10]

Use a normal CPython layout, first test how far unpatched CPython already relocates, then fix observed gaps. Avoid global byte/string replacement across binaries or blanket deletion of configuration fields. Internal build flags/absolute paths should not leak into consumer extension builds, but ABI-required flags must survive.

### A.9 Dependency linkage, data, and pip

PBS mostly statically links third-party dependencies by deleting their shared-library outputs from its private dependency prefix; Tcl/Tk are exceptions. That is a mechanism, not the requirement. Build PIC static libraries directly where supported. Where dynamic libraries materially simplify the result, bundle and relocate those private libraries rather than assuming the target machine has Alpine's matching APK installed. Do not remove anything from the host's `/usr/lib`. [R5, R10]

Linux reference readline uses libedit, not GNU readline. Its `_dbm` preference is Berkeley DB; macOS uses ndbm. A different dbm backend can change persistent file compatibility, not just a version string. Tcl/Tk includes script/resource trees and X11 dependencies on Linux; a successful `_tkinter` import is not proof that Tcl scripts or a Tk window work after relocation. OpenSSL has providers, configuration, and trust-store considerations beyond `import ssl`. Ncurses can require terminfo data. [R5, R6, R10]

PBS disables install-time ensurepip, installs a pinned pip wheel offline, includes no setuptools for Python 3.14, and removes `__pycache__` from the installation payload. Preserve usable pip/venv and a deliberate bytecode policy. There is no need to copy its host-Python trick for installing pip on a native build. Do not add an `EXTERNALLY-MANAGED` marker simply because Alpine's system Python package has one; this is a separately managed standalone installation, not `/usr/bin/python3`. [R10, R11, R19]

### A.10 Packaging, reproducibility, and isolation observations

PBS's full tar archives sort members, place `PYTHON.json` first, normalize ownership and modes, and use timestamp **1704067200**. The full archive is compressed with Python `zstandard` at level 22 and `BTULTRA2`. These choices concern the full build distribution, which contains metadata and build material beyond the consumer installation. [R12]

Its Rust packaging code converts full distributions to install-only and stripped install-only archives. It selects entries, filters content, rewrites paths, uses its own tar/gzip implementation including flate2, and invokes LLVM stripping with `--strip-debug`. An equivalent useful installation does not require the same archive library, compressor, object-file payload, or conversion program. Use the small local packaging stage specified in Section 9. [R13]

CPython 3.14.6's `getbuildinfo.c` embeds `DATE` and `TIME`, defaulting to compiler date/time macros. Normalizing archive timestamps does not normalize those compiled values. OpenSSL-generated metadata, absolute paths, debug/bitcode material, build IDs, Mach-O UUIDs/signatures, and compressor versions are additional byte-difference investigation points. Record the project's effective inputs and investigate actual differences rather than treating a normalized tar as proof of reproducibility. [R14]

The macOS reference's PGO workload uses instrumented execution based on `-m test --pgo -j NUM_CPUS`, with pooled profile handling. This is relevant when interpreting performance comparisons with the LTO-only macOS roadmap target. Recovering or generating profiling inputs is outside this project's optimization policy. [R5]

PBS's execution layer has isolation limitations: macOS uses a nonisolated random temporary directory; environment setup can read `~/.python-build-standalone-env`; parallelism derives from the machine; and container operations do not by themselves enforce an offline boundary. A `--serial` setting at one level does not control every nested `nproc`-based operation. These observations motivate declared environments, explicit parallelism, and negative isolation tests in Section 7. [R7, R12, R15]

### A.11 Additional Alpine evidence

Alpine's `main/python3/APKBUILD` at commit `d17c5866a2f2c56b63c19dac9070091d6519b167` is a useful native-musl comparison. It packages **3.14.7**, so it is **not** this project's source pin and should not replace 3.14.6. It demonstrates a conventional configure/make build, shared libpython, system dependency selection, explicit per-module development dependencies, and a much smaller patch footprint than PBS. Its PGO invocation and `/usr` packaging policy are not to be copied. [R19]

Two concrete details need explicit investigation:

**Thread stack sizing.** That recipe uses a 2 MiB `THREAD_STACK_SIZE` compile definition and an ELF `-z stack-size` setting, and includes a thread-recursion smoke test. It places private build flags in `CFLAGS_NODIST` / `LDFLAGS_NODIST` rather than leaking them into consumer builds. Check CPython 3.14.6's behavior and use a narrow, tested stack policy appropriate to musl. Run thread recursion, real C-FFI recursion/callback, thread-pool, and relevant upstream tests; Python-only recursion by itself may not adequately stress the native C stack. The ELF stack-size hint and the per-thread compile-time setting are related but not interchangeable. [R19]

**`ctypes.util.find_library`.** Alpine carries `musl-find_library.patch`, an old-origin patch which searches library paths, handles musl's combined libc/libm/libpthread naming, checks ELF magic, and avoids depending on glibc `ldconfig` behavior. Its historical path names and broad branch are not automatically the right relocation behavior for the product's private library directory. Test `find_library`, `CDLL(None)`, absolute-path loading, SONAME loading, and callbacks in the final minimal runtime without compiler/binutils helpers. Adopt or replace only the relevant behavior, with provenance and tests. Do not claim that finding a filename proves its ABI is compatible. [R20]

Alpine's listed test exclusions are leads to investigate, not a ready-made skip list. They include locale, libc, kernel, timing, and architecture-specific issues. Run this project's tests and justify each exclusion from actual evidence; do not import wholesale skips that hide regressions. [R19]

### A.12 Isolation and musllinux compatibility

An Alpine userspace can run in a same-architecture chroot on another Linux distribution without Docker. The host kernel is still shared. A plain chroot does not isolate networking and is not by itself secure containment of a privileged hostile process. Add enforced process/filesystem/network boundaries and keep the build unprivileged. [R21]

PEP 656 concerns Python interpreters dynamically linked against musl. Fully static interpreters and mixed-libc builds are out of its scope. Verify actual packaging tags using the built interpreter's pip/packaging behavior; don't relabel incompatible binaries `musllinux` or claim manylinux/glibc-wheel compatibility. Runtime musl detection and wheel tags are not a substitute for testing the compatibility floor of this standalone interpreter and its bundled libraries. [R22]

## Appendix B. Reference artifact identities

The following release-metadata fingerprints identify comparison-only inputs. Verify downloaded bytes before inspecting or executing them. These are recorded source/release-metadata values, not a claim that every listed archive has been downloaded and independently rehashed during preparation of this specification. [R1]

For M1, acquire only the x86_64 musl references that a comparison needs. The stripped install-only archive is a consumer comparison; the full archive can supply build metadata and module information. ARM/macOS entries support the roadmap research and are not initial downloads.

No interpreter, native library, object, generated header, standard-library file, or installed pip from these archives may become a product build input. Run reference binaries only in the isolated comparison environment described in Section 8.

```json
{
  "status": "comparison inputs only; not target build inputs or required output hashes",
  "research_date": "2026-09-17",
  "upstream": {
    "repository": "https://github.com/astral-sh/python-build-standalone",
    "release": "20260610",
    "build_commit": "f1d7b92301235781d4de2493578773aaa413c0a5",
    "asset_metadata": "https://github.com/astral-sh/python-build-standalone/releases/expanded_assets/20260610"
  },
  "artifacts": [
    {
      "target": "x86_64-unknown-linux-musl",
      "variant": "lto-full.tar.zst",
      "name": "cpython-3.14.6+20260610-x86_64-unknown-linux-musl-lto-full.tar.zst",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-x86_64-unknown-linux-musl-lto-full.tar.zst",
      "sha256": "0fbf6847b5e80fc27027a2979182ebf1d4d35fddc9fc8be23f4d1653c0a1a9a7",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "x86_64-unknown-linux-musl",
      "variant": "install_only.tar.gz",
      "name": "cpython-3.14.6+20260610-x86_64-unknown-linux-musl-install_only.tar.gz",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-x86_64-unknown-linux-musl-install_only.tar.gz",
      "sha256": "c55940c8ef8cfa73a8a5bc2c1cf3ea37cc87c92f7bd208adbbd283f4a1df652b",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "x86_64-unknown-linux-musl",
      "variant": "install_only_stripped.tar.gz",
      "name": "cpython-3.14.6+20260610-x86_64-unknown-linux-musl-install_only_stripped.tar.gz",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-x86_64-unknown-linux-musl-install_only_stripped.tar.gz",
      "sha256": "54eca143d09ed3c596ecad5e3bfcb7724387818f8f984f44f3d8c0e9f36681d3",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "aarch64-unknown-linux-musl",
      "variant": "lto-full.tar.zst",
      "name": "cpython-3.14.6+20260610-aarch64-unknown-linux-musl-lto-full.tar.zst",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-aarch64-unknown-linux-musl-lto-full.tar.zst",
      "sha256": "3b72e88f0a0c6653563287c6ef912b712e0165c7bcee04ac88aee8f27725d73d",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "aarch64-unknown-linux-musl",
      "variant": "install_only.tar.gz",
      "name": "cpython-3.14.6+20260610-aarch64-unknown-linux-musl-install_only.tar.gz",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-aarch64-unknown-linux-musl-install_only.tar.gz",
      "sha256": "f51342846ea9a043c1b933cff6c8b7be6fd6c644a922d9330e8f48a725e9e1f3",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "aarch64-unknown-linux-musl",
      "variant": "install_only_stripped.tar.gz",
      "name": "cpython-3.14.6+20260610-aarch64-unknown-linux-musl-install_only_stripped.tar.gz",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-aarch64-unknown-linux-musl-install_only_stripped.tar.gz",
      "sha256": "5c75bea22f425ebc94912c618518a5aa4753eedeea6b5da5939f027d3a9c0fec",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "aarch64-apple-darwin",
      "variant": "pgo+lto-full.tar.zst",
      "name": "cpython-3.14.6+20260610-aarch64-apple-darwin-pgo+lto-full.tar.zst",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-aarch64-apple-darwin-pgo+lto-full.tar.zst",
      "sha256": "104d0ebde43207192b84b3907f5d63e665325282703dec8c0d416918ff66cf3f",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "aarch64-apple-darwin",
      "variant": "install_only.tar.gz",
      "name": "cpython-3.14.6+20260610-aarch64-apple-darwin-install_only.tar.gz",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-aarch64-apple-darwin-install_only.tar.gz",
      "sha256": "953db72ff2dea68b5112231b1ba77163ec9114f87c7ece530b3ea742a3b492c5",
      "role": "comparison-only; never a compiled distribution input"
    },
    {
      "target": "aarch64-apple-darwin",
      "variant": "install_only_stripped.tar.gz",
      "name": "cpython-3.14.6+20260610-aarch64-apple-darwin-install_only_stripped.tar.gz",
      "url": "https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-aarch64-apple-darwin-install_only_stripped.tar.gz",
      "sha256": "875516e13be36296f8f7dd0972b22ba3bed069ed08d27d5f0069caf227522921",
      "role": "comparison-only; never a compiled distribution input"
    }
  ]
}
```

## Appendix C. PBS compiler and base-image identities

These inputs document how the reference distributions were built. The Linux LLVM archives require a GNU/glibc build userspace and are not permitted native Alpine compiler inputs. The Debian images are research context, not environments to reconstruct for M1. Use the project's own locked native Alpine toolchain and source-built bundled target libraries. The macOS compiler identity is an observation, not a decision to depend on that archive for the future macOS build. [R2, R6, R7]

```json
{
  "role": "observed PBS toolchain inputs; not this project's bootstrap lock",
  "compiler_bootstraps": [
    {
      "host": "linux_aarch64",
      "version": "22.1.3+20260410",
      "url": "https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20260410/llvm-22.1.3+20260410-gnu_only-aarch64-unknown-linux-gnu.tar.zst",
      "size": 237655768,
      "sha256": "9cb4b562323a3d899fffe6393148e92447e17b69a2501d7c6e7f2a86c32cddc1"
    },
    {
      "host": "linux_x86_64",
      "version": "22.1.3+20260410",
      "url": "https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20260410/llvm-22.1.3+20260410-gnu_only-x86_64-unknown-linux-gnu.tar.zst",
      "size": 281109065,
      "sha256": "0ee8e4f89c20983d62547b1e665147ee08a7413f478e9e443fa991548da1030d"
    },
    {
      "host": "macos_arm64",
      "version": "22.1.3+20260410",
      "url": "https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20260410/llvm-22.1.3+20260410-aarch64-apple-darwin.tar.zst",
      "size": 159775425,
      "sha256": "98171836c31c04edec074e5f3fee67fcace4bf3859b68a770dd9ff2039ea127d"
    }
  ],
  "base_images": {
    "x86_64": "debian@sha256:32ad5050caffb2c7e969dac873bce2c370015c2256ff984b70c1c08b3a2816a0",
    "aarch64": "debian@sha256:c5c5200ff1e9c73ffbf188b4a67eb1c91531b644856b4aefe86a58d2f0cb05be",
    "note": "These are PBS base-image references, not identities for complete derived builder environments."
  }
}
```

A compiler version string or base-image digest alone does not identify all build inputs. The reference identities do not provide a complete package closure, Apple SDK/OS/linker manifest, bootstrap-tool environment, or record of embedded temporary paths and profiling data. The implementation must produce a complete lock and provenance for its own build; reconstructing those missing upstream environmental details is not an acceptance requirement.

## Appendix D. Dependency source fingerprints

These entries are candidate source identities recorded from the pinned PBS download manifest. They are reference data for selecting independent source inputs, not an instruction to import that manifest as executable code. [R2] They are not proof that an origin will remain online, nor a complete lock. Before using an entry, verify its downloaded bytes and record the source, tool packages, transitive dependencies, license, and selected configuration in the project's own lock. Origin substitutions require verifying the bytes; two archives of the same version can have different hashes.

```json
[
  {
    "component": "bzip2",
    "version": "1.0.8",
    "url": "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz",
    "sha256": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269"
  },
  {
    "component": "Expat",
    "version": "2.8.1",
    "url": "https://github.com/libexpat/libexpat/releases/download/R_2_8_1/expat-2.8.1.tar.xz",
    "sha256": "10b195ee78160a908388180a8fe3603d4e9a12f4755fbf5f3816b23a9d750da0"
  },
  {
    "component": "libedit",
    "version": "20240808-3.1",
    "url": "https://thrysoee.dk/editline/libedit-20240808-3.1.tar.gz",
    "sha256": "5f0573349d77c4a48967191cdd6634dd7aa5f6398c6a57fe037cc02696d6099f"
  },
  {
    "component": "libffi (musl reference)",
    "version": "3.3",
    "url": "https://github.com/libffi/libffi/releases/download/v3.3/libffi-3.3.tar.gz",
    "sha256": "72fba7922703ddfa7a028d513ac15a85c8d54c8d67f55fa5a4802885dc652056"
  },
  {
    "component": "libffi (macOS reference)",
    "version": "3.4.6",
    "url": "https://github.com/libffi/libffi/releases/download/v3.4.6/libffi-3.4.6.tar.gz",
    "sha256": "b0dea9df23c863a7a50e825440f3ebffabd65df1497108e5d437747843895a4e"
  },
  {
    "component": "OpenSSL",
    "version": "3.5.7",
    "url": "https://github.com/openssl/openssl/releases/download/openssl-3.5.7/openssl-3.5.7.tar.gz",
    "sha256": "a8c0d28a529ca480f9f36cf5792e2cd21984552a3c8e4aa11a24aa31aeac98e8"
  },
  {
    "component": "SQLite",
    "version": "3.53.1",
    "url": "https://www.sqlite.org/2026/sqlite-autoconf-3530100.tar.gz",
    "sha256": "83e6b2020a034e9a7ad4a72feea59e1ad52f162e09cbd26735a3ffb98359fc4f"
  },
  {
    "component": "mpdecimal",
    "version": "4.0.0",
    "url": "https://www.bytereef.org/software/mpdecimal/releases/mpdecimal-4.0.0.tar.gz",
    "sha256": "942445c3245b22730fd41a67a7c5c231d11cb1b9936b9c0f76334fb7d0b4468c"
  },
  {
    "component": "ncurses",
    "version": "6.5",
    "url": "https://ftp.gnu.org/pub/gnu/ncurses/ncurses-6.5.tar.gz",
    "sha256": "136d91bc269a9a5785e5f9e980bc76ab57428f604ce3e5a5a90cebc767971cc6"
  },
  {
    "component": "Berkeley DB",
    "version": "6.0.19",
    "url": "https://ftp.osuosl.org/pub/blfs/conglomeration/db/db-6.0.19.tar.gz",
    "sha256": "2917c28f60903908c2ca4587ded1363b812c4e830a5326aaa77c9879d13ae18e"
  },
  {
    "component": "libuuid",
    "version": "1.0.3",
    "url": "https://sourceforge.net/projects/libuuid/files/libuuid-1.0.3.tar.gz",
    "sha256": "46af3275291091009ad7f1b899de3d0cea0252737550e7919d17237997db5644"
  },
  {
    "component": "Tcl",
    "version": "9.0.3",
    "url": "https://prdownloads.sourceforge.net/tcl/tcl9.0.3-src.tar.gz",
    "sha256": "2537ba0c86112c8c953f7c09d33f134dd45c0fb3a71f2d7f7691fd301d2c33a6"
  },
  {
    "component": "Tk",
    "version": "9.0.3",
    "url": "https://prdownloads.sourceforge.net/tcl/tk9.0.3-src.tar.gz",
    "sha256": "bf344efadb618babb7933f69275620f72454d1c8220130da93e3f7feb0efbf9b"
  },
  {
    "component": "xz/liblzma",
    "version": "5.8.1",
    "url": "https://github.com/tukaani-project/xz/releases/download/v5.8.1/xz-5.8.1.tar.gz",
    "sha256": "507825b599356c10dca1cd720c9d0d0c9d5400b9de300af00e4d1ea150795543"
  },
  {
    "component": "zlib",
    "version": "1.3.1",
    "url": "https://github.com/madler/zlib/releases/download/v1.3.1/zlib-1.3.1.tar.gz",
    "sha256": "9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23"
  },
  {
    "component": "zstd source-deps export",
    "version": "1.5.7",
    "url": "https://github.com/python/cpython-source-deps/archive/refs/tags/zstd-1.5.7.tar.gz",
    "sha256": "f24b52470d12f466e9fa4fcc94e6c530625ada51d7b36de7fdc6ed7e6f499c8e"
  },
  {
    "component": "pip wheel",
    "version": "26.1.2",
    "url": "https://files.pythonhosted.org/packages/5d/95/6b5cb3461ea5673ba0995989746db58eb18b91b54dbf331e72f569540946/pip-26.1.2-py3-none-any.whl",
    "sha256": "382ff9f685ee3bc25864f820aa50505825f10f5458ffff07e30a6d96e5715cab"
  },
  {
    "component": "libX11",
    "version": "1.6.12",
    "url": "https://www.x.org/archive/individual/lib/libX11-1.6.12.tar.gz",
    "sha256": "0fce5fc0a24a3dc728174eccd0cb8d6a1b37a2ec1654bd5628c84e5bc200d594"
  },
  {
    "component": "libXau",
    "version": "1.0.11",
    "url": "https://www.x.org/releases/individual/lib/libXau-1.0.11.tar.gz",
    "sha256": "3a321aaceb803577a4776a5efe78836eb095a9e44bbc7a465d29463e1a14f189"
  },
  {
    "component": "libxcb",
    "version": "1.17.0",
    "url": "https://xcb.freedesktop.org/dist/libxcb-1.17.0.tar.gz",
    "sha256": "2c69287424c9e2128cb47ffe92171e10417041ec2963bceafb65cb3fcf8f0b85"
  },
  {
    "component": "xcb-proto",
    "version": "1.17.0",
    "url": "https://xcb.freedesktop.org/dist/xcb-proto-1.17.0.tar.xz",
    "sha256": "2c1bacd2110f4799f74de6ebb714b94cf6f80fb112316b1219480fd22562148c"
  },
  {
    "component": "xorgproto",
    "version": "2024.1",
    "url": "https://www.x.org/archive/individual/proto/xorgproto-2024.1.tar.gz",
    "sha256": "4f6b9b4faf91e5df8265b71843a91fc73dc895be6210c84117a996545df296ce"
  },
  {
    "component": "xtrans",
    "version": "1.6.0",
    "url": "https://www.x.org/archive/individual/lib/xtrans-1.6.0.tar.gz",
    "sha256": "936b74c60b19c317c3f3cb1b114575032528dbdaf428740483200ea874c2ca0a"
  },
  {
    "component": "X11 util-macros",
    "version": "1.20.2",
    "url": "https://www.x.org/archive/individual/util/util-macros-1.20.2.tar.gz",
    "sha256": "f642f8964d81acdf06653fdf9dbc210c43ce4bd308bd644a8d573148d0ced76b"
  },
  {
    "component": "libpthread-stubs",
    "version": "0.5",
    "url": "https://www.x.org/archive/individual/lib/libpthread-stubs-0.5.tar.gz",
    "sha256": "593196cc746173d1e25cb54a93a87fd749952df68699aab7e02c085530e87747"
  }
]
```

## Appendix E. Primary sources

Reference research date: 2026-09-17. PBS implementation URLs identify the fixed reference commit. CPython and Alpine source URLs identify their separate versions or commits. Documentation and package-index links are explanatory/discovery sources, not immutable build inputs; the verified source tarball and project locks govern exact implementation behavior.

### R1. PBS comparison release and published asset list

- <https://github.com/astral-sh/python-build-standalone/releases/tag/20260610>
- <https://github.com/astral-sh/python-build-standalone/releases/expanded_assets/20260610>

### R2. Download versions, source hashes, mirror URLs, compiler bootstrap identities

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/downloads.py>

### R3. Top-level Unix dispatch and Make orchestration

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/build.py>
- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/build-main.py>
- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/Makefile>
- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/build.py>

### R4. Extension inventory and build metadata generation

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/extension-modules.yml>
- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/cpython.py>

### R5. Main CPython recipe: patch selection, compiler feature conditions, configure, PGO, modules and installation

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/build-cpython.sh>

### R6. Target triples, dependency families, macOS minimum, frame pointers and compiler selection

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/targets.yml>

### R7. Docker environment and image assembly; inspect Dockerfile recipes referenced by these modules

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/docker.py>
- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/buildenv.py>

### R8. Musl 1.2.2 reallocarray compatibility surgery

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/build-musl.sh>

### R9. Dedicated host CPython and environment/bootstrap behavior

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/build-cpython-host.sh>
- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/buildenv.py>

### R10. libpython linkage, loader paths, pip installation and initial sysconfig edits; static-interpreter upstream change

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/build-cpython.sh#L750-L1080>
- <https://github.com/python/cpython/pull/133313>

### R11. Remaining sysconfig, shebang, pkg-config, payload and bytecode handling; inspect the rest of the recipe

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/cpython-unix/build-cpython.sh>

### R12. Full-archive normalization, compression, environment and download verification helpers

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/utils.py>

### R13. Rust install-only/stripped archive conversion and archive-postprocessing LLVM tools

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/src/release.rs>

### R14. Exact CPython 3.14.6 build-information source

- <https://github.com/python/cpython/blob/v3.14.6/Modules/getbuildinfo.c>

### R15. Temporary-directory/container execution behavior

- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/buildenv.py>
- <https://github.com/astral-sh/python-build-standalone/blob/f1d7b92301235781d4de2493578773aaa413c0a5/pythonbuild/utils.py>

### R16. CPython source release and exact configure source

- <https://www.python.org/ftp/python/3.14.6/Python-3.14.6.tar.xz>
- <https://github.com/python/cpython/blob/v3.14.6/configure.ac>
- <https://github.com/python/cpython/blob/v3.14.6/Makefile.pre.in>

### R17. CPython 3.14 configure options; verify against the pinned source for patch-level details

- <https://docs.python.org/3.14/using/configure.html>
- <https://github.com/python/cpython/blob/v3.14.6/Doc/using/configure.rst>

### R18. Alpine compiler-package evidence; verify exact target architecture/branch before locking

- <https://pkgs.alpinelinux.org/package/edge/main/x86_64/clang22-dev>
- <https://pkgs.alpinelinux.org/package/v3.24/main/ppc64le/clang22>
- <https://pkgs.alpinelinux.org/package/v3.24/main/x86_64/lld22-dbg>

### R19. Alpine native Python packaging: 2 MiB stack settings, NODIST flags, normal configure, tests; this source is 3.14.7, not the target version

- <https://github.com/alpinelinux/aports/blob/d17c5866a2f2c56b63c19dac9070091d6519b167/main/python3/APKBUILD>

### R20. Alpine musl ctypes library-discovery patch; inspect behavior rather than copying blindly

- <https://github.com/alpinelinux/aports/blob/d17c5866a2f2c56b63c19dac9070091d6519b167/main/python3/musl-find_library.patch>

### R21. Alpine chroot execution and limits; do not copy unverified latest/untrusted bootstrap examples

- <https://wiki.alpinelinux.org/wiki/Alpine_Linux_in_a_chroot>
- <https://wiki.alpinelinux.org/wiki/Chroot>

### R22. PEP 656: dynamic-musl interpreter scope and wheel compatibility tagging

- <https://peps.python.org/pep-0656/>
