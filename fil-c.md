You are working on two local repositories:

* The primary/product repository is `joshuarli/python-build`. Start from its current checkout and read `AGENTS.md` completely before making changes.
* Fil-C is already cloned at `~/d/fil-c`.
* **DO NOT clone Fil-C again.** It is an enormous repository. Treat `~/d/fil-c` as the authoritative local Fil-C checkout.
* You are explicitly authorized to modify **both repositories** as needed.
* You are also authorized to create/use a `joshuarli/fil-c` fork if changes to Fil-C itself are required. If a fork is needed, use the existing `~/d/fil-c` checkout, add the fork as a remote, and push from there. Do not reclone it.
* Do not ask me questions. Make technically sound decisions and continue until the completion contract below is satisfied.

# Mission

Add a genuinely working **CPython 3.14.6 built with Fil-C on Linux x86_64 using Fil-C's musl/Pizfix runtime** to `python-build`, as an additional build alongside the existing:

* `aarch64-apple-darwin`
* `x86_64-unknown-linux-musl`
* `aarch64-unknown-linux-musl`

The existing builds must continue to work unchanged.

This is not a feasibility spike and not a "get it compiling" task. You own the complete implementation, including changes to Fil-C itself if CPython 3.14.6 exposes compiler/runtime/libc limitations.

**Do not stop until we have a real CPython 3.14.6 interpreter built by python-build with Fil-C, with its native dependency closure built for the Fil-C ABI, packaged, tested, and built in CI.**

glibc is completely out of scope. Do not use `/opt/fil`, Fil-C glibc, or Pizlix's glibc configuration. We are interested only in the classic **musl-based Pizfix Fil-C environment**.

A normal Linux/glibc host is acceptable as a bootstrap/build host. The produced Fil-C target and its entire runtime/native-library closure must be Fil-C/musl.

# Definition of done

The task is complete only when all of the following are true:

1. `python-build` has an explicit additional target, preferably named something unambiguously ABI-distinct such as:

   `x86_64-filc-linux-musl`

   Do **not** masquerade it as `x86_64-unknown-linux-musl`. Fil-C has a different ABI from ordinary musl C.

2. CPython is exactly **3.14.6**, from the existing locked CPython source in `python-build`.

3. CPython itself is compiled by the Fil-C compiler from the Pizfix toolchain.

4. Every native library linked into CPython or its extension modules is compatible with the Fil-C ABI. Do not accidentally link ordinary Alpine/Ubuntu libraries into the Fil-C program.

5. The build uses Fil-C's **musl** libc/runtime and Fil-C loader. No Fil-C glibc path exists anywhere in the implementation.

6. The resulting interpreter genuinely runs Python and preserves `python-build`'s existing useful Linux product scope. At minimum all existing `REQUIRED_MODULES` applicable to Linux must work, including SSL/hashlib, SQLite, decimal, ctypes/libffi callbacks, zlib/bz2/lzma/zstd, readline, curses, dbm, multiprocessing, threading, subprocess, sockets, etc.

7. The shipped artifact is self-contained with respect to the Fil-C runtime. A consumer must not need a pre-existing Fil-C installation.

8. Native extension support is demonstrated using the same pinned Fil-C ABI/toolchain. A trivial C extension must compile and load successfully.

9. The Fil-C build cannot accidentally consume an ordinary native musl/glibc CPython extension. Make its ABI identity explicit. Prefer a Fil-C-specific SOABI/extension suffix such as an `x86_64-filc-linux-musl` spelling rather than claiming ordinary CPython/musl ABI compatibility.

10. Existing ordinary musl and macOS artifacts remain green.

11. GitHub CI actually builds and tests the Fil-C x86_64 artifact.

12. The release pipeline publishes the Fil-C archive as a clearly distinct additional release asset.

13. **Do not put the Fil-C artifact into the ordinary uv `linux-x86_64-musl` download metadata.** uv has no Fil-C ABI dimension and advertising this as a normal musl CPython would be incorrect.

