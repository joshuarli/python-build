# TAR-owned private checksum module, 2026-09-25

**Keep as an opt-in macOS experiment.** `build --tar-checksum` now adds `_rust_tar_checksum`, a private C extension linked to a separate `no_std` Rust scanner. The default selection remains patches 0001–0003; `--url-unquote` and `--tar-checksum` apply together. Fresh extractions of the pinned source verified the changed paths for all three selections before the build. The installed `tarfile.py` matches the patched source SHA-256 `4a695c4430e3c4792085a4f2ecbdfa27afe2f61ea5161ced827d1a3e648b8442`. `nm` found `PyInit__rust_tar_checksum` and `tar_checksum_scan` in the installed extension. The TAR patch no longer changes `_rust_url_quote`.

`calc_chksums` uses the Rust scanner only for built-in `bytes` of exactly 512 bytes while its captured `struct.unpack_from` and `sum` helpers retain their identities. The extension loads on the first eligible call. Other inputs and helper replacements made **after** `tarfile` imports take the original two unpack/sum expressions. A helper replaced **before** `tarfile` imports becomes the captured reference, so an exact header can bypass it; this remains an observable difference. A custom importer or `sys.modules` replacement can also observe the new lazy import. Those cases require a stronger contract decision before broader acceptance.

The native Apple Silicon build used source archive SHA-256 `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`, locked LLVM 23.1.2, nightly Rust 2026-09-15, ThinLTO, and CPython PGO (`-m test --pgo -j 9`). It completed in **258.17 s wall**, **700.22 s user + 105.87 s system CPU**, **1,769,947,136 B peak resident**, **38,699,512 B peak footprint**, and zero reported swaps. This is a complete independent build, so its time is not an incremental cost of the TAR module.

Five alternating pairs ran `bin/python3.16 rust-cpython/experiments/source_tar_hybrid.py <locked archive> --loops 3` serially against the existing quote-only stage. Each process read all 6,539 archive members and streamed 6,031 regular files (136,064,031 bytes) three times. Every output digest was `4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805`. Both installed interpreters were built separately with PGO, so their profile and machine-code differences limit attribution of the speed change to this patch alone.

| Three-pass process | Quote-only median | TAR-owned median | Median paired change |
| --- | ---: | ---: | ---: |
| External wall | 1.1440 s | 1.0389 s | −9.24% (pair range −11.25% to −8.35%) |
| Kernel user CPU | 1.09 s | 0.99 s | −9.17% |
| Peak resident | 46,809,088 B | 46,546,944 B | Mixed pair directions |

Five paired cold `import tarfile` runs used the same source-only cache policy. Both sides loaded `tarfile.py` from source and left `_rust_tar_checksum` and `_rust_url_quote` absent from `sys.modules`. Candidate median external wall was 0.1040 s versus 0.1087 s control, with paired changes ranging from −6.72% to +0.93%; this does not establish a cold-import speed or memory effect. The candidate's lazy import inside each eligible checksum did not erase the complete archive gain in these runs.

The [compact data](data/tar-owned-module-20260925.json) records the build, every benchmark attempt, source/build/stage hashes, paired order, resource fields, swap state, and a failed patch-application attempt during authoring. `/usr/bin/time -l -p` provided process-tree kernel CPU, maximum resident, footprint, and swaps; `perf_counter` independently measured external wall. No process sampler, aggregate simultaneous RSS, process count, or unique/proportional memory measurement was collected. No CPython tests or Linux build ran under this lane's instructions.
