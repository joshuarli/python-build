# zlib-rs compressed-byte compatibility, 2026-09-24

## Scope

`zlib-byte-compat.py` ran the same pinned, no-Rust CPython 3.16 executable
with either its platform zlib 1.2.12 extension or the already proved
zlib-rs 0.6.7 overlay. The extension SHA-256 values were
`5c6c337e794165f39ca399430abec5040ae428364a39bc8e7e3a59388a9bbacc`
and `3e1081e635ab5818c191e00303c757b00482c45b075b6d713395cc2e1699d118`,
respectively. This changes only the `zlib` backend under CPython's existing
public wrapper. Full generated streams and the per-case report are in the
ignored `rust-cpython/results/zlib-byte-compat/` directory of this worktree.

Four fixed inputs (empty, repeated text, byte-pattern binary, and mixed),
levels 0/1/6/9, raw/zlib/gzip window settings (-15/-9/9/15/31 where
applicable), default/filtered/Huffman-only/RLE/fixed strategies, one-call and
seven-byte input chunks, and sync/full flush boundaries made 876 cases.
The public `zlib.compress`, `zlib.compressobj`, `gzip.compress`,
`gzip.GzipFile`, and `zipfile.ZipFile` paths were exercised. Gzip timestamp
and filename and ZIP timestamp, mode, and member name were fixed so container
bytes were comparable.

## Result

| Public path | Equal compressed bytes | Cases |
| --- | ---: | ---: |
| `zlib.compress` | 10 | 16 |
| `zlib.compressobj` | 638 | 824 |
| `gzip.compress` | 6 | 12 |
| `gzip.GzipFile` | 6 | 12 |
| `zipfile.ZipFile` | 6 | 12 |
| **Total** | **666** | **876** |

All 204 level-0 and 216 level-9 cases produced equal bytes; 102 of 216
level-1 and 108 of 240 level-6 cases differed. Huffman-only and RLE
strategies matched in all 320 sampled cases. For a concrete level-6 example,
`zlib.compress` of the 12,288-byte binary pattern emitted 388 bytes with
platform zlib and 419 bytes with zlib-rs. The same input through
`gzip.GzipFile` emitted 400 versus 431 bytes; through `zipfile.ZipFile`,
500 versus 531 bytes. Other inputs and settings can reverse or remove that
size difference.

Each backend reproduced its own entire result on a second run. Every one of
the 876 streams round-tripped within its producer and decoded in the other
backend, both whole and in seven-byte output/input reads. The decoded
SHA-256, Adler-32, and CRC-32 values agreed. ZIP member reads also verified
the archive's CRC. This establishes interoperability for these samples, not
compressed-byte identity. Applications that compare compressed hashes,
signed archives, or reproducible artifact bytes would observe changes.
Even within one backend, changing from one input call to seven-byte calls
changed 30 of 400 platform-zlib streams and 99 of 400 zlib-rs streams; the
streaming call boundary belongs in any byte-for-byte contract.

## Resource account and limits

The final diagnostic command used `/usr/bin/time -l` around the Python
controller and its six serial CPython child processes (two encodes per backend
and one cross-decode per backend). It reported 4.31 user CPU seconds,
0.20 system CPU seconds, 4.59 elapsed seconds, and 106,577,920 bytes maximum
resident set size. These `time -l` counters are for the wrapped command;
the report does not partition CPU or RSS by child. The observed run was well
inside the assigned 300 CPU-second and 2 GiB limits. This was a correctness
probe, not a performance comparison.

This does not cover arbitrary input lengths, all `memLevel` values, preset
dictionaries, every flush sequence, malformed input behavior, or external
gzip/ZIP readers. The previous zlib proof covered CPython's broader zlib and
consumer test suites. No production build was changed, and no full suite was
run in this lane.

**Verdict:** keep the backend as an interoperability experiment, but reject
compressed-byte equivalence to platform zlib as a claim. Any promotion needs
an explicit decision that changed encoded bytes are acceptable for public
zlib/gzip/ZIP producers and reproducible artifacts.
