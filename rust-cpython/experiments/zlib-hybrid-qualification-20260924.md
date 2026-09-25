# Hybrid zlib inflate qualification, 2026-09-24

**Recommendation: stop work on this optional hybrid and retain it as a correctness candidate, without promotion.** All measured workloads produced identical input and output digests. The inner decode and gzip timers show a repeatable hot-path gain, but the matched accepted-fork control did not establish a complete-task speed gain or a stable RSS direction within five paired runs. The hybrid adds 1,592,928 bytes to the installed unstripped `zlib` extension and 1,451,456 bytes after the same copied-artifact debug-strip policy. Compatible USS/PSS and native allocation counts remain unavailable, and the matched upstream resource baseline required by `rust-for-cpython.md` is absent. The measured hot-path gain does not justify that size and qualification cost for this optional candidate.

All 238 successful workload attempts, including each external memory sample, kernel lifetime root peak, `wait4` CPU result, digest, launch order, and unique attempt ID, are retained in [the raw data](data/zlib-hybrid-qualification-20260924.json). The four complete `/usr/bin/time -l` controller records are embedded there. The original attempt files remain in ignored `rust-cpython/results/zlib-hybrid-qualification-20260924/` in this worktree.

## Installed identity and comparison boundary

The original platform control and hybrid installation trees were copied into this isolated lane before measurement. The later accepted-fork control was copied as a separate third tree. `bin/python3.16`, `zlib` extension, `zipfile/__init__.py`, `importlib/__init__.py`, and `urllib/parse.py` hashes match each source tree and its copied counterpart. Every tree has 2,045 relative Python source paths and 6,099 `.pyc` files. The installed cache audit found 2,033 valid checked-hash caches and the same 12 missing source caches in each tree; no stale checked-hash cache was found.

| Tree | `bin/python3.16` SHA-256 | `zlib` extension SHA-256 | `urllib/parse.py` SHA-256 |
| --- | --- | --- | --- |
| Initial platform control | `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd` | `5612288b143dfa1130ef645f54f30cd701c1950419260326950b2a7395d60f07` | differs from accepted fork |
| Accepted-fork platform control | `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6` | `2aef4049da6abe4b4e6725f2f79f692ef8f8b3148aa87903a0d40cdef3ef50bd` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` |
| Hybrid | `c3c5e030b2294d9327c4e0f657b85e84514ff131ce2a4cd90d66985fa9295c12` | `34e0cce48e60c1ba6622b98615a0d239a5e48cbe3cb36a428e65c623b7ba970c` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedc3a44c33cd45c85c3279acee` |

The accepted control and hybrid have identical source bytes except `_sysconfigdata__darwin_darwin.py` and `config-3.16-darwin/python-config.py`, which embed build metadata. The initial platform control also lacks the accepted `_rust_url_quote` path in `urllib/parse.py`; its results are secondary. Replays of all five workload roots on both sides, plus the cold ZIP direct child, showed `urllib.parse` absent from `sys.modules`. The original measured processes were not import-traced, so this is a deterministic-path replay, not a historical trace. Both accepted and hybrid configure logs specify `--enable-optimizations` and `PROFILE_TASK="-m test --pgo -j 9"`; their interpreter hashes differ, and merged profile-data identity was not matched. Separate PGO runs can affect small startup and workload deltas.

Both primary comparisons set `PYTHONPYCACHEPREFIX` to the same nonexistent lane path and `PYTHONDONTWRITEBYTECODE=1`, forcing source compilation with no cache writes. Both interpreters reported that prefix and `sys.dont_write_bytecode=True`; the directory remained absent. `PYTHONHASHSEED=1`, `PYTHONNOUSERSITE=1`, `PYTHONMALLOC=default`, and the same benchmark `PYTHONPATH` were used. The valid-cache ZIP repeats unset `PYTHONPYCACHEPREFIX` and used each tree's audited installed caches. These policies are distinct comparisons.

## Matched accepted-control results

The accepted-fork comparison ran five serial control/control timing pairs, then five counterbalanced control/hybrid timing pairs for each focused workload. The external 10 ms memory sampler ran in a separate five-pair ZIP pass. Values are paired hybrid-minus-control medians. A logical unit is one decoded or extracted byte; the ZIP job reads four wheels, or 8,413,264 extracted bytes. `wait4` user plus system CPU is reported per unit, separately from wall latency.

| Workload | Paired hybrid-minus-control external wall per byte | Paired hybrid-minus-control complete CPU per byte | Paired wall range per job | Control/control wall range per job |
| --- | ---: | ---: | ---: | ---: |
| `zlib_decode_1m` | +0.097 ns | +0.035 ns | −3.235 to +7.791 ms | −3.772 to +2.838 ms |
| `gzip_extract_1m` | +0.290 ns | −0.166 ns | −1.901 to +13.383 ms | −10.742 to +6.770 ms |
| `zip_read_wheel` | −0.292 ns | +0.229 ns | −5.166 to +6.446 ms | −12.712 to +4.300 ms |

