# macOS malloc phase boundary diagnostic (2026-09-25)

## Verdict

Keep the phase boundary as an experiment-only diagnostic. The observer now exposes one `malloc_observer_phase_begin()` / `malloc_observer_phase_end()` pair per PID. A spin lock orders each phase transition with successful allocation-return accounting; allocation callbacks do not allocate, format, or perform I/O. Each callback invokes the original allocator before acquiring the lock, then checks the phase state and increments while holding it, before returning to its caller. A call racing with begin or end falls on the side determined by lock acquisition, even if the original allocator began earlier. The fixture starts its phase after interpreter startup and ends after worker threads join, so its startup and post-phase sentinel requests are excluded. This does not qualify a general allocation benchmark.

The exact interposed APIs are `malloc`, `calloc`, and `realloc` calls routed through dyld's three symbol replacements. `malloc` records requested bytes; `calloc` records the product when representable; `realloc` records the requested new size. The sentinel counts apply only to `malloc`. Direct malloc-zone calls, aligned/other allocator APIs, anonymous VM mappings, Python allocator-domain requests, failed requests, and allocations whose calls bypass these replaced symbols are not covered. Counters can wrap at 64 bits. A callback interrupted by an allocating signal handler while holding the spin lock, a plain fork inheriting a locked state, or an abnormal exit can lose or hang reporting. Exit files are written only by the normal destructor. The output is therefore not crash safe or a complete process-tree census.

## Recipe and identities

Native Apple Silicon, macOS 26.5.2. The read-only interpreter was `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16` (Mach-O arm64, SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`). The earlier report's `/private/tmp/.../python3.16` stage no longer existed; the current stage was found before compiling. No production source, stage, dependency, or system setting changed.

Final source SHA-256: `observer.c` `b05bccbbfcf6982adbc2eecfff5410b317dbec0a9890f47f4b13b53104338cf9`; `phase_fixture.py` `c4372550194004c6c240a4f97c838d0522649836deb11554ed024a06294b79f7`. Compile with `xcrun clang -arch arm64 -O2 -std=c11 -dynamiclib rust-cpython/experiments/mac-malloc-interpose-probe/observer.c -o rust-cpython/work/mac-malloc-phase-20260925/observer.dylib`. The ignored dylib SHA-256 was `7daf8e8351574cbbd3f3757e18395c88d479c051b6371308c68c148a61a21536`.

For each run, `/usr/bin/time -l` wrapped `gtimeout -k 2s 15s /bin/zsh -c 'export DYLD_INSERT_LIBRARIES=<absolute observer.dylib>; export PYTHON_BUILD_MALLOC_OBSERVER_PREFIX=<absolute ignored work prefix>; exec <absolute interpreter> <absolute phase_fixture.py>'`. The two variables were confined to that shell and its spawned interpreters. The fixture loads the observer and libc before beginning the phase, makes three sentinel requests before, the controlled batch during, and three after; the parent uses four threads for 40 of its 47 in-phase requests. It spawns one child using Python's `spawn` context. All requests are freed. The parent joins the child with a ten-second limit. No test suite was run.

## Observations

| Attempt | Fixture source | Outcome | Elapsed s | Wrapper user/system s | Wrapper peak RSS bytes | Swap events |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| P1 | `6c972319bb660e8d68b7bb3097caf5c79d0a9b1ab16315b465c184cb17f2bdad` | pass; no per-PID usage markers yet | 0.31 | 0.07 / 0.07 | 22,904,832 | 0 |
| P2 | final hash above | pass | 0.13 | 0.06 / 0.04 | 23,478,272 | 0 |

The compile took 0.19 s elapsed, 0.06 user + 0.07 system CPU seconds, peak RSS 53,657,600 bytes, zero swaps. `time -l` reports the wrapped command's kernel usage; its peak RSS is not the sum of concurrently resident processes. The fixture's `getrusage(RUSAGE_SELF)` markers separately report P2 parent 0.019500 user + 0.015176 system CPU seconds, peak RSS 20,283,392 bytes; child 0.029373 user + 0.017853 system, peak RSS 23,478,272 bytes. Markers precede interpreter shutdown, so those per-PID values omit later activity. The resource tracker did not emit a usage marker. Both runtime attempts and compilation together were under one CPU second and 54 MiB peak observed RSS, well below the 30 CPU-second and 512 MiB bounds. OrbStack was consuming CPU during the run, so elapsed times have no performance meaning.

P2 stdout reported `START pid=54000`, `MARK role=parent pid=54000 size=65537 expected=47`, and `MARK role=child pid=54011 size=73729 expected=9`. Normal-exit JSON records were:

| PID / role | Parent PID at exit | Phase state | `malloc` calls / requested bytes | `calloc` calls / requested bytes | `realloc` calls / requested bytes | 65,537 / 73,729 sentinels |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 54000 parent | 53997 | 2 | 63 / 3,082,799 | 8 / 4,640 | 0 / 0 | 47 / 0 |
| 54011 child | 54000 | 2 | 9 / 663,561 | 0 / 0 | 0 / 0 | 0 / 9 |
| 54010 resource tracker | 1 | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

State 0 means no phase began; state 2 means the phase ended. P1 produced the same three role/state/sentinel outcomes with PIDs 50676, 50699, and 50697 respectively; its parent had 63 `malloc` calls / 3,082,799 bytes and child 9 / 663,561 bytes. The controlled in-phase sentinel requested bytes were `47 * 65537 + 9 * 73729 = 3,743,800`; unrelated in-phase requests account for the other recorded bytes. Six out-of-phase requests per participating process did not enter sentinel counts.

P2 output SHA-256 identities: stdout `50ebc0b3a7b3c687eb9580beed750e336a2500597d3177e36134971fa828c904`; time stderr `7ef5b891a1d6635b5a84f736a83f7e4f8a578bd119d514ad17d2807ba525be3e`; parent JSON `2ccf40f6534e1f9b018a53e0eeb84e7825d82a4dd61a20d78eb527d62ba4b143`; child JSON `7fc8717d133820359a8df49e1408c5a82fd5496eb61270c5e2ff0b226a0cd6e6`; resource-tracker JSON `aa0d9ed30d4c10fe28ae477f93eeeabc8126bbf573a869bd37322f2e0e29d7be`.

No run failed. P1 was superseded solely to add per-interpreter resource markers. The observed three exit records match the three known interpreter processes in this fixture; arbitrary subprocess discovery and required exit-record completeness remain unproven. The lock and observer overhead were not measured in quiet paired self-comparisons. These counts cannot be combined with Python-domain counters or used as a speed result.
