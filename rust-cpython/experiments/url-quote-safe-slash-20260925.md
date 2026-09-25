# Exact default-safe URL quotation route, 2026-09-25

## Verdict

**Reject this optional parser guard under the assigned breadth gate.** Routing
every exact `safe=b'/'` quote through pinned Python reduced complete
`catalog_request_path` CPU by 4.4–6.9% against the current Rust guard in two
direct pairs. Complete `catalog_search_form` CPU increased by 0.7–0.9%; that
increase exceeded the observed same-side drift (0.08% current, 0.02%
proposed). `catalog_url_normalize` had mixed direct pairs and no clear change.
The proposed search route still beat the pure parser by about 4% in two pairs,
but the direct regression against the current guard fails this experiment's
stop condition. The current patch and manifest remain untouched.

The host's one-minute load moved from 3.63 to 4.61 on ten CPUs. OrbStack
Helper was about 18–28% CPU in boundary snapshots, and swap used remained
243.88 MiB. These are source-overlay measurements on a moderately loaded
host, not an installed-build or publishable speed claim. No further timing
lane was run after this result.

## Source and measurement

The standalone parser hunk adds `safe != b'/'` after the existing public
fast exit, exact-byte type checks, and trace/profile guard. It preserves the
Python route for the exact default safe value at every length; other safe
values retain the current Rust route. Both parsers were applied to copied
source from the same read-only CPython 3.16 installation. Every arm used the
same interpreter (SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`).
The pure parser SHA-256 was
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`,
the current parser `f2949f2bfd61891f33a9e79168f1c188587b374985ebb3faa04a476202b280f2`,
and the proposed parser `d9d3259acb4e9da268445e1dba6613d7796d92723631d010822976c3745e9765`.
The exact current `0001` patch SHA-256 was
`8117e87d51a91dd362d5c315f3eae552ac1144b83f43dae1980423c320b618ad`;
the optional hunk was
`46a76b4cf1555b382901f17f38a8c941dae5be56db1fb9b6dd63e0e00b46c029`.

The private extension was compiled in this worktree from the current patch's
C and Rust hunks, SHA-256 `727e5b12a8a2e0b8a81be59b86ccb5252f88b1f66c64ca1cbc05ec71448f44df`
and `bb9156522ea47140e52e309b501ee3222ed5466fb8b33a779a31566e184fad8c`.
Its binary SHA-256 was
`b1ab627f758d778087fb2c8e8e8df0835396e9b9c8d3db45550c7ca74710d617`.
Pinned nightly Rust 2026-09-15 and locked LLVM 23.1.2 Clang binary hashes,
the precise commands, and all process resource observations are in the raw
JSON. Direct `rustc`, Clang compilation, and linking used respectively
0.060, 0.076, and 0.117 kernel user-plus-system CPU seconds; peak RSS was
101.5, 54.1, and 35.7 MB, with zero reported swaps for each. There was no
full build or PGO.

Each arm copied `urllib/*.py` to an isolated source-only overlay with no
`__pycache__`; fresh processes used `-B`, `PYTHONDONTWRITEBYTECODE=1`, and
`PYTHONHASHSEED=1`. `PYTHONPATH` selected side, private extension, then
repository root. The pure parser did not import the extension. Complete tasks
used 500 search, 1,000 path, and 2,000 normalization iterations. Every one
of the 36 task attempts matched input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and its exact registered output digest. `os.wait4` measured direct-child
kernel user/system CPU, lifetime peak RSS, and swaps; monotonic wall covered
startup and output. These tasks spawn no children. Peak RSS ranged 28.6–34.7
MB across tasks, with no consistent paired direction; all `ru_nswap` values
were zero. Unique or proportional memory was unavailable.

| Complete task | Proposed/current paired CPU ratios | Proposed/current paired wall ratios | Proposed/pure paired CPU ratios | Same-side CPU second/first |
| --- | --- | --- | --- | --- |
| Search form | 1.0069, 1.0092 | 0.9854, 1.0013 | 0.9603, 0.9593 | current 1.0008; proposed 0.9998 |
| Request path | 0.9306, 0.9555 | 0.9175, 0.9537 | 1.0286, 1.0217 | current 1.0010; proposed 1.0016 |
| URL normalize | 1.0053, 0.9868 | 1.0056, 0.9834 | 1.0310, 1.0498 | current 1.0060; proposed 0.9986 |

The synthetic sentinel quoted a 32 KiB byte string with exact `safe=b'/'`
100 times in each fresh process. Its complete output digest matched in all
four attempts. Proposed/current CPU ratios were 2.35 and 2.30; wall ratios
were 2.09 and 2.13. This shows a long-input gain the guard would discard,
but this synthetic loop is not an application gate.

The first run stopped after one synthetic call because the repeated source
contained only 30,720 bytes, below the intended 32 KiB. Its three successful
build attempts and invalid sentinel are preserved in
`data/url-quote-safe-slash-20260925.json`. The corrected run's three build,
four sentinel, and 36 task attempts are in
`data/url-quote-safe-slash-20260925-run2.json`; each was checkpointed under a
unique ID. No tests, formatters, linters, hooks, dependencies, commits, or
remote operations were run or added. Static AST and overlay cache checks
passed.
