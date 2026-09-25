# Complete source TAR rewrite, 2026-09-25

**Keep the TAR-owned checksum module as an opt-in speed candidate.** The checked-in [workload](source_tar_rewrite.py) streams the locked CPython source `.tar.gz` through public `tarfile.open(..., "r|gz")`, copies every member and regular payload through `TarFile.addfile` into deterministic uncompressed `w|` TAR output, and hashes the result. Every measured run verified the locked input fingerprint, all 6,539 members, 6,031 regular files, 136,064,031 regular-file bytes, and source metadata/content digest `4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805`. All 12 runs produced the same 147,763,200-byte output with SHA-256 `8026bc5b211c69b1d7cda5a929b506cb7bf61d70290a3dfa5e51d275c4f85efd`.

The existing quote-only control was `/Users/josh/d/python-build-exp-merged-macos-url-20260925/rust-cpython/stage-quote-only`; the TAR-owned candidate was this worktree's `rust-cpython/stage-tar-owned`. The input was the pinned `.cache/objects/965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467.blob`. The output path was the ignored, reusable `rust-cpython/work/tar-rewrite/output.tar`. `PYTHONPYCACHEPREFIX` selected an empty ignored directory and `PYTHONDONTWRITEBYTECODE=1` prevented cache writes. Separate verbose imports showed `tarfile.py` loaded from source on both sides. The stages are independently PGO-built, so their profile and machine-code differences limit exact attribution.

One serial control/control calibration pair had external wall times 0.897 and 0.873 s, a 2.6% spread. Five alternating control/candidate pairs followed on the quiet host:

| Complete rewrite process | Quote-only median | TAR-owned median | Median paired change |
| --- | ---: | ---: | ---: |
| External wall | 0.864 s | 0.761 s | −11.87% (pair range −14.08% to −11.01%) |
| Kernel user + system CPU | 0.83 s | 0.73 s | −12.05% |
| Peak resident | 43,532,288 B | 43,483,136 B | Mixed pair directions |
| Peak footprint | 30,786,040 B | 30,753,272 B | Mixed pair directions |

All attempts reported zero swaps; host swap allocation stayed at 243.88 MiB. The [compact observations](data/source-tar-rewrite-20260925.json) retain each attempt's external wall, kernel user/system CPU, RSS, footprint, swaps, output identity and counts, paired order, stage/source/script hashes, and the shared command and environment. `/usr/bin/time -l -p` measured each direct interpreter; `perf_counter` independently measured external wall. Maximum resident and footprint are lifetime high-water marks. There was no process sampler or qualified unique/proportional-memory measurement. No build, test suite, dependency, formatter, linter, hook, or remote action was part of this breadth pass.
