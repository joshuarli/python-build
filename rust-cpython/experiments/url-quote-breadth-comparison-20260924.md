# Installed URL quotation breadth comparison, 2026-09-24

## Verdict

The guarded Rust quotation patch improves both newly registered complete URL workloads on this macOS host. Against the last accepted Rust fork installation, five serial paired runs gave median candidate/control external wall ratios of **0.856** for `catalog_search_form` and **0.955** for `catalog_request_path`; root kernel user-plus-system CPU ratios were **0.856** and **0.957**. Each task's gain exceeds its accepted control and candidate timing self-noise. Neither task showed a clear individual timing regression. The existing catalog normalization task remains visible through its earlier installed comparison: wall ratio 0.823 and root CPU ratio 0.821, with equal full digests.

Against the matched vanilla upstream 3.16 stage, the candidate's median wall ratios were **0.878** for search form and **0.956** for request path; root CPU ratios were **0.875** and **0.955**. Upstream has the same broad compiler, PGO, ThinLTO, architecture, and optimization policy, but a different fork ancestry and independently generated PGO profile. The prior-fork comparison is the direct installed candidate comparison; upstream results establish the broader reference direction.

The separate three-pair root peak-RSS and sampled-footprint medians are within measured self-noise. Request path consistently used about 0.25–0.49 MB more peak RSS in the paired passes. One upstream path pair rose **491,520 bytes**, above the candidate's **473,673-byte** self-noise allowance; the upstream path paired median was **425,984 bytes**, within that allowance. This directional signal and single excursion should remain visible. macOS whole-tree USS/PSS and compatible native/Python allocation counts remain unavailable, so upstream memory parity is **open**, not passed. A fresh-process `import urllib.parse` sentinel had a median +4.1% candidate/control wall ratio and +196,608-byte paired peak-RSS median, but timing self-noise was 15.6% control and 24.8% candidate; the import regression is unresolved rather than established.

## Inputs and correctness

Base commit: `b0d16ad311178f756f454c60b0f557f681b9808f`. I APFS-cloned the accepted fork, patched fork, and upstream installed stages into this worktree's ignored `rust-cpython/work/url-quote-breadth-comparison-20260924/{control,candidate,upstream}`. Their original stages were not changed. The control and upstream `urllib/parse.py` SHA-256 is `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`; the candidate's is `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee`. The candidate extension SHA-256 is `5f00a07bbcc282659e1258d0509c1e117f9db185cf94f867aeb809736f616916`.

Each clone's own interpreter generated a checked-hash parser cache before measurement. Every child checked installed executable prefix, parser path and source digest, cache magic/flags `3` and matching source hash (`fcbbd960190070b8` control/upstream; `fb86b91008046490` candidate), cache digest, and candidate extension path/digest. Measured children set `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=1`, ordinary allocator, and the same repository `PYTHONPATH`. The raw file records all identities.

Every measured batch checked the fixed input SHA-256 `7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f` and complete output SHA-256: `a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22` for search form, `52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff` for request path. One operation handles all 48 records; search form makes 48 encodes, 48 `Request` objects, 48 parses, and validates 240 ordered pairs; request path makes 96 splits, 96 byte unquotes, 48 quotations, 48 unsplits, and 48 byte round-trip checks. A pass-through counter outside timing saw **182** candidate native helper calls per search batch and **32** per path batch, matching the workload-registration diagnostic. The installed candidate's earlier full-build report already records the unchanged `test_urlparse`/`test_urllib` and 2,177-case public differential checks.

A separate fresh-process long-input sentinel quoted exact lengths **199,999**, **200,000**, and **200,001** bytes from a repeated long catalog URL containing unsafe percent bytes. All three complete output digests and decoded-byte round trips matched control in three memory pairs. A counter around the candidate helper saw one call at 199,999 and none at the two fallback lengths. These checks ran outside timing.

## Timing and memory