14. If Fil-C itself needs changes, those changes exist as clean commits in the Fil-C fork/local checkout, and `python-build` CI consumes an immutable, hash-pinned compact Fil-C toolchain artifact corresponding exactly to those changes.

15. No CI path clones the gigantic Fil-C repository just to build Python. CI consumes a compact prebuilt Fil-C Pizfix toolchain archive. `~/d/fil-c` is for local development and for producing that toolchain when necessary.

16. The final CI workflow has been dispatched and observed to pass. Do not stop at "the YAML looks right."

# Important existing Fil-C prior art

Read the current Fil-C tree before changing anything.

Fil-C currently has an upstream CPython port under:

`~/d/fil-c/projects/Python-3.12.5`

and its build driver:

`~/d/fil-c/build_cpython.sh`

A particularly useful historical anchor is Fil-C commit:

`4d81217a0e270ee87396680624a5218a1bc4afe8`

which contains the Fil-C changes made to upstream Python 3.12.5.

Study that diff carefully, but **do not mechanically apply it to 3.14.6**. CPython internals have changed substantially. Forward-port the *semantics*.

The 3.12 Fil-C Python build used roughly:

* `--without-mimalloc`
* `--without-pymalloc`
* `--without-freelists`
* Fil-C clang
* Pizfix prefix

CPython 3.14.6 still supports `--without-mimalloc` and `--without-pymalloc`. The old `--without-freelists` configure option no longer exists; do not invent it. If 3.14 freelists are genuinely incompatible, fix the concrete problem rather than cargo-culting the removed option.

# Known CPython porting areas

Use the old Fil-C port as a map. Expect to investigate at least these classes of issues in 3.14.6:

## Pointer metadata and pointer/integer round trips

Fil-C capabilities are lost when pointers are treated as raw integers. CPython has historically relied heavily on these idioms.

Inspect and fix semantically where necessary:

* GC linked-list fields and tagged GC pointers.
* `_gc_next` / `_gc_prev`.
* low-bit tagging of pointers.
* `PyLong_FromVoidPtr` / `PyLong_AsVoidPtr`.
* pointer values serialized into compact structures such as code-object metadata.
* semaphore handles exposed through integer fields.
* pointer subtraction/arithmetic that assumes unrelated pointers can safely be treated as one flat address space.
* any new 3.14 instances discovered by compiler diagnostics or Fil-C panics.

Prefer Fil-C's actual capability-preserving primitives from `stdfil.h`, such as the existing pointer-table and pointer-retagging APIs, where they are the correct abstraction.

Do not silence diagnostics by scattering casts.

## CPython GC

The old port converted GC links from integer storage to capability-preserving pointer storage and used Fil-C pointer-tagging helpers.

CPython 3.14.6 still has integer-tagged GC links. Port this carefully.

The objective is to preserve CPython GC semantics while making pointer representation valid under Fil-C. Do not disable CPython GC.

## Interpreter frame/data stack

The old Fil-C port replaced CPython's manually managed interpreter-frame stack chunks with GC-backed allocations because the original scheme conflicted with Fil-C pointer/capability rules.

CPython 3.14.6 still has the `datastack_chunk`, `datastack_top`, `datastack_limit`, `_PyThreadState_PushFrame`, and `_PyThreadState_PopFrame` architecture.

Determine whether the old strategy is still necessary and, if so, forward-port it cleanly to 3.14.6 rather than trying to preserve invalid pointer arithmetic.

## Atomics

CPython atomics changed substantially between 3.12 and 3.14.

3.14 has first-class pointer atomic helpers, which may eliminate some old Fil-C patches.

Use pointer atomics for pointers. Do not convert a pointer into `uintptr_t` merely because an older CPython implementation did so.

## Allocators

Start the Fil-C CPython target with:

`--without-mimalloc --without-pymalloc`

Fil-C already provides memory-safe malloc/realloc/free on top of its GC.

