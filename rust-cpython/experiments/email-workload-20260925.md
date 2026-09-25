# Pinned email archive ingest workload

**Keep as a priority-0 coverage workload; no speed claim.** `email-workload-20260925.py` ingests 11 source-corpus RFC messages as one archive operation. It parses 72 MIME parts, extracts searchable subject, sender, recipient, date, message ID, part type, disposition, filename, charset, decoded content digest, and parser defects, then serializes and reparses every message to check the index. The output digest includes the complete index and each serialized message digest. This is an application-style mail import with genuine plain text, multipart, report, forwarded, signed, HTML, and attachment-bearing messages. Repeating the archive is for measurement only; one logical operation is the entire fixed archive.

The source is Rust-for-CPython commit `b812b4a7b9efaca46b98544a8633b7d7e454166b`, PSF-2.0, with archive SHA-256 `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467` in `rust-cpython/sources.lock.json`. Fixture names and their SHA-256 values are pinned in the workload. They were surveyed in the extracted source tree and matched byte for byte against the installed stage fixture tree. Runtime reads only those local fixture bytes, verifies every digest before timing, and requires no network or added dependency. The staged CPython test fixture tree is an experimental input, not a shipped product fixture. This workload is deliberately standalone rather than registered in the production benchmark suite.

## Recipe and observed identity

From this worktree root, with the installed 3.16 experiment stage available:

```sh
/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -B rust-cpython/experiments/email-workload-20260925.py --iterations 5
/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -B rust-cpython/experiments/email-workload-20260925.py --iterations 5 --profile
/usr/bin/time -l /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -B rust-cpython/experiments/email-workload-20260925.py --iterations 5
```

`--fixture-root` can point at another verified extraction's `Lib/test/test_email/data` or an installed `lib/python3.16/test/test_email/data`; the default is the active interpreter's installed tree. The two fresh `/usr/bin/time -l` process invocations each returned output SHA-256 `e5faf8d7b11d84b98aef05bb543b77eecb8ae5324b13467bf0d6136b37572534`. Each operation read 27,194 bytes, indexed 11 messages and 72 parts, and serialized 27,140 bytes. The workload checks that output digest on every operation.

The compact record is `rust-cpython/experiments/data/email-workload-20260925.json`. It retains the initial attempts under script SHA-256 `69865d8e...` and adds three distinct `lazy-import-*` attempts under revised script SHA-256 `9a0ab388d856435b29ab0fbdc0b73617de90ffc470e7ff4a746fc80d641a8792`. The revision loads `cProfile`, `pstats`, `resource`, and `os` only in `--profile` mode. In its two plain fresh processes, task time was 0.149 and 0.155 seconds for five operations; whole-process wall time was 0.25 and 0.21 seconds, kernel-accounted user CPU 0.17 and 0.18 seconds, system CPU 0.02 and 0.01 seconds, peak RSS 29,523,968 and 29,540,352 bytes, with zero swaps. `/usr/bin/time -l` covers interpreter startup and imports, unlike the task timer.

The earlier script is reconstructed exactly by moving those four imports from
the `--profile` branch to the top-level import block; its recorded hash
checks the reconstruction. Its plain-process resource values are superseded
by the revised script's measurements.

The revised profiled process took 0.54 seconds wall, 0.51 user CPU, 0.01 system CPU, and 31,555,584 bytes peak RSS externally. The internal profile window took 0.480 seconds, 0.476 user CPU and 0.0023 system CPU, with 31,080,448 bytes process peak RSS. Its initial load averages were 3.083 / 3.210 / 3.252. The older profile retained in the record measured 31,227,904 bytes process peak RSS and initial load averages of 2.333 / 3.031 / 3.199; those values supersede the inaccurate rounded figures in the first draft of this report. Profile instrumentation changes timing, and the host was loaded, so these are diagnostics rather than a baseline speed result. The discarded first collector attempt retains numeric whole-process values but no captured output identity; it is excluded from the repeatability claim.

The revised `cProfile` run attributed 0.349 seconds cumulative to header registry construction/fetch paths and 0.220 seconds cumulative to `BytesParser.parsebytes` across 110 parse calls. Those stacks overlap; their times must not be added. The header registry path offers the clearest place to investigate, but this one diagnostic does not isolate a safe native kernel or estimate a candidate gain. A quiet-host, paired control/candidate run with matching fixture and output identities is required for a speed verdict.

The fixture corpus is small and historically test-oriented, with 11 selected messages totaling 27 KB. It gives semantic breadth and a complete import operation but does not model mailbox storage, network transfer, giant attachments, or a modern production mail distribution. The source archive itself was not rehashed during this lane; the checked source lock and per-fixture hashes are the provenance and runtime byte gates here.
