# Bounded one-shot zlib routing, 2026-09-25

**Recommendation: keep the 8 KiB route as an opt-in measurement candidate; do
not promote it without paired quiet-host results.** The separate
`--zlib-adaptive` mode sends public `zlib.decompress` inputs of at least 8192
compressed bytes to the existing prefixed zlib-rs backend. It sends shorter
inputs and all persistent streams to platform zlib. The original
`--zlib-oneshot` remains available. Selection happens before stream
initialization, so initialization, inflate, and end use the same backend.

## Why this cutoff is only a tradeoff

[`zlib_oneshot_block_classes.py`](zlib_oneshot_block_classes.py) regenerated
all deterministic SQLite payloads and read both fixed 1 MiB zlib streams from
the checked-in workload. It validated each zlib header and decoded content,
then classified the first DEFLATE block. [Compact data](data/zlib-oneshot-block-classes-20260925.json)
records exact source hashes, host zlib identity, class counts, stream lengths,
and the route selected by the proposed cutoff. Run it from the repository
root with `python3 rust-cpython/experiments/zlib_oneshot_block_classes.py`.
The class inspection is diagnostic and carries no timing claim.

| Input | First block | Compressed bytes | 8 KiB route |
| --- | --- | ---: | --- |
| Winning 1 MiB compressible | Dynamic | 1,040 | Platform |
| Winning 1 MiB incompressible | Stored | 1,048,667 | Rust |
| Winning small SQLite BLOBs | 256 fixed | 190–219 | Platform |
| Regressing mixed SQLite BLOBs | 170 stored/dynamic, 86 fixed | 51–4,101 | Platform |

The first-block type alone cannot split wins from regressions: dynamic and
stored blocks occur on both sides. The cutoff routes all mixed SQLite fixture
streams to platform zlib, but it
also gives up the measured small-BLOB gain and the Rust gain for the highly
compressible 1 MiB stream. The published 38.4% CPU reduction for
`zlib_decode_1m` combines that stream with the incompressible one; it cannot
predict the new mode's aggregate gain. The 8 KiB boundary comes from the
observed 4,101-byte fixture maximum with room above it. Other data
distributions can cross it differently, and the function-pointer dispatch
may add function-pointer dispatch cost.

## Exact source and build recipe

Patch `0011-zlib-adaptive-oneshot.patch` has SHA-256
`b3c63c08a48305a62c8d34f51a26ef9405fec4391f15657fb402600321a9fca1`.
The manifest selects it after patches 0001, 0002, and 0003 only for
`--zlib-adaptive`. The optional backend remains pinned to zlib-rs 0.6.7 with
the `python_build_rs_` symbol prefix, and C compilation defines both
`PYTHON_BUILD_ZLIB_ONESHOT=1` and `PYTHON_BUILD_ZLIB_ADAPTIVE=1`. It links
platform libz and the prefixed Rust static archive. No new dependency or
production build path is involved.

