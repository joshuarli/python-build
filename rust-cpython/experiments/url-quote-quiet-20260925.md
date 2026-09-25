# Revised URL quote guard: bounded host diagnostic, 2026-09-25

## Verdict

**Loaded-host diagnostic; no publishable speed claim.** The exact revised
`0001-rust-url-quote.patch` is directionally faster on `catalog_search_form`
and slower on `catalog_request_path` when compared with the pinned pure parser
on the same CPython 3.16 executable. The request-path CPU regression is larger
than the measured same-side noise and should inform the default-route decision.
The workload is an overlay of source compiled on each fresh import, not an
installed patched CPython build. OrbStack Helper was active throughout, so a
quiet-host integrated decision remains open.

## Source and build identity

The current patch is SHA-256
`8117e87d51a91dd362d5c315f3eae552ac1144b83f43dae1980423c320b618ad`.
Its parser hunk applied without fuzz to a fresh copy of pinned commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b`'s `Lib/urllib/parse.py`.
The candidate parser SHA-256 is
`f2949f2bfd61891f33a9e79168f1c188587b374985ebb3faa04a476202b280f2`;
the pure installed parser and control overlay both hash to
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`.
The executable SHA-256 is
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`.

The patch's exact new C and Rust files were compiled into a private extension
using nightly Rust `2026-09-15` (`--edition=2024 --crate-type=staticlib -C
opt-level=3 -C panic=abort --target=aarch64-apple-darwin`) and the locked LLVM
23.1.2 `clang` (`-O3 -fPIC -mcpu=apple-m1 -mmacosx-version-min=26.0`, Xcode
26.5 SDK, stage Python 3.16 headers). The link used `-bundle -undefined
dynamic_lookup` with the same deployment floor and SDK. The C and Rust source
hashes are `727e5b12a8a2e0b8a81be59b86ccb5252f88b1f66c64ca1cbc05ec71448f44df`
and `bb9156522ea47140e52e309b501ee3222ed5466fb8b33a779a31566e184fad8c`.
The extension hash is
`b1ab627f758d778087fb2c8e8e8df0835396e9b9c8d3db45550c7ca74710d617`;
`otool -L` shows only `/usr/lib/libSystem.B.dylib`. An import probe resolved
the candidate overlay and private extension paths and returned `x%20y` for
`quote_from_bytes(b"x y")`.

The exact argv and every build attempt are in
`data/url-quote-quiet-build-20260925.json`. The final direct-compiler Rust
compile used 0.043 user plus 0.021 system CPU seconds and peaked at about 101 MB
RSS; C compile used 0.054 plus 0.075 seconds and peaked at 54 MB; final link
used about 0.070 plus 0.102 seconds and peaked at 36 MB. Each reported zero
swaps. The first Rust invocation went through `rustup`; its direct-child
`wait4` accounting does not include the Rust compiler, so a direct-compiler
rebuild supplies the usable CPU observation. An intermediate replay had a
mistyped LLVM path and failed before spawning the linker; its immediately
preceding Rust compile completed but lost its resource record. Both facts are
retained in the build data. The final extension hash matched the originally
measured bytes exactly.

## Workload observations

The runner is `url-quote-quiet-20260925.py`, with all 32 attempts and host
snapshots in `data/url-quote-quiet-20260925.json`. Each attempt used
`stage/bin/python3.16 -B -m benchmarks.workloads.catalog_url_breadth TASK
--iterations N`, with `PYTHONPATH=SIDE:NATIVE:ROOT`,
`PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=1`. Neither overlay had a
bytecode cache. Search used 500 iterations and request path used 1,000.
Both arms exposed the same extension path through `PYTHONPATH`; the pure parser
did not import it. `os.wait4` measured direct-child kernel user/system CPU,
peak RSS, and swaps. The workload creates no children. Monotonic wall includes
an in-run host sample with `ps`, `sysctl`, and `vm_stat`; the sample itself can
affect wall time. Host CPU, load, memory pages, and swap were recorded before
and during each attempt. The external `ps` RSS snapshot is not a physical or
unique footprint measurement.

All 32 attempts returned input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`.
Search output digest was
`a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22`;
request-path output digest was
`52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff`.
Four control/candidate pairs per task alternated order. Two control/control
and two candidate/candidate pairs per task measured local noise.

| Task | Candidate/control paired wall ratios | Candidate/control paired CPU ratios | Median CPU ms/workload iteration, control → candidate | Paired peak RSS difference, MB, candidate − control |
| --- | --- | --- | --- | --- |
| Search form | 0.898, 0.953, 0.975, 0.961 (median 0.957) | 0.943, 0.958, 0.975, 0.961 (median 0.959) | 1.812 → 1.742 | +0.311, −0.410, +0.524, +0.459 |
| Request path | 1.092, 1.078, 1.087, 1.060 (median 1.083) | 1.090, 1.079, 1.087, 1.075 (median 1.083) | 0.245 → 0.266 | +0.180, +0.164, +0.016, −0.115 |

Same-side CPU ratio medians were 1.003 for search control/control, 0.988 for
search candidate/candidate, 1.008 for path control/control, and 1.019 for path
candidate/candidate. Same-side wall ratio medians were respectively 1.001,
0.987, 1.011, and 1.027. The peak RSS differences change sign within both
tasks and are small relative to the 34 MB process, so there is no clear RSS
direction. All workload `ru_nswap` counts were zero. A distinct physical or
unique-footprint estimate was unavailable from the local `ps` fields; no
footprint claim is made.

The one-minute host load was 3.95 initially and 3.56 finally, ranging
3.52–3.95 across per-attempt snapshots. OrbStack Helper was the highest CPU
process in those snapshots, about 10–59% before attempts and 11–39% during
attempts, with 76% in the initial snapshot. Host swap used stayed at 243.88
MiB. These conditions and the source-only overlay limit the result to a
diagnostic. No further timing was started after this bounded run.

No tests, formatters, linters, hooks, dependencies, or commits were run or
added. The primary checkout stage and pinned source were read only.