Do not spend time preserving pymalloc unless later evidence demonstrates that doing so is both useful and straightforward.

Keep the ordinary python-build targets' allocator behavior unchanged.

## `_multiprocessing`

Study the old Fil-C semaphore-handle work. POSIX `sem_t *` passing through integer representations is a known capability problem.

Port only what 3.14 still needs.

Multiprocessing is part of the acceptance criteria; do not simply disable it.

## libffi / ctypes

This is important.

Fil-C's libffi support is not an ordinary libffi build: Fil-C has historically replaced assembly/JIT closure machinery with its reflection/closure APIs.

`python-build` currently pins libffi 3.8.0, and the current Fil-C repository already contains 3.8.0 material. Use the Fil-C implementation/patches as reference and port them into the python-build dependency build as necessary.

`ctypes`, callbacks, closures and function calls are hard acceptance gates.

## Architecture-specific assembly/SIMD

Fil-C already has porting work for several dependencies around:

* CPUID
* xgetbv
* inline assembly
* version scripts
* libffi assembly/JIT
* zstd assembly/SIMD
* OpenSSL assembly

Use current `~/d/fil-c` rather than reinventing these ports.

Where `python-build`'s exact locked version differs from Fil-C's ported source, forward-port the minimal patch to the locked source.

Do not silently substitute a different dependency version merely because Fil-C already vendors it.

# Dependency policy

The Fil-C Python must not accidentally link normal system libraries.

Start with the exact dependency versions already locked by python-build.

For every dependency in the Linux dependency graph:

* first attempt the locked upstream source with Fil-C;
* if it works unchanged, great;
* if Fil-C already has a corresponding patch/Projeny port, derive the minimal source/build patch from it;
* keep Fil-C-specific patches explicitly scoped to the Fil-C target;
* do not perturb the existing ordinary-musl builds;
* record provenance clearly enough that the patch can be updated later.

The current Fil-C tree already contains useful prior art for many of these components. Inspect at least:

* OpenSSL
* SQLite
* zlib
* bzip2
* xz
* zstd
* Expat
* libffi
* ncurses
* libedit

Also investigate mpdecimal, libuuid and Berkeley DB rather than assuming they work.

Do not satisfy CPython configure tests using an ordinary host library.

After the build, inspect every ELF dependency and prove the native closure is the Fil-C closure.

# Fil-C toolchain strategy

Do not begin by forking Fil-C.

First test current upstream/current local `~/d/fil-c`.

Use the classic musl build:

`./build_all_fast.sh`

Do not use any `*_glibc.sh` build.

Do not run the enormous full corpus build unless a concrete reason requires it. The fast build provides the compiler/runtime/musl/libc++ foundation needed for this task.

The compiler should come from:

`~/d/fil-c/build/bin/clang`

and its Pizfix from:

`~/d/fil-c/pizfix`

Make a tiny C smoke program first and verify the resulting ELF is actually Fil-C.

Then work toward python-build.

# When to modify/fork Fil-C

If CPython 3.14.6 exposes a real missing capability or bug in Fil-C itself rather than merely CPython source that assumes unsafe C semantics, fix Fil-C.

Examples include:

* incorrect compiler lowering,
* broken atomics,
* unsupported but valid C construct,
* loader/runtime defect,
* musl defect,
* libffi/closure/runtime issue that properly belongs in Fil-C,
* a generic Fil-C compiler/runtime feature needed by 3.14.

Do not contort CPython to compensate for a Fil-C compiler bug.

If Fil-C changes are necessary:

1. Work directly in `~/d/fil-c`.
2. Check its remotes.
3. If there is already a writable `joshuarli/fil-c` remote, use it.
4. Otherwise create the fork without cloning:
   `gh repo fork pizlonator/fil-c --clone=false`
