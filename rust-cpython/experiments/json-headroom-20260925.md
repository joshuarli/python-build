# Complete catalog JSON export: accepted-control headroom

This repeats the earlier pinned-stage diagnostic in
[`catalog-json-profile-20260924.md`](catalog-json-profile-20260924.md)
on the later accepted fork control. Both profiles locate the repeated
application encode/decode round trip and reach the same deferral decision;
their separate builds and profiles are not a paired speed comparison.

## Boundary and identity

This diagnostic used the accepted fork control at
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`.
That worktree was at `5e9483de38e3bacabddba6147cb7b3b0feb4eb64`;
this diagnostic worktree was based on `8c9f92c5063cab2fae6de62bacb6241308555fe8`.
The interpreter reports CPython `3.16.0a0`; the experiment source lock pins
`b812b4a7b9efaca46b98544a8633b7d7e454166b`. The measured installed
binary's SHA-256 was `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`,
`libpython3.16.dylib` was `c091393061f0a49b679131a363cac8fb8d08948135d377d8134fa75ed17a7ddc`,
and `_json.cpython-316-darwin.so` was
`24e49ed334870773c16be725f4ceca19a0a6ac8bc5f10b9f5f2f59bc87b18ab3`.
The installed `json/__init__.py`, `json/encoder.py`, and `json/decoder.py`
hashes were respectively `4cc35eb04b789ce4890cffa944829c946e4c5dd032aaa6dc01f53449b250985a`,
`2d3ded41ec1251b6334ee2d8a53b3fbb22a05202b7085636c749f99a38d00902`,
and `f339376ba0304981fc6b35246472d950903987023a46810bbe224141801ae3e7`.

The package-free `benchmarks.workloads.catalog_json` workload calls
`catalog_service.export.export_json` once per operation with all 512 fixture
entries. The workload, fixture `export.py`, and fixture `codec.py` SHA-256
hashes were respectively `1b89090ddd58d93e1504fd83321fbd806a3b2dfa26012e9e502070d7d630c0aa`,
`8dd31afad14019d223b21def3f1567ba4c5ef7e623495d74aeb193e3c5bd3c55`,
and `8f4aef23f50a5fcc1facc317e981adfcd8e43d131b9f21034151631d6107eede`.
Both runs passed the input digest
`9c3c7d7b1dd6d58e72b446ce4684ee93edc031aca5bdd6b8c6d852bc079b8bc4`
and output digest
`e73d3916e9d6984dacef72251336a1582a4d64814c244595aeb566af4d9146d3`.
Each full export produced 259,349 bytes.

## Resource and profile evidence

| Command | Complete exports | Workload export elapsed | `/usr/bin/time -l` real | User + system CPU | Peak RSS | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uninstrumented | 250 | 0.998 s, 3.992 ms/export | 1.12 s | 1.07 + 0.02 = 1.09 s | 31,244,288 B | 0 |
| `cProfile` | 250 | 1.643 s, 6.574 ms/export | 1.76 s | 1.72 + 0.02 = 1.74 s | 31,670,272 B | 0 |
| Accelerator identity | 0 | — | 0.02 s | 0.01 + 0.00 = 0.01 s | 18,268,160 B | 0 |

The three process commands used 2.84 kernel-accounted CPU seconds in total;
the largest observed RSS was 31,670,272 B. `/usr/bin/time -l` covers each
entire single-process invocation, including startup, fixture setup, digest
checks, and output. No child processes ran. The workload elapsed covers only
`export_json` calls. All three commands exited zero; their unique stdout,
stderr, time reports, and the profile data are retained under ignored
`rust-cpython/work/json-headroom-20260925a/` in this worktree.

`cProfile` recorded 3,636,744 calls and 1.720 s for the whole process;
the 250 `export_json` calls accumulated 1.611 s. Relevant rows are:

| Profile row | Calls | Cumulative s | Internal s | Share of `export_json` cumulative |
| --- | ---: | ---: | ---: | ---: |
| `export_json` | 250 | 1.611 | 0.055 | 100% |
| `json.dumps`, all callers | 128,763 | 0.683 | 0.087 | 42.4% |
| `json.loads` | 128,000 | 0.640 | 0.091 | 39.7% |
| `JSONEncoder.iterencode` | 128,763 | 0.467 | 0.467 | 29.0% |
| `JSONDecoder.raw_decode` | 128,000 | 0.213 | 0.213 | 13.2% |
| `encode_entry` | 128,512 | 0.703 | 0.114 | 43.7% |
| `list.sort` | 250 | 0.028 | 0.021 | 1.8% |
| SHA-256 constructor | 252 | 0.027 | 0.027 | outside export |
| Fixture import path `_catalog_modules` | 1 | 0.021 | 0.000 | outside export |

The `json.dumps` callers split into 128,512 entry encodes (including 512
input-check encodes, 0.497 s cumulative), 250 final-array encodes (0.186 s),
and one result print. Within the export itself there are 128,000 entry
encodes and 128,000 immediate decodes. Entry conversion in `encode_entry`
builds a dict, copies attributes and labels, encodes JSON, and returns UTF-8
bytes. `export_json` then decodes every byte string back to a mapping, sorts
by identifier, and encodes the full array. `encode_entry` and the encoder rows
are nested; their times cannot be added. `json.dumps` plus `json.loads` are
sequential within each export and total about 1.32 s, or 82% of its profiled
cumulative time. The final array encoding alone is about 12%.

The installed accelerator identity check reported `_json.Encoder`,
`_json.Scanner`, and built-in `scanstring`. The compact one-shot `dumps` path
selects the C encoder, and default `loads` selects the C scanner. `cProfile`
charges their execution to surrounding Python frames, so the `iterencode`
and `raw_decode` internal times **do not measure C-only time**. Instrumentation
raised observed export elapsed from 0.998 to 1.643 s; these profile shares
are diagnostic and cannot be applied directly to the uninstrumented latency.

## Headroom and recommendation

Even an impossible zero-cost replacement of all `json.dumps` and
`json.loads` calls in this profiled export would leave about 0.288 s of its
1.611 s, an upper-bound speedup near 5.6x under this profile's costs. A Rust
full-document engine has much less demonstrated headroom: the existing C
accelerator already handles encoding and scanning, and the profile cannot
separate its share from Python wrapper, object conversion, call, and bytes
allocation costs. It also cannot remove the application's encode/decode
round trip while preserving the current `export_json` implementation.

**Defer a Rust full-document JSON engine.** Investigate the application
boundary first: construct mappings directly from `CatalogEntry`, sort once,
and encode the final array once, while preserving exact output bytes and the
public export contract. That needs a separate, paired uninstrumented
comparison before making a speed claim. The generic `_json` surface also has
custom encoder/decoder hooks, numeric parsing, Unicode, ordering, and error
semantics that this complete export does not justify reimplementing.

## Exact process commands

Run from `/private/tmp/python-build-exp-json-headroom-20260925a`:

```sh
/usr/bin/time -l -o rust-cpython/work/json-headroom-20260925a/uninstrumented-250.time /private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16 -m benchmarks.workloads.catalog_json catalog_json_export --iterations 250 > rust-cpython/work/json-headroom-20260925a/uninstrumented-250.stdout 2> rust-cpython/work/json-headroom-20260925a/uninstrumented-250.stderr
/usr/bin/time -l -o rust-cpython/work/json-headroom-20260925a/cprofile-250.time /private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16 -m cProfile -o rust-cpython/work/json-headroom-20260925a/cprofile-250.pstats -m benchmarks.workloads.catalog_json catalog_json_export --iterations 250 > rust-cpython/work/json-headroom-20260925a/cprofile-250.stdout 2> rust-cpython/work/json-headroom-20260925a/cprofile-250.stderr
/usr/bin/time -l -o rust-cpython/work/json-headroom-20260925a/accelerator-identity.time /private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16 -c 'import sys,json,_json,json.encoder,json.scanner,json.decoder; print(sys.version); print(_json.__file__); print(json.encoder.c_make_encoder, json.scanner.make_scanner, json.decoder.scanstring)' > rust-cpython/work/json-headroom-20260925a/accelerator-identity.stdout 2> rust-cpython/work/json-headroom-20260925a/accelerator-identity.stderr
```

No source, dependency, or interpreter was changed. No test suite, formatter,
linter, hook, or build was run.
