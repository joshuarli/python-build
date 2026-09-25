# Current optional IPv4 guard: bounded measurement, 2026-09-25

**Verdict: inconclusive for adoption.** The exact current optional `0006-rust-ipv4-scan.patch` parser hunk and private C/Rust extension were measured against the pure pinned `ipaddress.py` source on the same accepted, read-only CPython 3.16 executable. Five serial counterbalanced routing pairs show a median guarded/pure wall ratio of **0.917** (about 8.3% faster) and kernel CPU ratio of **0.922** (about 7.8% less CPU). Host load was 6.55–6.65 during timing, and this was one short diagnostic. The earlier roughly 9.8% complete-routing gain belongs to a prior patch and is not assigned to this revision.

## Source and setup

The pure parser was fetched from immutable Rust-for-CPython commit `b812b4a7b9efaca46b98544a8633b7d7e454166b` and matched the accepted stage's installed parser byte for byte (SHA-256 `6e800cb5727ac9ea045d406873a7dfb37f1be01ef5a8a1df52d6399635995a79`). The current patch SHA-256 was `83d6529503188ce9144b90f853b684187867d07ee1a23ff29af678d142fbce70`; the patched parser was `0fb3286efaef72a5808dff5e3583075f5f2c2692508db0d727a8aa32220c8607`. The accepted executable was `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`; both arms used that exact file. The standalone extension's initial hash was `055b0d45bdf1046aa899406a5b97766df5e637f0d093f0afc7d8c2f577ee62b8`.

`ipv4-current-guard-measure-20260925.py` extracts the exact `module.c` and `scan.rs` new-file hunks, applies only the exact parser hunk to an isolated source overlay, and records direct compiler commands and source hashes in the JSON. The extension-use probe confirmed that a canonical IPv4 address loads the private extension only in the guarded arm. Both arms used `-S -B`, `PYTHONDONTWRITEBYTECODE=1`, an empty `PYTHONPYCACHEPREFIX`, and `PYTHONPATH` overlays with no `.pyc`. The workload was `ipaddress_v4_workload.py --count 30000 --rounds 2`; every run produced digest `71b21698342ecd72171e968712cf7218d0272ea3cbc856e94797a428a0218180` and the same complete JSON output.

## Observations

| Measure | Guarded / pure or guard minus pure | Same-side range |
| --- | ---: | ---: |
| Complete-routing wall time, five pairs | Median 0.917; range 0.914–0.936 | Pure 0.999–1.009; guard 0.998–1.005 |
| Complete-routing kernel user + system CPU | Median 0.922; range 0.915–0.934 | Pure 1.003–1.004; guard 0.990–1.000 |
| Separate physical footprint, three pairs | Guard +294,912 to +655,360 bytes; median +442,344 bytes | No same-side footprint calibration |

The five comparison runs per arm had median wall times of 0.808 s pure and 0.742 s guarded per 60,000 routing rows; median CPU was 0.796 s pure and 0.732 s guarded. The separate memory pass used `/usr/bin/time -l -p` for child peak RSS, physical footprint, swaps and kernel CPU; swaps were zero. Initial compiler `wait4` observations and later `/usr/bin/time` direct-compiler observations, including resource costs and distinct failure-free attempts, are in the JSON. The direct pinned Rust compiler and LLVM clang were each run once more with unique output paths so the compiler accounting excludes `rustup` launcher ambiguity. Compiler output byte hashes vary across output names; the source and commands are recorded. The compiler process count beyond the direct child was not observed, so no total process-count claim is made.

Host swap usage stayed at 243.88 MiB. This short high-load sample supports further evaluation of this current guard but cannot establish a publishable speed or footprint claim. No full PGO build, tests, formatters, linters, hooks, dependency changes, or commit were performed. Raw attempts and the reproducible runner are retained beside this report.