5. Add that fork as a remote to the existing `~/d/fil-c`.
6. Create a focused branch, e.g. `python-3.14.6`.
7. Make clean, general-purpose Fil-C commits rather than CPython-specific hacks when the problem is genuinely generic.
8. Rebuild the fast musl/Pizfix toolchain and rerun relevant Fil-C tests.
9. Package the compact Pizfix binary toolchain using Fil-C's existing packaging machinery.
10. Publish that compact binary artifact from the fork under an immutable tag/release.
11. Pin its exact URL, digest, version/tag and provenance in python-build's bootstrap inputs.

**python-build CI must download that compact artifact, not clone `fil-c`.**

If stock Fil-C works with only CPython/dependency patches, prefer the official Fil-C 0.685 x86_64 Pizfix binary release as the pinned CI toolchain.

# python-build architecture

Keep the existing architecture clean.

Add a separate family such as:

`linux-filc-musl`

and a target such as:

`x86_64-filc-linux-musl`

Do not treat Fil-C as merely another compiler choice for the ordinary musl ABI.

The current target machinery assumes one native target per OS/architecture. Adding a second x86_64 Linux target makes `native_target()` ambiguous.

Fix this deliberately.

A reasonable shape is:

* explicit target selection for phase drivers;
* default-to-native behavior remains for the existing targets;
* Fil-C always requires the explicit Fil-C target;
* Docker/CI passes the target explicitly.

Do not make dictionary ordering decide which x86_64 target is selected.

Continue respecting python-build's principle that architecture/target policy is centralized rather than spread as random `if filc` statements.

A small `Target` capability such as `is_filc`, `abi`, or a family dispatch is preferable to string comparisons all over the repository.

# Optimization policy

Correctness and memory safety come first.

Linux currently uses `-O3`, ThinLTO and no PGO.

Try to retain appropriate optimization under Fil-C, but do not assume Fil-C supports python-build's existing ThinLTO path identically.

Establish this experimentally.

If ThinLTO works correctly with Fil-C, retain it.

If it does not, make **only the Fil-C target** a documented LTO exception rather than adding hacks or blocking the port forever.

Do not add PGO just for this target.

# Fil-C-specific ABI identity

This deserves explicit implementation, not merely documentation.

A Fil-C CPython extension is not ABI-compatible with an ordinary CPython extension compiled for Linux/musl.

Ensure that the Fil-C build advertises a distinct native-extension ABI.

Inspect and adjust as necessary:

* `SOABI`
* `EXT_SUFFIX`
* `sysconfig`
* `python3.14-config`
* extension suffix recognition in import machinery
* generated Makefile/sysconfig metadata

A standard clang-built `x86_64-linux-musl` extension must not accidentally look loadable by this interpreter.

Add tests for this.

Conversely, build a tiny extension with the pinned Fil-C compiler, install/copy it into a test location, import it, call it, and verify the result.

Also verify no build-root paths leak into installed sysconfig metadata.

# Runtime packaging and loader problem

Treat this as a first-class engineering problem.

Fil-C has its own ABI and its classic musl runtime includes a custom loader such as:

`ld-fil1-x86_64.so`

along with `libyoloc`, `libpizlo`, Fil-C libc and the rest of the required runtime closure.

A final Python artifact must not depend on `~/d/fil-c/pizfix`.

Bundle the exact runtime libraries needed by the Python distribution.

Make the final artifact runnable after extraction at an arbitrary path on an otherwise ordinary Linux x86_64 system with no preinstalled Fil-C.

Prefer a design that is immediately runnable after extraction.

Investigate whether directly invoking the bundled Fil-C loader through a small relocatable launcher is the cleanest way to avoid ELF `PT_INTERP`'s absolute-path limitation. If so, implement that carefully and ensure:

* `sys.executable`
* subprocess
* multiprocessing
* Python getpath/prefix discovery
* shared libpython
* extension-module loading

all still behave correctly.

If Fil-C fundamentally requires an install-time relocation/setup operation, a tiny idempotent setup step is acceptable only if there is no cleaner robust option. In that case:

