"""Complete search-form and request-path tasks using the fixed catalog batch.

One operation processes all 48 records. The existing catalog normalization
task stays in catalog_url, so its import path retains the same startup cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from typing import Callable, Protocol
from urllib.parse import parse_qsl, quote_from_bytes, unquote_to_bytes, urlencode, urlsplit, urlunsplit
from urllib.request import Request

from .catalog_url import WorkloadError, _EXPECTED_INPUT, _batch, _digest


_EXPECTED_SEARCH_OUTPUT = "a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22"
_EXPECTED_PATH_OUTPUT = "52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff"

CatalogBatch = tuple[tuple[str, tuple[str, ...]], ...]
TaskResult = dict[str, int | float | str]


class _Digest(Protocol):
    def update(self, data: bytes) -> None: ...


def _frame_count(digest: _Digest, count: int) -> None:
    digest.update(count.to_bytes(4, "big"))


def _frame_value(digest: _Digest, value: str | bytes) -> None:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)


def _checked_batch() -> tuple[CatalogBatch, str]:
    batch = _batch()
    input_digest = _digest(tuple((url, *parts) for url, parts in batch))
    if input_digest != _EXPECTED_INPUT:
        raise WorkloadError(f"catalog URL input changed: {input_digest}")
    return batch, input_digest


def _search_form_batch(batch: CatalogBatch) -> str:
    """Frame every request URL, query, and ordered parsed pair in the batch."""
    digest = hashlib.sha256()
    _frame_count(digest, len(batch))
    for url, parts in batch:
        query = urlencode((("url", url), ("part", parts),
                           ("return", "café / search")), doseq=True)
        request = Request("https://catalog.example/search?" + query)
        pairs = parse_qsl(request.full_url.partition("?")[2], keep_blank_values=True)
        expected = [("url", url), *(("part", part) for part in parts),
                    ("return", "café / search")]
        if pairs != expected:
            raise WorkloadError(f"search form round trip changed: {pairs!r}")
        _frame_count(digest, 2)
        _frame_value(digest, request.full_url)
        _frame_value(digest, query)
        _frame_count(digest, len(pairs))
        for name, value in pairs:
            _frame_count(digest, 2)
            _frame_value(digest, name)
            _frame_value(digest, value)
    return digest.hexdigest()


def _request_path_batch(batch: CatalogBatch) -> str:
    """Frame each rebuilt request target and its original decoded path bytes."""
    digest = hashlib.sha256()
    _frame_count(digest, len(batch))
    for url, _parts in batch:
        split = urlsplit(url.strip())
        path_bytes = unquote_to_bytes(split.path)
        quoted_path = quote_from_bytes(path_bytes, safe=b"/")
        rebuilt = urlunsplit((split.scheme, split.netloc, quoted_path,
                              split.query, split.fragment))
        rebuilt_split = urlsplit(rebuilt)
        if unquote_to_bytes(rebuilt_split.path) != path_bytes:
            raise WorkloadError(f"request path round trip changed: {url!r}")
        _frame_count(digest, 2)
        _frame_value(digest, rebuilt)
        _frame_value(digest, path_bytes)
    return digest.hexdigest()


_BATCH_TASKS: dict[str, tuple[Callable[[CatalogBatch], str], str]] = {
    "catalog_search_form": (_search_form_batch, _EXPECTED_SEARCH_OUTPUT),
    "catalog_request_path": (_request_path_batch, _EXPECTED_PATH_OUTPUT),
}


def _url_task(iterations: int, task: str) -> TaskResult:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    try:
        run_batch, expected = _BATCH_TASKS[task]
    except KeyError as error:
        raise ValueError(f"unknown catalog URL breadth task: {task}") from error
    batch, input_digest = _checked_batch()
    started = time.perf_counter()
    for _ in range(iterations):
        output_digest = run_batch(batch)
        if output_digest != expected:
            raise WorkloadError(f"{task} output changed: {output_digest}")
    elapsed = time.perf_counter() - started
    result: TaskResult = {
        "operation_count": iterations, "digest": output_digest,
        "input_digest": input_digest, "elapsed_seconds": elapsed,
        "records_per_operation": len(batch),
    }
    if task == "catalog_search_form":
        result.update(query_encodes_per_operation=48, requests_per_operation=48,
                      parses_per_operation=48, parsed_pairs_per_operation=240,
                      parsed_fields_per_operation=480,
                      quote_plus_calls_per_operation=480)
    else:
        result.update(splits_per_operation=96, byte_unquotes_per_operation=96,
                      quotations_per_operation=48, unsplits_per_operation=48,
                      path_checks_per_operation=48)
    return result


def catalog_search_form(iterations: int) -> TaskResult:
    """Build and parse 48 outbound catalog search requests per operation."""
    return _url_task(iterations, "catalog_search_form")


def catalog_request_path(iterations: int) -> TaskResult:
    """Canonicalize and check 48 request paths per operation."""
    return _url_task(iterations, "catalog_request_path")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=tuple(_BATCH_TASKS))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    scenarios = {"catalog_search_form": catalog_search_form,
                 "catalog_request_path": catalog_request_path}
    try:
        result = scenarios[args.scenario](args.iterations)
    except WorkloadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
