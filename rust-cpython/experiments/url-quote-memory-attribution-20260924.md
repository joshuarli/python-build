# Lean URL quote memory attribution

## Finding

The prior ~2.93 MB peak-RSS increase is explained by **unequal `urllib.parse`
bytecode-cache validity in the overlay comparison**, within the limits of
these diagnostics. The original parser in the control used its installed
checked-hash `parse.cpython-316.pyc`. Replacing only the candidate's source
left that original cache in place with an invalid source hash. Because the
benchmark sets `PYTHONDONTWRITEBYTECODE=1`, every fresh candidate process
compiled the 51 KB parser source during import. The increase appeared before
catalog quotation work. When both sides compiled source, or both sides had
valid checked-hash bytecode, the candidate's paired median RSS difference was
near zero and had mixed signs across rounds. Explicitly importing the lean
extension with the original parser also stayed near the control.

This revises the [lean comparison's](url-quote-lean-comparison-20260924.md)
memory interpretation. It does not establish a timing gain or final memory
qualification. The next comparison should retain this same lean quote
implementation, give **both** installed parsers valid bytecode caches, and
rerun candidate self-calibration, matched timing, and paired memory checks.
There is no evidence here that a different native quote variant is needed to
address the measured 2.93 MB rise.

## Controlled trees and cache states

I APFS-cloned the same pinned `rust-cpython/stage-no-rust` independently into
`control`, `import_only`, and `candidate` under the ignored
`rust-cpython/work/url-quote-memory-attribution-20260924/`. The source stage
and earlier lean proof were read-only inputs. `control` retained original
`urllib.parse` and had no extension. `import_only` retained original
`urllib.parse`, installed the lean extension, and imported it explicitly.
`candidate` installed the same extension and guarded parser. No compilation
of the extension, dependency, or CPython took place.

| Installed item | SHA-256 |
| --- | --- |
| All three `bin/python3.16` and source-stage executable | `ecbc7340ff2ffce477c43ac8cf10465b896708c9599112f6adcbde105418da5f` |
| Original control/import-only/source-stage `urllib/parse.py` | `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825` |
| Guarded candidate `urllib/parse.py` | `8e29cff7399e7bae9e243bcc022afa43d73ad85912b9468b1e3cc73875079576` |
| Both installed lean extensions | `74feaae8a1f52c735a61b94a4abe82daf2f65c4896434aca2b874200ce93a344` |

The child runner asserted each process's own `sys.prefix`, `urllib.parse.__file__`,
extension presence and path, and exact catalog counts and digests. All 120
processes passed: each catalog process completed 1,500 batches of 48 URLs
and 48 keys, with input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and complete output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
The import phase imported `urllib.parse` in every variant and did no catalog
work; it held the process for 120 ms so the external sampler could observe
physical footprint. The command and workload environment were identical
within each phase except for the clone's interpreter path. The runner inferred
the variant from `sys.prefix`.

The cloned stage contained a checked-hash parser pyc with header flags `3`
and source-hash bytes `fcbbd960190070b8`. That matched the original parser
but not the guarded source. Its proper checked hash is
`08e1c2739578432c`. Three cache conditions were measured serially:

1. **Stale candidate cache:** original installed pyc in all three clones;
   only the candidate source hash did not match. This reproduces the prior
   overlay condition.
2. **No parser cache:** removed `parse.cpython-316*.pyc` in all three clones;
   every process compiled its parser source. The first pass and one repeat
   used this condition.
3. **Valid parser cache:** outside measured processes, each clone's Python
   generated its own checked-hash parser pyc with `py_compile`. Header hash
   equality against each clone's source was checked. The control and
   import-only hashes were `fcbbd960190070b8`; candidate was
   `08e1c2739578432c`.

## External memory observations

Each pass used four serial, rotated-order rounds of three variants for the
catalog phase and four more for the import phase: 24 fresh processes per
pass. The same
[`runner`](url-quote-memory-attribution-20260924.py) called the repository's
`benchmarks.harness.process.run_command` with a 10 ms external macOS sampler.
All rows reported one process, no sampling errors, kernel root lifetime peak
RSS, sampled physical footprint, and root `wait4` user/system CPU. The paired
numbers below subtract the same round's control. This is a memory diagnostic;
sampler wall and CPU observations are resource accounting, not a speed test.

| Cache state | Candidate minus control catalog peak RSS, median (range) | Candidate minus control import peak RSS, median | Catalog sampled footprint median |
| --- | ---: | ---: | ---: |
| Stale | +2,777,088 B (+2,244,608 to +3,112,960) | +3,604,480 B | +2,719,732 B |
| Stale repeat | +3,031,040 B (+2,736,128 to +3,129,344) | +3,612,672 B | +3,006,464 B |
| No cache | +65,536 B (−147,456 to +458,752) | +73,728 B | +49,152 B |
| No cache repeat | +114,688 B (−81,920 to +491,520) | −122,880 B | +49,164 B |
| Valid cache | −65,536 B (−131,072 to +16,384) | +81,920 B | −98,304 B |

For comparison, import-only catalog median RSS differences were −131,072,
+98,304, +73,728, +155,648, and −65,536 bytes in the same row order. Its
import-only differences were +163,840, +262,144, +278,528, +163,840, and
+237,568 bytes. Thus simply loading the 50,712-byte extension did not
reproduce the multi-megabyte rise. The stale candidate did reproduce it
before any catalog work. Removing the cache asymmetry removed it even though
the guarded quote path still ran for the complete catalog task. Valid-cache
candidate catalog differences were all within the previous comparison's
437,237-byte local RSS self-noise allowance; one no-cache repeat round was
slightly above that allowance, so these small effects still merit a new
matched qualification rather than a pass claim.

`/usr/bin/time -l` covered each controller and its waited workload children:

| Pass | User + system CPU | Controller command max RSS | Swaps | Workload processes |
| --- | ---: | ---: | ---: | ---: |
| Stale | 8.27 + 0.77 s | 31,424,512 B | 0 | 24 serial, one at a time |
| No cache | 8.37 + 0.77 s | 29,278,208 B | 0 | 24 serial, one at a time |
| Valid cache | 8.12 + 0.68 s | 28,786,688 B | 0 | 24 serial, one at a time |
| Stale repeat | 8.15 + 0.67 s | 29,343,744 B | 0 | 24 serial, one at a time |
| No-cache repeat | 8.52 + 0.74 s | 29,392,896 B | 0 | 24 serial, one at a time |

The five measured commands used 45.06 CPU seconds in total. One failed
controller import setup used 0.05 CPU seconds, and the three external
`py_compile` commands were short; the lane stayed below 50 command CPU
seconds and 1 GiB peak RSS. The controller's maximum RSS is a per-process
maximum, not a sum across processes. Full external sampler results for the
valid-cache pass and both repeats remain ignored as `raw-valid-cache.json`,
`raw-stale-cache-repeat.json`, and `raw-no-cache-repeat.json` under the work
directory. The five committed compact
[`data` files](data/url-quote-memory-attribution-valid-cache-20260924.json)
retain every process's import path, digest, root CPU counters, RSS, footprint,
process count, and paired RSS difference. The first stale and no-cache passes
retain compact rows only because later passes replaced their full sampler
files. Kernel RSS covers the root process lifetime; physical footprint is a
sampled per-PID diagnostic. No exact USS, PSS, allocation, or retained-memory
claim follows, and no timing claim follows from a memory-sampled process.

## Reproduction and next decision

The input clones and generated cache files are ignored work artifacts; the
script preflights all executable, parser, and extension hashes before running.
Use the exact clone and cache states above, run
`python3 rust-cpython/experiments/url-quote-memory-attribution-20260924.py`
from this worktree root, and preserve its generic `raw.json` and compact JSON
before changing cache state. It writes one 24-process pass per invocation.
`PYTHONPATH`, hash seed, user-site exclusion, bytecode-write exclusion, and
allocator settings come from the same `workload_environment(None)` helper as
the prior comparison.

This diagnosis points to an overlay methodology error: replacing source
without regenerating its checked-hash pyc under a no-write benchmark
environment. A source patch build will naturally regenerate cache only if its
install or qualification step does so explicitly; that state must be checked.
Repeat the lean overlay's timing and memory comparison with verified cache
parity and a quiet host before changing the implementation or accepting it.
