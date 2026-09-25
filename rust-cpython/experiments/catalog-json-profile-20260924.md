# Complete catalog JSON export: pinned-control diagnostic

## Question and boundary

Does the package-free `catalog_json_export` workload expose a useful Rust
kernel in CPython's JSON implementation? The workload calls the fixture
application's public `catalog_service.export.export_json` on 512 records per
operation. This diagnostic used only the pinned control interpreter at
`/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`; it changed no
source or installed interpreter. The 300-operation uninstrumented run preceded
a separate 300-operation `cProfile` run. Both completed with the fixture's
digest checks. The profiled run is for attribution, not timing comparison.

## Complete-task evidence

| Run | Exports | Export elapsed reported by workload | `/usr/bin/time -l` real | User + system CPU | Peak RSS | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uninstrumented | 300 | 1.236 s (4.121 ms/export) | 1.36 s | 1.31 + 0.02 = 1.33 s (4.43 ms/export) | 30,916,608 B | 0 |
| `cProfile` | 300 | 2.010 s | 2.13 s | 2.09 + 0.02 = 2.11 s | 31,424,512 B | 0 |

Each operation exported 512 records and 259,349 bytes. Both runs reported
input SHA-256
`9c3c7d7b1dd6d58e72b446ce4684ee93edc031aca5bdd6b8c6d852bc079b8bc4`
and output SHA-256
`e73d3916e9d6984dacef72251336a1582a4d64814c244595aeb566af4d9146d3`.
The reported export elapsed excludes input creation/checking and output
hashing. Process CPU and RSS include startup, those checks, and printing.
`/usr/bin/time -l` accounts for the one-process command; there were no child
processes. Peak memory footprint was 18,006,496 B uninstrumented and
18,481,632 B profiled. No swap was reported. The three diagnostic process
commands together used 3.45 s of kernel-reported user plus system CPU; this
includes the accelerator check below and excludes read-only log inspection.

## Profile attribution

`cProfile` recorded 4,354,018 calls in 2.093 s for the entire invocation.
Its 300 `export_json` calls accumulated 1.969 s. Relevant rows, rounded from
`pstats`:

| Call path | Calls | Cumulative s | Internal s | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `export_json` | 300 | 1.969 | 0.073 | Complete export path, including list construction, sort, and final encoding |
| `encode_entry` | 154,112 | 0.854 | 0.137 | 153,600 export records plus 512 setup digest records; overlaps `json.dumps` |
| `json.dumps` | 154,413 | 0.834 | 0.105 | 153,600 record encodes, 300 final array encodes, 512 setup encodes, one result print |
| `JSONEncoder.encode` / `iterencode` | 154,413 each | 0.709 / 0.572 | 0.097 / 0.572 | Encoder path, including C encoder execution inside `iterencode` |
| `json.loads` | 153,600 | 0.781 | 0.113 | One decode of each record's newly encoded bytes |
| `JSONDecoder.decode` / `raw_decode` | 153,600 each | 0.457 / 0.258 | 0.117 / 0.258 | Decoder path, including C scanner execution inside `raw_decode` |
| `list.sort` | 300 | 0.035 | 0.027 | Identifier sort and its key calls |

`json.dumps` and `json.loads` occur sequentially within `export_json`; their
inclusive totals account for roughly 1.6 s of its 1.969 s. This is a broad
attribution, not a measured C-only fraction. The `encode_entry`, encoder, and
decoder rows nest under those totals and **must not be added**. `cProfile`
charges work performed by `_json` callable objects to their Python caller
frames, so it cannot isolate C encoder/scanner time. Its instrumentation also
changes timing; the profiled elapsed and CPU cannot estimate an uninstrumented
speedup.

The stage interpreter loads `_json.cpython-316-darwin.so`. Its
`json.encoder.c_make_encoder` is `_json.Encoder`,
`json.scanner.make_scanner` is `_json.Scanner`, and
`json.decoder.scanstring` is the C built-in. The chosen compact `dumps` calls
use the one-shot C encoder path; default `loads` uses the C scanner. The
Python fallback encoder was present but unused in the profiled hot path.

## Decision

**Defer a Rust `_json` kernel for this workload.** The dominant JSON paths
already use C accelerators. The application deliberately encodes each model
entry to bytes, immediately decodes it to a mapping, sorts those mappings,
then encodes the complete array. That repeated round trip creates 153,600
encoder and decoder calls in 300 exports and is a more specific source of
work than a missing low-level accelerator. A Rust replacement would need to
respect the public encoder/decoder options and extension hooks, including
custom `cls`/`default`, `object_hook`/`object_pairs_hook`/`array_hook`, numeric
parse hooks, ordering, Unicode and error semantics. This profile does not
isolate enough C time or show a semantic advantage to justify that surface.
An application-level mapping path would need a separate contract-preserving
experiment and paired uninstrumented comparison before any speed claim.

## Reproduction and raw records

From the worktree root, with no concurrent build or benchmark:

```text
/usr/bin/time -l -o rust-cpython/work/json-profile-20260924ah/uninstrumented-300.time /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -m benchmarks.workloads.catalog_json catalog_json_export --iterations 300
/usr/bin/time -l -o rust-cpython/work/json-profile-20260924ah/cprofile-300.time /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -m cProfile -o rust-cpython/work/json-profile-20260924ah/cprofile-300.pstats -m benchmarks.workloads.catalog_json catalog_json_export --iterations 300
```

Stdout, stderr, resource logs, the profile data, and an independently timed
accelerator identity check are in ignored
`rust-cpython/work/json-profile-20260924ah/`. The two commands above had
stdout and stderr redirected to unique files there. Both exited zero. The
accelerator check used 0.01 + 0.00 s CPU, 18,104,320 B peak RSS, and zero
swaps. No tests, formatter, linter, hook, or build was run in this lane.
