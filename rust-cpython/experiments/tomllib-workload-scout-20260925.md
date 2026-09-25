# Public `tomllib` workload scout, 2026-09-25

## Recommendation

**Defer a Rust parser prototype.** A pinned, complete CPython tooling task does
exercise public `tomllib` on a substantial real manifest: `Tools/build/stable_abi.py
--dump` reads and validates `Misc/stable_abi.toml`. Its diagnostic profile puts
the parser on the task's critical path. This is build tooling that validates one
ABI manifest three times, not a representative application metadata workload.
The existing benchmark suite and approved macOS CPython 3.16 package inputs
contain no task that reads a substantial `pyproject.toml` through public
`tomllib`. The next evidence target is a fixed, version-matched application or
packaging task with a pinned meaningful project manifest, a public
`tomllib.load`/`loads` call in its normal path, and an end-to-end output digest.
Profile its cold and warm complete tasks before implementing the parser.

## Workload search and identity

The source pin is Rust-for-CPython CPython commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b` from
`rust-cpython/sources.lock.json`. The accepted guarded URL-quote fork
installation at
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage`
ran this diagnostic. Its `bin/python3.16` SHA-256 is
`622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`.
The extracted script SHA-256 is
`fb7b0d8b7b860884abfe354a88142bdedd107ab7efc5320deea5f3d52faf9323`.
The installed and pinned-source `tomllib/_parser.py` files both have SHA-256
`1eca6101d6135d4ba30573eb2212becb4cea39cb3416f48225a1deeecdd94c4d`.

`stable_abi.py:parse_manifest` calls `tomllib.load` on the pinned
`Misc/stable_abi.toml`; `check_dump` calls `tomllib.loads` on a generated text
round trip and `tomllib.load` on the same file again. The 72,592-byte source
manifest SHA-256 is
`eab726f2482c71e67a23ea04aaa9c5a11d565bee4472320f813262f273c1e966`.
The generated in-memory TOML input has 62,149 bytes and SHA-256
`1a31cb0efe1a0ced81844b455437d9c1d617ab9f7310602ef3522a31ec945509`.
One successful complete task prints 62,150 bytes, SHA-256
`fe05cdfffc22cb80211c08416bfc42dfe0f566a816f93db9b982664c997b455b`.
The direct and cProfile runs produced that exact output digest. Both used
`env -i`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=1`.

The pinned CPython source also has a real `generate_slots.py` caller on a
14,411-byte `Python/slots.toml`, and `stable_abi.py` is the largest direct
public caller found. The benchmark registry has no `tomllib` workload;
pyperformance's selected `tomli_loads` exercises Tomli. The macOS CPython
3.16 approved wheel set is Django, asgiref, and sqlparse only; its registered
Django tasks do not call `tomllib`. The repo controller reads a Cargo manifest
through `tomllib.loads`, but it runs under the host interpreter, outside the
staged CPython candidate. Tiny CPython project manifests remain useful only
as compatibility fixtures. A source and workload search found no larger
version-matched application project metadata task already approved here.

## Complete-task diagnostic attribution

`python3.16 -m cProfile -o ... Tools/build/stable_abi.py --dump` profiled one
cold complete process, including imports, parsing, ABI dataclass construction,
text generation, validation, and output. It recorded 266,381 function calls
and 0.089537 s instrumented function time. These are diagnostic seconds only,
not a speed or CPU verdict. The direct command took 0.10 s wall and 0.07 s
kernel CPU; instrumentation raised those to 0.14 s wall and 0.11 s CPU.

| Disjoint self-time bucket | Seconds | Share of instrumented total |
| --- | ---: | ---: |
| `tomllib` Python frames | 0.047790 | 53.4% |
| `stable_abi.py` Python frames | 0.003693 | 4.1% |
| Other Python frames | 0.011740 | 13.1% |
| Built-in/C frames, including imports, I/O, and scalar operations | 0.026314 | 29.4% |

The three `tomllib.loads` calls accumulated 0.053200 s, or 59.4% of the
instrumented complete task. They include parser callees; their cumulative
time overlaps the two outer `tomllib.load` calls (0.036528 s cumulative), so
those rows must not be added. The two `load` calls also contain file read and
UTF-8 decode. `parse_manifest` accumulated 0.019758 s, and `check_dump`
0.038104 s; those are project phases containing the public parser calls,
not additional disjoint parser time. The self-time buckets above isolate
project logic from parser Python frames. Built-in/C time is not all file I/O:
its largest row is dynamic-module import at 0.007468 s, while all 60
`BufferedReader.read` calls (including import reads) total 0.000392 s self
and two input `open` calls total 0.000204 s self. Input size and triple
validation are specific to this tooling task; neither can be generalized to
other applications. The profile is under the accepted fork and contains no
candidate/control comparison.

## Resource ledger

All substantive attempts ran serially from
`/private/tmp/python-build-exp-tomllib-workload-scout-20260925a`, branch
`exp/tomllib-workload-scout-20260925a`, base `a7be46a`. A process preflight
showed no compiler or benchmark process. Raw stdout, stderr, cProfile data,
summary JSON, and unique `/usr/bin/time -l` records are under ignored
`rust-cpython/work/tomllib-workload-scout-20260925a/`. No substantive attempt
failed; an earlier read-only `ls` queried a nonexistent old worktree path and
did not launch a workload. No test suite, compiler, formatter, linter, hook,
or push ran.

| Attempt | Exit | Wall s | User s | System s | CPU s | Peak RSS bytes | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `direct-dump-1` | 0 | 0.10 | 0.05 | 0.02 | 0.07 | 27,377,664 | 0 |
| `profile-dump-1` | 0 | 0.14 | 0.10 | 0.01 | 0.11 | 28,508,160 | 0 |
| `profile-summary-1` | 0 | 0.05 | 0.02 | 0.01 | 0.03 | 20,709,376 | 0 |
| **Measured total / maximum** | | **0.29** | **0.17** | **0.04** | **0.21** | **28,508,160** | **0** |

`/usr/bin/time -l` covers each complete direct process; these commands spawn
no child processes, so it covers their process trees. RSS is lifetime peak,
not unique or retained memory. Read-only searches and hash checks were short
and unmetered, so 0.21 s is the total for recorded substantive commands, not
a claim about every inspection command. No per-process RSS approached the
512 MiB cap, and measured CPU stayed below the 30-second lane budget.
