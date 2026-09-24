# URL quotation workload breadth audit, 2026-09-24

## Scope and recommendation

This is a static workload proposal. No build, benchmark, or new fixture was
run. The installed candidate has already improved the registered
`catalog_url_normalize` batch, but that batch puts most eligible calls in
`stable_key`. Add the two complete tasks below before treating the result as
representative of URL creation more broadly. Both use the exact 48 records in
`benchmarks.workloads.catalog_url._batch()`; its input digest is
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`.
The 36 distinct and 12 repeated records contain Unicode, spaces, reserved
characters, malformed escapes, credentials, long components, and ordinary
ASCII. They need no package or network service.

The patch in `rust-cpython/patches/0001-rust-url-quote.patch` calls the native
helper only after `quote_from_bytes` validation, `safe` normalization, and
the empty/already-safe exits. It requires exact `bytes` for both input and
normalized `safe`, and fewer than 200,000 input bytes. A workload must count
calls **past those exits**, not merely calls to `quote` or `quote_from_bytes`.
The catalog diagnostic counted 96 helper-eligible calls of 150
`quote_from_bytes` calls per batch; that is evidence for the existing batch,
not an estimated rate for either new task.

## Candidate complete tasks

| Task | One logical operation | Public route and expected guard reach |
| --- | --- | --- |
| Search form query and request creation | For each of the 48 `(url, parts)` records, build `urlencode((("url", url), ("part", parts), ("return", "café / search")), doseq=True)`, attach it to `https://catalog.example/search?` with `urllib.request.Request`, and parse its query with `parse_qsl(keep_blank_values=True)`. This is 48 query encodes, 48 request objects, 48 parses, and 240 decoded name/value fields per batch. | `urlencode` calls the public `quote_plus` path for five values and their five names per record: 480 `quote_plus` calls per batch. Its ordinary `str` values become exact UTF-8 `bytes` in `quote`, and `safe` becomes exact `bytes` in `quote_from_bytes`. The URL values, Unicode/reserved parts, and fixed return value contain bytes requiring quoting. Names and plain values normally take the already-safe exit. Count actual helper hits before timing; do not label all 480 as hits. |
| Request path canonicalization | For each of the same 48 URLs, run `urlsplit(url.strip())`, `unquote_to_bytes(split.path)`, `quote_from_bytes(path_bytes, safe=b"/")`, and `urlunsplit((split.scheme, split.netloc, quoted_path, split.query, split.fragment))`. Finally parse the result and check that `unquote_to_bytes` of its path equals the original `path_bytes`. This is 96 splits, 96 byte unquotes, 48 quotations, 48 unsplits, and 48 round-trip path checks per batch. | `unquote_to_bytes` returns exact `bytes`; the literal `safe` is exact `bytes`. Decoded non-ASCII paths and literal/malformed percent signs proceed beyond the already-safe exit and have lengths far below 200,000. Plain paths, including the long ASCII `p` path, exercise the existing fast exit. Count actual hits and fallbacks; preserve the mixed distribution. |

The first task represents building outbound search links or form submissions;
the second represents accepting and canonicalizing request targets while
preserving path bytes. They exercise different public callers and different
`safe` values. They also retain parsing, object creation, and validation costs
in the measured task, so a native scanning win has to matter to a complete
operation. The first task's `parts` tuples each contain three strings in the
current fixed batch, hence five encoded values per record. The second task
deliberately preserves the source URL's existing query and fragment rather
than silently changing their escaping rules. Neither task makes an HTTP
request.

For each task, verify the existing batch input digest before measurement.
Length-frame and SHA-256 **every** ordered result, including the 12 repeated
records: for the form task include `Request.full_url`, the complete encoded
query, and every ordered parsed `(name, value)` pair; for the path task include
the reconstructed URL and decoded path bytes. Frame the record count, each
field count, each byte length, and each UTF-8/byte payload so concatenation
cannot alias different outputs. Compute one fixed expected output digest from
the unchanged no-Rust control, check the candidate against it on every batch,
and retain both the digest and a few readable edge results in the workload
record. Also assert the form parse reproduces exactly `url`, three ordered
`part` values, and `return`, with no omitted empty values. A digest alone
cannot explain a semantic mismatch.

## Regression sentinels

Run a fresh-process `import urllib.parse` task without URL work. Capture
external startup-plus-import wall and kernel user/system CPU, lifetime peak
RSS, and sampled footprint in a separate memory pass. The patch eagerly
imports `_rust_url_quote`, so this task can regress even when complete URL
work improves. Before any comparison, check each installed interpreter and
parser path, source hash, candidate extension identity, and valid per-source
`parse.pyc` header; the earlier stale checked-hash cache added about 3 MB
of apparent import RSS. Use the same cache policy and environment on both
sides.

As a bounded fallback check, use the existing long path/query record's bytes
as a repeated source to make three exact input lengths: 199,999, 200,000,
and 200,001 bytes. Call public `quote_from_bytes(data, safe=b"/")` once per
case, compare complete output digests and decoded-byte round trips with the
control, and record peak memory separately. Ensure an unsafe source byte is
present, so the already-safe exit does not mask the threshold. The first
length may use the helper; the latter two must use CPython's chunked fallback.
Keep this an edge and memory sentinel, not a heavily repeated speed score:
quoting and hashing up to roughly 600 KB of output per call can dominate a
small process and has a different allocation shape from ordinary URL work.

## Minimum quiet-host evidence for a breadth verdict

1. Confirm the unchanged `test_urlparse` and `test_urllib` plus the existing
   differential public cases still pass on the fully installed candidate.
   Run a pass-through counter outside timing to report `quote_from_bytes`
   calls, exact-byte inputs, already-safe exits, helper-eligible calls,
   200,000-byte fallbacks, and error/round-trip checks for each new task.
2. On one quiet host, compare the last accepted fork control and patched
   candidate serially with counterbalanced pairs. Calibrate each side against
   itself first. Use at least five uninstrumented timing pairs after the noise
   gate is met. Report external wall plus actual kernel user and system CPU
   per complete batch; these tasks spawn no children, so root accounting
   covers them. Preserve raw observations and per-task ratios. Repeat a close
   result when its direction is within self-comparison noise.
3. Use a separate external memory pass with at least three pairs, recording
   lifetime peak RSS, sampled footprint, process count, sample coverage, and
   swap. Measure fresh import separately from steady batches. The current
   macOS observer does not provide whole-tree USS/PSS or a compatible native
   allocation count, so these data cannot establish upstream memory parity.
   Report installed extension and interpreter bytes separately.
4. Keep the already registered catalog task visible beside these two tasks.
   Compare each task individually with a matched upstream CPython 3.16
   control once available; the installed fork-to-fork result alone cannot
   settle the upstream resource gate. Use equal source/bytecode-cache policy,
   fixture digest, operation count, compiler/PGO settings, and public outputs
   before interpreting a speed difference. Avoid concurrent builds and the
   active upstream comparison on the same host.

The existing catalog installed-build comparison found a 0.823 median wall
ratio and a 0.821 median root CPU ratio for 1,500 complete batches. Its
three-pair median peak-RSS difference was +294,912 bytes, within local
self-noise; unique/proportional memory and allocation parity remain open.
Those results motivate breadth checks but do not predict their outcome.