The workload also reports an internal `elapsed_seconds` timer around its decode or extraction loop. For each pair, the internal difference is `(hybrid elapsed_seconds − control elapsed_seconds) / operation_count`; the table reports the median of five pair differences, with the control/control second-minus-first range from the same session. One logical unit is one decoded or extracted byte, as above.

| Workload | Paired hybrid-minus-control internal elapsed per byte | Internal control/control range per byte | Median paired internal change |
| --- | ---: | ---: | ---: |
| `zlib_decode_1m` | −0.095 ns | −0.010 to +0.001 ns | −44.8% |
| `gzip_extract_1m` | −0.119 ns | −0.053 to +0.014 ns | −40.0% |
| `zip_read_wheel` | −0.068 ns | −0.113 to +0.077 ns | −10.3% |

All five decode and gzip internal pairs favored the hybrid, beyond the observed self-comparison ranges. The ZIP internal difference stayed within its self range. These timers omit interpreter startup, input fixture creation, imports, digest reporting, and process cleanup. They are useful evidence for the hot decompression path; external wall and complete root-plus-child CPU measure the full task and govern the application-level decision. Separate PGO profiles also limit attribution of small differences between the installed interpreters.

The source-only ZIP memory pass gave a paired median root lifetime peak RSS difference of **+409,600 bytes**, range −3,948,544 to +3,719,168 bytes. The paired root physical-footprint median was +212,992 bytes, range −4,145,152 to +3,522,560. A separate five-pair accepted-control valid-cache ZIP memory repeat gave +1,490,944 bytes root peak RSS, range −2,850,816 to +3,719,168, and +1,310,720 bytes root footprint, range −3,031,040 to +3,538,944. Its uninstrumented timing median was +0.467 ns per extracted byte, with pair range −1.310 to +0.993 ns per byte. The memory passes observed one process, at least 15 samples per attempt, and no sampler errors. These wide, sign-changing ranges do not establish a stable ZIP memory direction.

## Secondary initial-control breadth

The first 128-attempt pass used the original platform control before the closer accepted-fork control became available: five control/control and five control/hybrid timing pairs for all five workloads; five memory pairs for ZIP and three each for decode, gzip, and cold ZIP. `zlib_stream_4k` received timing only. All input/output digests and operation counts matched. The timing medians per byte were −0.041 ns decode, −0.061 ns streaming, +0.065 ns gzip, and +0.539 ns ZIP. The cold ZIP median was +2.211 ms wall and +2.639 ms complete CPU per import, with all five hybrid wall differences positive; the same-session control/control wall range was −2.995 to +4.013 ms per import. Its root `wait4` CPU and the workload's direct reaped-child `RUSAGE_CHILDREN` delta were added exactly once. Each cold job reaped three children; the memory sampler observed up to two concurrent processes because imports were serial. The accepted-control pass did not repeat cold ZIP, so this observation does not establish a hybrid-specific regression.

The initial-control ZIP memory median was +1,474,560 bytes root peak RSS, range −3,031,040 to +3,375,104. Its five-pair valid-cache repeat gave −933,888 bytes, range −2,293,760 to +2,097,152. This reversal is another reason to retain the raw observations without treating the initial tree as the primary control.

## Size, resources, and limits

The accepted control's installed `zlib` extension is 82,760 bytes; the hybrid is 1,675,688 bytes. Copies stripped with the same `/opt/homebrew/opt/llvm/bin/llvm-strip --strip-debug` command are 77,056 and 1,528,512 bytes. This uses Homebrew LLVM 23.1.1 and the product's debug-strip flag, but it is a size diagnostic on copies, not the locked LLVM 23.1.2 packaging and re-signing path.

Four `/usr/bin/time -l` controller commands used 50.48 total kernel-accounted user+system CPU seconds, with a maximum reported controller process-tree RSS of 56,623,104 bytes and zero swaps. The accepted source-only run began at host load 3.66/3.90/4.15 and ended at 3.60/3.87/4.13; host swap allocation stayed 243.88 MiB. No compiler or competing benchmark appeared in the preflight process check. Individual workload roots have separate `wait4` CPU and kernel root peak records in the raw data. The macOS sampler records process counts, RSS, and charged physical footprint; its snapshots can miss short-lived child peaks, and footprint is neither USS nor PSS. The cold child CPU delta is complete for directly reaped children, while the cold process-tree memory snapshots remain approximate. No allocation pass or matched upstream USS/PSS baseline was run. No production code, dependency, formatter, linter, hook, or remote was changed.
