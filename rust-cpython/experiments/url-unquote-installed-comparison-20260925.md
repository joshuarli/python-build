# Fresh installed URL unquote comparison, 2026-09-25

## Result

The fresh opt-in `--url-unquote` installation completed the entire `catalog_search_form` workload with **42.9% lower median process wall time** and **44.0% lower median kernel user-plus-system CPU** than the accepted quote-only installation. Five serial, counterbalanced pairs all showed the same direction. Every attempt returned the complete registered input and output digests. Five control/control and five candidate/candidate pairs on each workload bounded ordinary same-side wall variation at 2.6% for search. The observed search gain is well beyond that local noise.

`catalog_url_normalize`, the negative control with only four eligible credential decodes per 48-URL batch, showed a 2.6% median wall and 2.7% median CPU reduction. Its smaller difference could reflect the two separate native builds and PGO profiles. The earlier [same-executable decoder proof](url-unquote-proof-20260925.md) is the cleaner attribution of the search gain to the decoder. This installed comparison confirms the gain survives a fresh full opt-in build; it does not by itself isolate decoder machine code.

## Installed identity and method

The accepted quote-only control came from `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage`. The opt-in candidate came from `/private/tmp/python-build-exp-url-unquote-build-20260925a/rust-cpython/stage`. Both stages were read only. APFS clone copies under ignored `rust-cpython/work/url-unquote-proof-20260925a/{control,candidate}` supplied the measured interpreters. Each clone received a valid checked-hash `urllib/parse.py` bytecode cache before timing. The control and candidate cache flags were `3`, with matching source hashes `fb86b91008046490` and `0cbdbaed6fde156b`. Separate verbose imports showed each cache matched its source, loaded its code object, and loaded its own `_rust_url_quote` extension. Measured children suppressed bytecode writes and used normal per-process hash randomization.

| Installed file | Control SHA-256 / bytes | Candidate SHA-256 / bytes |
| --- | --- | --- |
| `urllib/parse.py` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` / 51,300 | `ad11741ef88e9b7175ef0e1ffb311fdee865c073194743e08eb61adee828f4dd` / 51,565 |
| checked-hash parser cache | `4c3967daa456464aa06579d4d66280e4c202b73153754a7b5568469215e98520` / 57,692 | `efaa99302d581df80e0b1a60dacff04071d94def62b6517b9db1762ec487f8a1` / 58,050 |
| `_rust_url_quote` extension | `5f00a07bbcc282659e1258d0509c1e117f9db185cf94f867aeb809736f616916` / 51,288 | `dec52fdb6257198c112b0bf475ce5a414b055ad8daa7ea97f8e053c2a5ac5e71` / 51,720 |

The parser and extension bytes in both clones matched their source stages. The control extension lacked `unquote_ascii`; the candidate exposed it. The two full builds used the same pinned CPython source, LLVM 23.1.2, ThinLTO, and `-m test --pgo -j 9` profile task, but their PGO data came from separate runs. Their installed interpreter and `libpython3.16.dylib` SHA-256 values also differed; [compact data](data/url-unquote-installed-comparison-20260925.json) records all four hashes. Those native binary differences limit attribution here.

The existing `url-unquote-proof/bench.py` called the complete registered workloads. One search batch handles 48 records, 480 parsed fields, and 240 pairs; one normalization batch handles 48 URLs. Each search child ran 500 batches and each normalization child ran 2,000. The child verified its prefix, parser/cache/extension identities and final digest. `/usr/bin/time -l` surrounded each whole process to measure external elapsed time and kernel user/system CPU. The task's internal loop time is retained only as supporting detail. No memory sampler, profiler, forced GC, or special allocator ran during timing. All 60 attempts were serial: ten self pairs per task across the two sides, then five alternating-order control/candidate pairs per task.

## Complete-task measurements

| Task | Batches per child | Control median wall / CPU | Candidate median wall / CPU | Paired wall ratios, candidate/control | Paired CPU ratios |
| --- | ---: | ---: | ---: | --- | --- |
| `catalog_search_form` | 500 | 0.77 / 0.75 s | 0.44 / 0.42 s | 0.579, 0.564, 0.571, 0.564, 0.571 | 0.560, 0.566, 0.560, 0.566, 0.560 |
| `catalog_url_normalize` | 2,000 | 0.76 / 0.74 s | 0.74 / 0.72 s | 0.974, 0.974, 0.987, 0.974, 0.974 | 0.973, 0.960, 0.986, 0.973, 0.973 |

For search, median external wall per 48-record batch was 1.54 ms control and 0.88 ms candidate; median kernel CPU was 1.50 and 0.84 ms per batch. For normalization, median external wall per 48-URL batch was 0.380 and 0.370 ms; median CPU was 0.370 and 0.360 ms. `/usr/bin/time -l` rounds these process times to hundredths of a second. Search control/control wall ratios ranged from 0.974 to 1.026, and candidate/candidate from 1.000 to 1.023. Normalization control/control ranged from 0.987 to 1.013, and candidate/candidate from 0.987 to 1.000. The compact data retains every raw paired ratio, order, process time, digest, and RSS reading.

All 60 attempts used input digest `7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`. Search output was always `a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22`; normalization output was always `a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`. Each attempt has unique `.json`, `.stderr`, and `.time` raw files in the ignored work directory. There were no failed attempts.

## Resources and acceptance limit

The outer timed controller reported **38.80 user + 1.53 system = 40.33 kernel CPU seconds**, including all 60 children and their orchestration. Two separately timed digest and identity preflights added **0.10 user + 0.04 system = 0.14 seconds**, for **38.90 user + 1.57 system = 40.47 timed CPU seconds**. Summing the 60 child records alone gives 39.58 seconds; these are already included in the controller and are not added twice. APFS cloning, cache preparation, verbose import audits, and report generation were untimed preparation, so 40.47 seconds is the exact timed-attempt total, not a claim about all lane activity.

The largest `/usr/bin/time -l` lifetime peak RSS in any measured child was **30,998,528 bytes**, under the 1 GiB per-process cap; the controller's own peak was also 30,998,528 bytes. Each timed command reported zero swaps, and host swap use was 243.88 MiB before and after the comparison. Lifetime peak RSS is neither retained memory nor USS/PSS, and this pass did not run a separate memory or allocation measurement. The 40.47 timed CPU seconds were below the 150-second cap. No compiler, test suite, formatter, linter, hook, or push ran in this lane.

The search speed result passes this local complete-workload and self-noise check. Promotion of the optional decoder still requires the broad public `unquote`, `unquote_plus`, and `parse_qsl` semantic comparison, focused unchanged URL regression suites, and the separate memory/allocation and upstream comparison gates. The small normalization difference remains an observation rather than a decoder benefit claim.
