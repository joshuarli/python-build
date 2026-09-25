# Django query decoding breadth scout, 2026-09-25

## Recommendation

**Defer this as a performance gate; keep one warm WSGI query request as a useful application correctness check if the URL decoder is promoted.** A query-bearing Django request can reach public `urllib.parse.parse_qsl` and then `unquote_plus`/`unquote` through `request.GET`. The existing benchmark does not: both WSGI and ASGI exchanges send an empty query, and `post_detail` never accesses `request.GET`. Merely adding `QUERY_STRING` or ASGI `query_string` would not establish decoder coverage because query parsing is lazy.

The likely complete-request timing signal is small. A realistic post-detail query has only a handful of escaped values, while this view performs a SQLite lookup, related-object prefetches, JSON construction, and response handling. The existing warm and cold WSGI comparisons did not resolve a gain from the quote patch within their same-interpreter noise. The much larger search-form decoder result came from **182** eligible fields per 48-record batch, not one ordinary request. Do not multiply a query artificially until the native cost dominates and call that representative Django speed evidence. A warm WSGI request is the least costly framework boundary for a diagnostic; ASGI scheduling and cold startup add more unrelated work.

## One fixed request and expected result

Use the already seeded `post-00007` fixture and the existing `post_detail` route. The proposed WSGI request is:

```text
GET /posts/post-00007/?highlight=C%2B%2B+%26+Python&tag=Python+%26+tools&tag=Unicode+caf%C3%A9&ref=weekly%2F2026-09-25 HTTP/1.1
Host: testserver
Accept: application/json
```

Set WSGI `PATH_INFO` to `/posts/post-00007/` and `QUERY_STRING` to the exact ASCII bytes after `?`, represented as the WSGI Latin-1 string. Leave the established host, method, headers, and fixture unchanged. Make the view consume `request.GET` and add a `query` object to the JSON response with `highlight = request.GET.get("highlight")`, `tags = request.GET.getlist("tag")`, and `ref = request.GET.get("ref")`. Require the decoded values to be exactly `"C++ & Python"`, `["Python & tools", "Unicode café"]`, and `"weekly/2026-09-25"`, respectively. Keep the existing post, tags, comments, and canonical URL checks. Hash the **complete response body bytes** with SHA-256 and require the same digest for every request and both interpreters; establish its fixed literal from the control implementation only after the view change. Also verify the prepared SQLite file's existing complete SHA-256 before and after the paired run.

The four query values contain `%` and are ASCII `str` inputs to public `unquote` with the normal UTF-8 replacement settings; their field names are plain ASCII and take the no-percent exit. The `+` characters exercise `unquote_plus` before percent decoding. The Unicode value is percent encoded on the wire, so it is still ASCII at the native guard. This is a proposal based on the documented `QueryDict`/`parse_qsl` path; the exact pinned Django 6.1.1 wheel source was not present in this worktree for an independent static identity check. Before treating the request as decoder coverage, inspect the prepared pinned wheel's `django/http/request.py` and count actual eligible native calls outside the timed interval. If that version uses another decoder or the view does not force `request.GET`, reject the workload for this purpose.

## Measurement boundary and value

For a possible later comparison, prepare and hash the same fixture and verified Django 6.1.1, asgiref 3.12.1, and sqlparse 0.6.0 wheels outside timing. Reuse a constructed `WSGIHandler` and the existing warm WSGI exchange; each measured operation is one complete request through Django and response iteration. Compare the quote-only control with the otherwise matched optional unquote candidate on the same quiet host. Keep response validation and digest calculation outside the internal request interval, as the current warm workload does. Use separate complete-process wall/CPU and memory passes, matched valid parser bytecode caches, and control/control noise. A cold first-request result, if collected, is a separate startup and SQLite-open question, not a substitute for the warm request.

The request adds application breadth because it checks Django's lazy `QueryDict`, duplicate-key ordering, `+` handling, UTF-8 percent decoding, and full JSON output using byte-pinned dependencies and the established fixture. It also checks that the native fast path participates in an actual framework request rather than only direct `parse_qsl` calls. Four eligible value decodes make a large timing result implausible without evidence; a null timing result would still be useful correctness evidence but would not contradict the catalog search-form gain.

## Inspection limits

This lane read repository instructions, the Django lock and fixture records, the WSGI/ASGI workload and view, the URL decoder proof and contract audit, and the prior Django comparison. No source, workload, tests, benchmark, compiler, or network command ran. Read-only file searches and reads were short and were not separately instrumented; no substantial CPU or memory usage was observed or claimed. No formatter, linter, or hook ran.
