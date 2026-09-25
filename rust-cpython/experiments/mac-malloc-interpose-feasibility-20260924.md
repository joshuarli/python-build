# macOS native malloc interposition feasibility (2026-09-24)

## Verdict

**Keep as an experiment-only diagnostic; the allocation benchmark gate remains unavailable.** A small `DYLD_INSERT_LIBRARIES` observer on the local, ad-hoc-signed CPython 3.16 stage captured exact requested sizes for seven parent `malloc(65537)` calls and nine spawn-child `malloc(73729)` calls. It also wrote a separate exit record for multiprocessing's resource-tracker interpreter. A four-thread probe captured 400 of 400 controlled `malloc(65537)` calls without a hang. This establishes that dyld injection, symbol replacement, per-PID accounting, and ordinary spawn/exec propagation work for these local fixtures.

The observer counts successful calls resolved through the three replaced symbols (`malloc`, `calloc`, `realloc`). It does not prove complete native allocation coverage: direct malloc-zone calls, other allocation APIs, anonymous mappings, failed requests, and abnormal exits can escape. Per-process totals contain interpreter startup and shutdown activity, with no workload phase boundary. The probe does not establish reliable per-operation totals for general workloads, whole-tree completeness, or comparable overhead. Python RAW/MEM/OBJ allocator-domain counts remain a separate later layer and must never be added to these system counts.

## Interface and security boundary

The installed `dyld(1)` manual documents `DYLD_INSERT_LIBRARIES` and says dyld ignores its environment variables for System Integrity Protection (SIP) protected executables when SIP is enabled. SIP is enabled on this host. The SDK's `mach-o/loader.h` defines `S_INTERPOSING` as pairs of replacement and replaced function pointers. The compiled dylib has a `__DATA_CONST,__interpose` section, and the controlled calls demonstrate its effect. The stage executable is ad-hoc, linker signed (`codesign` flags `0x20002`) without a hardened-runtime flag; this local success does not establish injection into protected or hardened executables or every subprocess. `DYLD_INSERT_LIBRARIES` and the output-prefix variable were set inside a single shell for each probe, after `/usr/bin/time` and `gtimeout` launched; they were not set globally.

The observer in `mac-malloc-interpose-probe/observer.c` uses atomic counters and calls the original allocator functions from its interposing image. Its allocation callbacks do no file I/O or formatting. A constructor copies the output prefix. A normal-exit destructor writes one `O_EXCL` JSON file per PID; the file is not a crash-safe journal. The sentinel fields count *malloc* requests only. `calloc` records successful product bytes when representable; `realloc` records successful requested bytes. These are requests, not live bytes or allocator usable sizes. The counters can include calls made before the constructor, and the destructor excludes calls made during its own reporting. A plain fork without exec would inherit counters; this probe covered spawn/exec only.

## Controlled evidence

Host: Apple Silicon, macOS 26.5.2, Xcode 26.6. The read-only interpreter was `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`, SHA-256 `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`. The existing fixture was `mac-allocation-probe-20260924.py`, SHA-256 `fa49f92ffb5d7bd99597de1d1f755ecbaa881e7c194921aef4a1dbbdd5e68c38`. It prints role/PID markers, joins the spawn child, and makes 7 × 65,537-byte parent requests and 9 × 73,729-byte child requests. The controlled requested-byte sum is 1,122,320. Other Python and system allocation activity is expected.

The final observer build used `xcrun clang -arch arm64 -O2 -std=c11 -dynamiclib`. The final fixture run used `/usr/bin/time -l gtimeout -k 2s 30s /bin/zsh -c 'export DYLD_INSERT_LIBRARIES=...; export PYTHON_BUILD_MALLOC_OBSERVER_PREFIX=...; exec <stage>/bin/python3.16 <fixture>'`. Each process inherited the dyld setting through its own interpreter exec. A first run of the same fixture with the initial observer also produced the expected sentinel counts; the final source narrows the sentinel to `malloc` alone.

| Final fixture record | PID | Parent PID in exit record | `malloc(65537)` | `malloc(73729)` | All `malloc` calls | All requested `malloc` bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Parent | 90304 | 90301 | 7 | 0 | 4,774 | 19,652,606 |
| Spawn child | 90384 | 90304 | 0 | 9 | 4,914 | 19,769,557 |
| Resource tracker | 90383 | 1 | 0 | 0 | 3,961 | 16,732,830 |

The resource tracker's parent PID was 1 when its destructor ran, after the fixture parent exited; its own PID was distinct and its JSON file was present. The parent and child marker PIDs matched their files. This is complete for the three observed interpreter processes in this fixture, not a proof that every process in an arbitrary tree will write a file. An exec of a SIP protected executable, a process that clears the environment, `_exit`, a signal, or a crash can leave a gap.

The ignored `thread_probe.py` created four threads, each making and freeing 100 `malloc(65537)` requests through `ctypes`. Its sole PID 93150 wrote `size_65537=400` on normal exit. The probe exercised concurrent increments and the normal-exit path. It did not exercise allocator failure, `realloc` size zero, thread termination races, or heavy recursive allocator paths.

## Resource bounds and overhead

All substantial commands were wrapped in `/usr/bin/time -l`; runtime commands had a 30-second hard timeout and two-second kill grace. No timeout fired. The final instrumented fixture was 1.19 s elapsed, 0.09 user + 0.05 system CPU seconds, 29,163,520-byte maximum RSS, zero swaps. A single uninstrumented run was 1.17 s elapsed, 0.08 user + 0.04 system CPU seconds, 28,999,680-byte maximum RSS, zero swaps. The instrumented four-thread probe was 0.05 s elapsed, 0.01 user + 0.01 system CPU seconds, 17,825,792-byte maximum RSS, zero swaps. Two dylib compilations each used at most 0.21 CPU seconds and peaked near 53 MiB RSS. All measured commands together used far less than 120 CPU seconds and 1 GiB maximum reported RSS. The small paired timing difference is an overhead signal only; one pair cannot bound host noise, and `time -l` around the timeout process does not independently establish complete CPU/RSS accounting for every short-lived interpreter descendant. No speed comparison is claimed.

Raw dylib, thread script, and per-PID JSON files are retained under ignored `rust-cpython/work/mac-malloc-interpose-20260924z/` in this worktree. No stage, production build, test, benchmark harness, dependency, pin, or system setting was changed.

## Next boundary

A later [bounded phase experiment](mac-malloc-phase-20260925.md) added one
explicit phase per PID and confirmed startup and post-phase sentinel requests
are excluded in a parent, spawn child, and threaded batch. Before using this
as a general diagnostic allocation pass, add explicit process discovery and a
required exit record for every interpreter. Check symbol/API coverage against
direct zone and anonymous-VM paths and validate overflow, failure, and
termination semantics. Measure observer perturbation with repeat
self-comparisons. A separate CPython RAW/MEM/OBJ observer would need its own
early-install and correctness evidence; its counts overlap underlying system
requests and remain separate.
