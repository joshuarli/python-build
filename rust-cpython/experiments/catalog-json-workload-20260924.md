# Complete catalog JSON export workload

`benchmarks/workloads/catalog_json.py` registers `catalog_json_export` as a
package-free serialization workload. One operation calls the checked-in
`catalog_service.export.export_json` once on all 512 `CatalogEntry` objects.
The catalog records are created before timing in a deliberately unsorted order
and include all four entry kinds, varied revisions, labels, attributes,
Unicode, JSON escapes, short and long bodies. The export sorts by identifier,
encodes each entry through `catalog_service.codec.encode_entry`, decodes each
entry to a mapping with `json.loads`, then encodes the complete array with
`json.dumps`. This is the fixture application's complete public JSON export
path. `json` ordinarily calls the `_json` C encoder and scanner for these
operations; the surrounding model conversion, list construction, sorting,
and byte encoding remain Python work. No Rust implementation is included.

The input digest is SHA-256 over each `encode_entry` byte string prefixed by
its eight-byte big-endian length, in workload order:
`9c3c7d7b1dd6d58e72b446ce4684ee93edc031aca5bdd6b8c6d852bc079b8bc4`.
The full 259,349-byte export's SHA-256 is
`e73d3916e9d6984dacef72251336a1582a4d64814c244595aeb566af4d9146d3`.
Both digests are checked on every invocation. Generation and input checking
precede measured time. Each complete export is timed; output hashing and
checking follow its measured interval. `operation_count` is the number of
complete exports; each processes 512 records and produces 259,349 bytes.

Focused correctness evidence on 2026-09-24:

| Command | Result | User + system CPU | Peak RSS | Swaps |
| --- | --- | ---: | ---: | ---: |
| System `python3` digest derivation | Both digests and byte count above | 0.05 + 0.02 s | 26,066,944 B | 0 |
| Pinned stage Python 3.16, `python3.16 -m unittest benchmarks.tests.test_catalog_json` | 2 tests pass | 0.08 + 0.02 s | 32,899,072 B | 0 |
| Pinned stage Python 3.16, `-m benchmarks.workloads.catalog_json catalog_json_export --iterations 1` | Exact digests, 512 records, 259,349 bytes | 0.05 + 0.01 s | 30,244,864 B | 0 |
| URL candidate stage Python 3.16, same one-iteration command | Exact digests and sizes | 0.05 + 0.02 s | 30,064,640 B | 0 |

The pinned interpreter was
`/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`; the candidate
was `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`.
Each command was wrapped with `/usr/bin/time -l`; unique raw stdout and time
logs are under `rust-cpython/work/json-workload/` in this lane. Kernel user and
system CPU, peak resident set, and swap fields cover each short single-process
command. No heavy benchmark or paired performance comparison was run while
the ZIP lane was active. The one-shot elapsed values are correctness output,
not comparison evidence.