* make it deterministic;
* make it impossible to accidentally use the build-tree Pizfix;
* test extraction into multiple unrelated absolute paths;
* document this target-specific behavior clearly.

Do not declare success with binaries that only run while `~/d/fil-c` happens to exist.

# Release/uv behavior

The ordinary three artifacts must keep their existing python-build-standalone/uv behavior.

The Fil-C artifact is a separate ABI and therefore a separate release asset.

Use a clearly distinct filename, for example:

`cpython-3.14.6+<tag>-x86_64-filc-linux-musl-install_only_stripped.tar.gz`

Do **not** insert it under:

`cpython-3.14.6-linux-x86_64-musl`

in `download-metadata.json`.

That key means ordinary musl CPython and would be false advertising.

The Fil-C artifact may have its own manifest/provenance JSON alongside the normal release assets.

Do not apply the existing Astral ordinary-musl archive-size budget to this ABI; the bundled Fil-C runtime makes that comparison meaningless.

# Validation requirements

Do not rely on "it compiled."

Add strong automated proof.

At minimum:

## Build identity

Prove with ELF/symbol inspection that CPython and representative extension modules are Fil-C output.

Check for expected Fil-C loader/runtime dependencies and/or Fil-C symbol structure.

Fail validation if an ordinary host libc/dependency has leaked into the native closure.

## Core runtime smoke

Run the existing `.github/scripts/toy.py`.

Add focused Fil-C runtime smoke for:

* imports
* exceptions
* GC
* cyclic GC
* large integers
* recursion
* generators/coroutines
* threads
* thread contention
* signals
* subprocess
* multiprocessing
* shared memory/mmap where supported
* sockets
* SSL
* SQLite
* ctypes
* ctypes callbacks/closures
* readline
* curses
* bz2
* lzma
* zlib
* zstd
* decimal
* dbm

## CPython regression suite

Run the actual installed CPython 3.14.6 regression suite.

Use the existing python-build philosophy:

* no giant Fil-C skip list;
* no hiding crashes;
* no "expected failure" merely because fixing it is inconvenient;
* retry actual flaky tests rather than classifying everything as flaky.

A small Fil-C-specific exclusion register is acceptable for tests that intentionally depend on unsafe/undefined C behavior or a consciously unsupported platform feature, but every exclusion must name the exact reason and consequence.

A Fil-C panic caused by valid Python behavior is a bug to fix.

## Native extension test

Compile a trivial extension with the pinned Fil-C compiler against the packaged Python headers/config.

Import it.

Exercise at least a normal function call and some allocation.

## Memory-safety proof

Add a separate test-only Fil-C extension or tiny executable that deliberately performs an unmistakable out-of-bounds/use-after-free access.

Run it in a subprocess.

Verify that Fil-C traps/panics rather than silently continuing.

This gives us direct evidence that we did not accidentally build ordinary clang CPython while merely linking some Fil-C-looking files.

## ABI negative test

Build an ordinary non-Fil-C native extension with the host compiler.

Verify that the Fil-C interpreter does not treat it as a compatible extension.

## Relocation

Extract/copy the final archive into at least two unrelated temporary prefixes and run it there.

Ensure:

* no `/work/...`
* no checkout paths
* no `~/d/fil-c`
* no CI workspace path
* no original Pizfix absolute path

appears in the runtime dependency resolution or installed sysconfig.

# CI

Add a dedicated Fil-C Linux x86_64 build job rather than complicating the existing ordinary-musl matrix unnecessarily.

The CI path should roughly be:

1. checkout `python-build`;
2. fetch/verify the compact pinned Fil-C musl Pizfix toolchain archive;
3. build the python-build native dependency closure with Fil-C;
4. build patched CPython 3.14.6 with Fil-C;
5. package;
6. run build identity checks;
7. run runtime/compatibility/regression tests;
8. upload the Fil-C dist artifact;
9. include it in release assets;
10. smoke-test the exact bytes being released on a clean Linux environment.