Timing used external monotonic wall time and `wait4` root user/system CPU, with no sampler or profiler. Each task ran five counterbalanced full-task pairs after five-pair self-calibrations on each side. The tasks launch no children; the separate memory observer saw one process and zero sampling errors in every run. Root CPU is recorded as root-only coverage, which covers the task's work. Memory used a separate external 10 ms sampler, kernel lifetime root peak RSS, and sampled Apple charged-dirty physical footprint. Footprint is neither USS nor PSS, and the tasks mark no retained-memory boundary.

| Task and comparator | Batches/child | Control wall / candidate wall per batch | Candidate/control wall | Control root CPU / candidate root CPU per batch | Candidate/control CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| Search form, prior fork | 500 | 1.851 / 1.595 ms | 0.856 | 1.810 / 1.550 ms | 0.856 |
| Search form, upstream | 500 | 1.833 / 1.601 ms | 0.878 | 1.792 / 1.568 ms | 0.875 |
| Request path, prior fork | 4,000 | 0.1875 / 0.1790 ms | 0.955 | 0.1820 / 0.1742 ms | 0.957 |
| Request path, upstream | 4,000 | 0.1875 / 0.1796 ms | 0.956 | 0.1833 / 0.1751 ms | 0.955 |

The raw file retains each root user and system CPU value separately. Search form's accepted timing self-noise was 2.21% control, 1.78% candidate, and 2.81% upstream. Request path's was 2.51%, 1.64%, and 1.45%. The registry default of 1,000 path batches yielded about 0.25-second children and 5.49% control self-noise; I retained that exploratory run and increased to 4,000 batches, yielding about 0.75 seconds for the control. The first search candidate and upstream self-calibrations had 11.43% and 9.79% noise and were repeated. The first upstream path paired timing pass had two delayed upstream children and widely scattered ratios; it is retained as discarded interference, followed by five ratios of `0.954, 0.946, 0.957, 0.959, 0.956`. No paired task result was selected from an aggregate.

| Task and comparator | Paired peak-RSS deltas, candidate minus control | Paired sampled-footprint deltas | RSS self-noise, control / candidate |
| --- | ---: | ---: | ---: |
| Search form, prior fork | −180,224, +147,456, +114,688 B | −262,168, +131,096, +65,560 B | 182,182 / 473,673 B |
| Search form, upstream | +49,152, −114,688, −65,536 B | −32,744, −196,584, −163,840 B | 874,473 / 473,673 B |
| Request path, prior fork | +245,760, +360,448, +245,760 B | +229,376, +327,680, +229,376 B | 983,782 / 473,673 B |
| Request path, upstream | +491,520, +425,984, +245,760 B | +409,624, +245,784, +180,248 B | 582,982 / 473,673 B |

The upstream path +491,520-byte pair exceeds candidate self-noise by 17,847 bytes, while the other two upstream path pairs and all three prior-fork path pairs remain within it. Sampled footprint deltas are listed separately and do not establish unique-memory parity. Installed launcher bytes are 33,768 control, 33,832 candidate, and 33,848 upstream. The candidate alone installs the 51,288-byte URL extension; the upstream-to-candidate whole-tree comparison, including other fork differences, is in the earlier upstream report.

## Resource accounting and next action

The compact [raw observations](data/url-quote-breadth-comparison-20260924.json) contain every accepted and discarded timing/memory row, child output checks, sample count, one-process/error checks, identities, self-noise, and `/usr/bin/time -l` controller records. Across the retained timed controller commands, including discarded calibrations and the exploratory path runs, user-plus-system CPU was **185.58 seconds**; the highest per-command controller RSS was **32,374,784 bytes**, with zero reported swaps. APFS clone preparation consumed about 7.04 additional CPU seconds outside this controller total. An initial controller assertion failed before launching a workload because the host Python computed a different parser source-hash value; its overwritten time record is unavailable, and the fixed runner checks the staged interpreters' recorded hash values. OrbStack and ordinary desktop activity remained present; the coordinator kept builds and competing benchmarks queued. The host reported 243.88 MB swap in use after the runs; the controller commands reported no swap activity.

Keep the guarded URL patch as a speed-qualified experiment across all three registered catalog tasks. The next resource gate is a compatible macOS unique/proportional-memory and allocation comparison, particularly for request path and fresh import. No source, workload, dependency, or production files changed in this comparison lane.
