# Public small Base64 route: stop

The pinned Rust-for-CPython 3.16 fork exports `_base64.standard_b64encode(s)`.
It accepts a contiguous buffer through `PyBUF_SIMPLE` and writes standard,
padded, unwrapped Base64 bytes. Public `base64.b64encode(s, altchars=None,
*, padded=True, wrapcol=0)` calls `binascii.b2a_base64`. The Rust entry point
does not implement alternate alphabets, omitted padding, or wrapping. Both
functions matched for the probed `bytes`, `bytearray`, and contiguous
`memoryview` inputs and raised the same `BufferError` for a strided view.

The [probe](base64_public_probe.py) models a route restricted to exact `bytes`
up to 256 bytes, `altchars is None`, `padded is True`, and an exact integer
zero `wrapcol`. It also checks at call time that `binascii.b2a_base64` is the
function captured at import, so a later replacement follows the existing
public path. A source patch would additionally need to decline routing when
that function had been replaced before import. The probe makes no source
change. Its `guarded` function calls Rust for eligible inputs and the original
public function for every other input. The `public` arm calls the installed
`base64.b64encode` directly; `rust` and `binascii` arms call their native
functions directly. The catalog arm encodes 20,000 distinct 32-byte records,
adds record numbers and newlines, concatenates the result, and hashes it. Both
catalog arms produced SHA-256
`3622e2ae535ee70a05e66f7cb29c85a0b0fe74ff3ee910f5b967793bdcc688a9`.

Run from this repository with the staged Rust interpreter:

```sh
/usr/bin/time -l /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 -I -S -B rust-cpython/experiments/base64_public_probe.py > rust-cpython/experiments/data/base64-public-loaded-diagnostic-20260925.json 2> rust-cpython/experiments/data/base64-public-loaded-diagnostic-20260925.resource.txt
```

The staged `base64.py` SHA-256 was
`93319e370390777e2b0a14dcb02b53d61e1bc83719c088e760eb5ab74eafa978`;
the `_base64` extension SHA-256 was
`3620100ade27872aa7e3281caf0aa85ff98e0e0a7205286c5a0b83031c030306`.
The [raw observations](data/base64-public-loaded-diagnostic-20260925.json)
contain three alternating size-sweep rounds, five alternating catalog pairs,
and five alternating cold-process import pairs. `process_time_ns` gives
process user plus system CPU for individual in-process operations;
`getrusage(RUSAGE_CHILDREN)` gives kernel-accounted user and system CPU for
each cold import subprocess. Wall time uses `perf_counter_ns`. `time -l`
measured the enclosing process tree.

| Input | Public median CPU/call | Guarded median CPU/call | Guarded change |
| --- | ---: | ---: | ---: |
| 32 bytes | 121.73 ns | 134.14 ns | +10.2% |
| 64 bytes | 124.95 ns | 150.25 ns | +20.2% |
| 128 bytes | 156.55 ns | 186.85 ns | +19.4% |

The five catalog guarded/public CPU ratios were 1.047, 1.076, 1.046, 1.071,
and 1.067 (median 1.067); the wall ratios were 1.047, 1.078, 1.044, 1.068,
and 1.073 (median 1.068). Cold `import base64, _base64` versus `import base64`
added a median 0.388 ms user CPU and 0.210 ms system CPU across five
subprocess pairs. The direct Rust 64-byte call remained faster than the
direct C call in this diagnostic, but the required public guard spent more
than that gain.

OrbStack's unrelated container used about 305% CPU during this run. These
timings are loaded-host diagnostics, not a publishable speed comparison.
The enclosing command used 3.00 user + 0.08 system CPU seconds, peaked at
33,226,752 bytes RSS and 20,775,416 bytes footprint, and reported zero
process swaps. Host swap usage was 243.88 MiB before and after. This pass
does not attribute peak memory to an individual arm or count allocations.

**Decision: reject the public small-input route and make no source patch.**
The required guard slowed all measured small public calls and the complete
catalog; importing the Rust extension adds cold cost. The existing direct
Rust result remains a kernel observation, with no demonstrated public gain.
No CPython test suite, full build, formatter, linter, or hook ran in this lane.
