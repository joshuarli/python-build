# Complete URL breadth workloads, 2026-09-24

## Workloads and contract

`benchmarks.workloads.catalog_url_breadth` exposes two package-free, registered
operations beside `catalog_url_normalize`. It imports the unchanged 48-record
`catalog_url._batch()` and its digest helpers; the original workload module
retains its previous imports and CLI. Each operation processes the batch once.
The batch input SHA-256 remains
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`.
The workload checks it before timing. Neither task makes a network request.

| Scenario | Work per operation | Complete output SHA-256 |
| --- | --- | --- |
| `catalog_search_form` | 48 `urlencode` calls, 48 `Request` objects, 48 `parse_qsl` calls, 240 parsed pairs (480 individual fields), 480 `quote_plus` calls through `urlencode` | `a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22` |
| `catalog_request_path` | 96 `urlsplit` calls, 96 `unquote_to_bytes` calls, 48 `quote_from_bytes` calls, 48 `urlunsplit` calls, 48 decoded path checks | `52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff` |

The search task uses five ordered query pairs per record: `url`, three
`part` values, and `return`. It checks every parsed pair against those source
values, including empty values. Its digest includes the complete
`Request.full_url`, encoded query, and every ordered name/value pair. The path
task decodes the input path to bytes, quotes with `safe=b"/"`, rebuilds the URL
with the original query and fragment, and checks the rebuilt path decodes to
the same bytes. Its digest includes each rebuilt URL and decoded path bytes.
Both SHA-256 streams frame the record count, each record's field count, every
pair count, each pair's field count, and each UTF-8 or byte payload length.
The checks and hashing run on every iteration.

Readable edge examples from the accepted control:

- Malformed escapes: the search request contains
  `url=https%3A%2F%2Fexample.org%2F%252f%2F%25ZZ%2F%25%3Fbad%3D%25G1%23%25`;
  the rebuilt path URL is `https://example.org///%25ZZ/%25?bad=%G1#%`, and
  its decoded path is `b'///%ZZ/%'`.
- Unicode path: the rebuilt URL is
  `https://example.org/%E6%97%A5%E6%9C%AC%E8%AA%9E/na%C3%AFve?tag=é#東京`;
  the decoded path bytes are
  `b'/\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e/na\xc3\xafve'`.

## Correctness evidence

The fixed digests were first computed with the last accepted Rust fork stage
at `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`. The narrow
`benchmarks.tests.test_catalog_url_workload` module passed five tests on that
stage and the patched stage at
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`.
Both stages returned the same complete digests for each task on one and two
iterations. The existing catalog task also passed. `PYTHONPATH=.` and
`PYTHONDONTWRITEBYTECODE=1` were set for these checks.

An untimed diagnostic wrapped the patched stage's
`_rust_url_quote.quote_bytes` entry point for one complete batch. It counted
182 native helper calls for search form creation and 32 for request path
canonicalization while the complete digests remained equal to the control.
These are actual calls beyond the parser's fast exits, not all public quote
calls. No diagnostic wrapper runs in the workload itself.

This lane adds workload definitions and correctness evidence only. It does
not include timing, memory, allocation, import startup, long-input threshold,
or upstream comparisons. Those require the quiet-host comparison described
in `url-quote-breadth-audit-20260924.md`.