A fresh verified extraction of source commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b` selected exactly 0001,
0002, 0003, and 0011. Each patch passed the controller's forward and reverse
application checks. `Modules/zlibmodule.c` changed from SHA-256
`36390fc1b0bdaf7da332d732c67cbe9669bd3f6e923a3e5810b4662159a0e20c`
to `8bcd620f2f12e826f0cc2b28639541ec3452e0220fc2dccd84c196c21c07534d`.
The fresh source contains the 8192-byte route. This selection check ran
before any build.

[`zlib_adaptive_patch_selection.py`](zlib_adaptive_patch_selection.py) also
extracted fresh verified trees for default, adaptive-only, and adaptive plus
all seven other optional modes. The `patch_selection` section of the
[combined evidence](data/zlib-adaptive-20260925.json)
records 8, 8, and 26 changed paths respectively; every intended path changed
and every selected patch passed forward and reverse checks. The adaptive
`zlibmodule.c` hash was the same in both adaptive compositions. The C wrapper
also compiled successfully in the full build, confirming that the SDK
`inflateInit2` macro expands to the selected four-argument function pointer.

## Native builds and installed identity

The candidate command was
`/usr/bin/time -l -p python3.14 rust-cpython/build.py build --variant zlib-adaptive --zlib-adaptive`.
The matched control command omitted `--zlib-adaptive` and used
`--variant zlib-adaptive-control`. Both used the same source commit, locked
LLVM 23.1.2, nightly Rust, `--with-lto=thin`, and native PGO task
`-m test --pgo -j 9`, with separate profile runs. The control has patches
0001–0003, which are inactive for zlib without a candidate flag; the
candidate adds 0011. Full command logs remain under ignored lane logs.
The `adaptive_build` and `platform_build` sections of the combined evidence
contain the exact flags, source hashes, installed hashes, and resource totals.

| Build | Elapsed | Kernel user + system | Peak reported RSS | Peak reported footprint | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Adaptive | 300.86 s | 703.28 + 109.88 s | 1,791,049,728 B | 54,968,824 B | 0 |
| Platform control | 281.08 s | 702.20 + 109.67 s | 1,801,043,968 B | 35,193,336 B | 0 |

`/usr/bin/time -l` covered the controller's waited build children. Its RSS
field is the largest reported process peak, not simultaneous tree memory;
the footprint field is macOS charged memory. Process count was not sampled.
Host swap remained 243.88 MiB before and after both builds. The build-time
differences are not workload speed or memory evidence.

The installed adaptive `zlib` extension SHA-256 is
`d09e1617974e142622921c2467257e865540115585d593f51845bfd4a9899403`
and its unstripped size is 1,676,264 bytes. It defines prefixed Rust
init/inflate/end symbols, retains platform inflate imports, and reports
platform zlib runtime 1.2.12. The matched platform extension SHA-256 is
`359af23cdd83e750663722b579652c36e0fef417c85f04b96e05bd35fe671bf6`
and its size is 82,808 bytes. The adaptive source wrapper hash after build
matches the fresh extraction check above. The build controller's installed
round-trip and symbol checks passed; the broad test command was not run.

## Output identity and loaded-host diagnostic

One complete output-identity pass in the `output_identity` section
used the installed adaptive stage and a pinned-fork platform-zlib stage for
each checked-in 1 MiB direct decode, small SQLite BLOB, and mixed SQLite BLOB
task. Each control/candidate output matched in full apart from each task's
internal elapsed field. The SQLite fixtures matched their earlier SHA-256
values. The first attempt invoked `benchmarks/workloads/zlib.py` directly,
which shadowed the stdlib `zlib` extension during import; the corrected
invocation used `-m benchmarks.workloads.zlib`. The failed attempt's resource
record and exception are in the compact identity data. Two seed attempts
preceding that failure (`identity-invocation-1-seed-smallblobs` and
`identity-invocation-1-seed-mixedblobs`) had their logs overwritten by the
corrected pass. Their process resources are missing, so no complete lane
resource total is claimed.

A new same-branch platform control was then built, avoiding the older stage's
different patch ancestry. The `loaded_pairs` section of the combined evidence
contains all 32 complete workload processes: three nearby control/control
pairs and five alternating adaptive/platform pairs per task. Each process
used the same absent no-write bytecode-cache prefix. All decoded digests
matched, every recorded process had zero swaps, and host swap stayed at
243.88 MiB. No sampler ran during these timings.

| Complete task | Adaptive paired wall change | Adaptive paired kernel CPU change | Nearby control/control wall range |
| --- | ---: | ---: | ---: |
| `zlib_decode_1m`, 1,707 iterations | −6.59% median (−6.59% to −1.10%) | −6.74% median (−7.78% to −3.37%) | −0.02 to +0.01 s |
| Mixed SQLite, 604 scans | 0.00% median (0.00% to +0.96%) | 0.00% median (0.00% to +0.98%) | 0.00 s |

These measurements were taken while an unrelated container remained active;
`/usr/bin/time -p` rounds both wall and CPU to 0.01 seconds, so the five
paired ratios are quantized. Distinct PGO profiles further limit fine
differences. The direct-decode direction is encouraging, and the mixed BLOB
regression did not recur in this diagnostic. **Keep the mode opt-in and defer
the speed and memory verdict to quiet-host serial pairs**, including the
highly compressible small SQLite task that this cutoff deliberately sends
back to platform zlib.
