# Django first WSGI request boundary

## Contract

`django_wsgi_first_request` measures one complete fresh interpreter process.
The parent prepares a SQLite file once using the same Django models and seed
function as the warm WSGI, ASGI, ORM, and template workloads. It hashes every
byte of that file before the paired run and again after it. The child opens the
file read-only when Django first connects to SQLite. No file copy is made.

Each measured child imports and sets up Django, constructs one `WSGIHandler`,
calls it exactly once, verifies the full response structure and status, hashes
the response body, prints one correctness payload, and exits. The harness uses
external spawn-to-exit duration and kernel `wait4` root CPU. A separate child
provides externally sampled memory. The initial file open, SQLite reads,
response validation, digest computation, and shutdown are inside the timing
boundary. Fixture creation and full-file hashing are outside it. The warm
scenarios retain their own internal intervals.

The fixture digest and timing boundary appear in the result identity. The
response digest is required to match across the fresh processes and both
interpreters. The fixture file is made read-only before any request.

## Validation and resource record

The approved macOS CPython 3.16 Django, asgiref, and sqlparse wheels were
read from the existing cache and reverified by `prepare_site`. The control
interpreter was
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`.
Raw attempts are retained in this lane under
`rust-cpython/work/django-cold-first-20260925/`.

| Attempt | Outcome | Real s | User s | System s | Peak RSS MiB | Swap count |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `01-prepare-site.log` | approved wheels prepared | 1.50 | 0.53 | 0.80 | 35.8 | 0 |
| `02-focused-tests.log` | failed: startup workload needed an explicit process boundary | 6.00 | 4.62 | 0.98 | 80.1 | 0 |
| `03-focused-tests.log` | 9 tests passed | 5.42 | 4.26 | 0.85 | 75.4 | 0 |
| `04-registered-smoke.log` | quick same-interpreter smoke passed | 3.66 | 2.39 | 0.98 | 72.0 | 0 |
| `05-focused-final.log` | 9 tests passed after environment isolation edit | 6.01 | 4.45 | 0.96 | 75.8 | 0 |

`/usr/bin/time -l` reported 20.82 total user plus system CPU seconds across
these five retained commands. Its resource counters cover the command tree;
the harness records the timed workload root separately with `wait4`.
The smoke issued one request per child and produced the same response digest
(`b609c04885f4c3ca00a0535939258e2f5595ee991874540da00d20f0d29806cf`)
for both sides and every pass. The SQLite file was 3,919,872 bytes and had
SHA-256 `3257bc071d043b7d7a67b1f3fe4bf034fc44c73430a0d858abed09ccb2245a30`
before and after requests. Fresh fixture preparations also produced the same
byte hash, and the cold response digest matched the warm WSGI response.

The four uninstrumented same-interpreter timing observations were 0.264 to
0.291 seconds per process. Kernel `wait4` root CPU was 0.236 to 0.263 seconds
per request process. The separate macOS memory passes reported root peak RSS
of 56.7 to 57.2 MB; peak swap bytes were unavailable in those process
samples. The timed children spawned no descendants. This was a correctness
smoke with the same interpreter on both sides, not a performance comparison.
