# `difflib` dictionary reuse probe

## Candidate and decision

**Reject.** In the pinned CPython 3.16 `SequenceMatcher.find_longest_match`, the candidate alternates two `j2len` dictionaries and clears the spare row instead of allocating a new row each iteration. It is a diagnostic monkeypatch of the pinned function, not a product patch or native kernel. It changes no persistent matcher state, dependencies, or public interface. The exact three source replacements fail closed if the pinned implementation changes. Both registered complete `unified_diff` workloads produced identical patch digests, but the candidate has no repeatable useful public workload gain and raises peak RSS by about 0.3 MB. Reordered input is slower in internal wall and user CPU. This does not justify a Rust port of this row-reuse idea.

## Semantic evidence

- Interpreter: `/Users/josh/d/python-build/rust-cpython/stage-no-rust/bin/python3.16` (pinned `difflib.py` SHA-256 `3a5bb23205537cd9a2a68255b4ca00d710573e0a18129b0166351bf126875cf3`).
- `check`: 132 differential matcher cases and 11 complete public output cases. Compared exact longest match, matching blocks, opcodes, grouped opcodes, ratios, `unified_diff`, `context_diff`, `Differ`, and `HtmlDiff`. Cases include empty/tie/prefix, junk, autojunk threshold, popular symbols, non-string hashables, exposed `b2j`/`bjunk`/`bpopular` mutations, subclass, and seeded random inputs.
- Unchanged `test.test_difflib` loaded with the candidate monkeypatch: 59 tests passed. No full CPython build or broader regression suite was run.

## Paired complete public workload evidence

Each pair ran serially in alternating control/candidate order. Each child completed 100 whole diffs, including emitted patch digest checks. External wall and `wait4` child user/system CPU are divided by 100; those measures include interpreter startup and fixture setup. Internal wall times only the complete diff loop. Peak RSS is `wait4` `ru_maxrss` for each child. Units below: milliseconds per diff, RSS MiB.

| Workload | Mode | Median external wall | Median internal wall | Median user CPU | Median system CPU | Median peak RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| difflib_unified_mostly_equal | control | 1.1749 | 0.4885 | 0.8945 | 0.1718 | 28.250 |
| difflib_unified_mostly_equal | candidate | 1.2106 | 0.4869 | 0.8911 | 0.1745 | 28.547 |
| difflib_unified_reordered | control | 0.9986 | 0.2428 | 0.6939 | 0.2031 | 28.312 |
| difflib_unified_reordered | candidate | 1.0182 | 0.2459 | 0.7059 | 0.2064 | 28.594 |

Raw serial observations (C = original, K = candidate):

| Workload | Pair | Mode | External ms | Internal ms | User ms | System ms | Peak MiB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| difflib_unified_mostly_equal | 0 | C | 1.2087 | 0.4922 | 0.9012 | 0.1699 | 28.234 |
| difflib_unified_mostly_equal | 0 | K | 1.2583 | 0.4869 | 0.8891 | 0.1746 | 28.812 |
| difflib_unified_mostly_equal | 1 | K | 1.2106 | 0.4910 | 0.8919 | 0.1667 | 28.516 |
| difflib_unified_mostly_equal | 1 | C | 1.1541 | 0.4818 | 0.8786 | 0.1718 | 28.250 |
| difflib_unified_mostly_equal | 2 | C | 1.1493 | 0.4885 | 0.8875 | 0.1696 | 28.312 |
| difflib_unified_mostly_equal | 2 | K | 1.1629 | 0.4829 | 0.8911 | 0.1745 | 28.547 |
| difflib_unified_mostly_equal | 3 | K | 1.2764 | 0.4932 | 0.9285 | 0.1970 | 28.578 |
| difflib_unified_mostly_equal | 3 | C | 1.1787 | 0.5009 | 0.8996 | 0.1731 | 28.109 |
| difflib_unified_mostly_equal | 4 | C | 1.1749 | 0.4849 | 0.8945 | 0.1792 | 28.406 |
| difflib_unified_mostly_equal | 4 | K | 1.1700 | 0.4786 | 0.8885 | 0.1742 | 28.531 |
| difflib_unified_reordered | 0 | C | 0.9571 | 0.2341 | 0.6491 | 0.1900 | 28.172 |
| difflib_unified_reordered | 0 | K | 0.9161 | 0.2379 | 0.6549 | 0.1735 | 28.688 |
| difflib_unified_reordered | 1 | K | 0.9482 | 0.2432 | 0.6744 | 0.1884 | 28.562 |
| difflib_unified_reordered | 1 | C | 1.2430 | 0.2452 | 0.6948 | 0.2054 | 28.406 |
| difflib_unified_reordered | 2 | C | 0.9986 | 0.2394 | 0.6954 | 0.2031 | 28.312 |
| difflib_unified_reordered | 2 | K | 1.1954 | 0.2459 | 0.7379 | 0.2337 | 28.594 |
| difflib_unified_reordered | 3 | K | 1.0182 | 0.2463 | 0.7059 | 0.2064 | 28.500 |
| difflib_unified_reordered | 3 | C | 1.0115 | 0.2428 | 0.6939 | 0.2053 | 28.344 |
| difflib_unified_reordered | 4 | C | 0.9793 | 0.2439 | 0.6844 | 0.1997 | 28.234 |
| difflib_unified_reordered | 4 | K | 1.0235 | 0.2486 | 0.7083 | 0.2132 | 28.734 |

The mostly equal and reordered patch digests were respectively `b5e86d88c7cad40f06a1ca79c7c2869a223315fdb30bdc7cd8940849414af2a3` and `26585b44b4a4ced0dbb5f717454d1cbc7fd290ad798a767f0de0ecd41497f7c8` in every child. Raw JSON remains in the worktree ignored `rust-cpython/results/` directory.

Host load averages around the runs were 4.13/4.48/4.83 and 4.44/4.54/4.85. A process snapshot after the runs showed OrbStack Helper near 98% CPU and 7.3 GiB RSS, `rustc` near 97% CPU and 0.9 GiB RSS. Thus differences near the noise floor are inconclusive; the candidate also raises RSS in all ten pairings and gives no persuasive speedup. Cold import and retained memory were not measured separately.