Do not clone the Fil-C source repository in this workflow.

For additional confidence, smoke the packaged result in two substantially different userspaces if practical, e.g. an Ubuntu runner and an Alpine container. Since this build carries its own Fil-C/musl slice, it should not accidentally depend on the host's glibc.

Do not add the Fil-C asset to ordinary uv metadata.

# Preserve current builds

Before large refactors, establish the current test baseline.

After implementation:

* run the full project unit-test suite;
* ensure existing x86_64 ordinary musl CI remains green;
* ensure aarch64 ordinary musl remains structurally unchanged/green;
* ensure macOS remains structurally unchanged/green.

Fil-C patches and configuration must be target-scoped.

# Code quality

Do not build a second parallel build system.

Extend the current architecture where the abstractions genuinely hold, and introduce a small Fil-C-specific layer where the ABI genuinely differs.

Keep:

* source locking;
* content-addressed caches;
* sealed/offline build discipline;
* explicit dependency provenance;
* target-scoped configuration;
* validation-first packaging;
* deterministic release assembly.

Avoid:

* shell-script sprawl;
* ad hoc environment-variable magic;
* duplicated copies of large Fil-C source trees;
* vendoring Fil-C into python-build;
* disabling features simply to make configure pass;
* broad warning suppression;
* unchecked pointer casts;
* pretending Fil-C is ordinary musl ABI.

Update `AGENTS.md` so the final architecture and target contract are accurately documented, but keep documentation lean and aligned with the repository's current style.

# Working method

Work empirically.

When something fails:

1. reduce it to the smallest concrete failure;
2. determine whether the bug is in CPython, a dependency, python-build integration, or Fil-C itself;
3. fix it in the correct layer;
4. add a regression test;
5. continue.

Use compiler diagnostics and Fil-C panics as useful information. Do not suppress them just to move forward.

When forward-porting the Python 3.12 Fil-C patch, compare the old source and the 3.14.6 source by semantic subsystem rather than line number.

It is entirely acceptable for this task to require substantial CPython patches. The objective is a correct Fil-C CPython 3.14.6, not an artificially tiny diff.

Likewise, it is acceptable to change Fil-C itself when the generic compiler/runtime is the correct layer.

# Do not stop early

The following are explicitly **not** completion:

* "Fil-C can probably compile Python."
* configure succeeds.
* CPython object files compile.
* the final link succeeds.
* `python -c 'print(1)'` works.
* most imports work.
* it works only inside the Fil-C checkout.
* it requires `/opt/fil`.
* it accidentally uses glibc.
* it requires a full Fil-C source clone in python-build CI.
* the GitHub workflow has merely been written but not run.
* a native extension cannot be built.
* the ordinary builds were broken.
* the final artifact is mislabeled as ordinary musl ABI.
* the regression suite still has unexplained crashes/failures.

Keep debugging and implementing until the actual completion contract is met.

# Final verification and handoff

When everything works:

1. Make coherent commits in `python-build`.
2. If Fil-C changed, make coherent commits in `~/d/fil-c` and push the dedicated branch/fork.
3. If Fil-C changed, publish the compact x86_64 musl Pizfix toolchain binary used by CI and pin its immutable digest in python-build.
4. Push python-build changes.
5. Dispatch the real build/release workflow.
6. Follow it to completion.
7. Fix any CI-only problems and rerun until green.
8. Inspect the produced Fil-C release archive itself, not an intermediate tree.
9. Run the final smoke/relocation/native-extension checks against those exact release bytes.

Only then report completion.

The final report should be concise and factual:

* python-build commit
* Fil-C commit/fork/tag if changed
* Fil-C toolchain artifact/digest
* final CPython Fil-C release asset name
* CI run and status
* CPython regression-suite result and any narrowly justified exclusions
* native-extension result
* relocation result
* memory-safety trap result
* any deliberate differences from the ordinary Linux musl build

Do the work now and continue autonomously until this state is reached.
