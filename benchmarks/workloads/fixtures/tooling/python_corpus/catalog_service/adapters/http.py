"""Transport-neutral request parsing and response construction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from catalog_service.errors import CatalogError, InvalidQueryError
from catalog_service.export import export_page
from catalog_service.model import Page
from catalog_service.query import parse_query


@dataclass(frozen=True, slots=True)
class Request:
    """The subset of an HTTP request consumed by search routes."""

    method: str
    path: str
    query: Mapping[str, str]
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class Response:
    """A complete transport response with deterministic headers."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


def search_request(request: Request, page_factory) -> Response:
    """Validate a request and serialize a page or stable error response."""
    if request.method.upper() != "GET" or request.path != "/search":
        return _json_response(404, {"error": "not found"})
    try:
        plan = parse_query(request.query.get("q", ""))
        offset = _parse_integer(request.query.get("offset", "0"), "offset")
        limit = _parse_integer(request.query.get("limit", "25"), "limit")
        page: Page = page_factory(plan, offset=offset, limit=limit)
    except (CatalogError, ValueError) as error:
        return _json_response(400, {"error": str(error)})
    return _json_response(200, export_page(page))


def decode_json_request(body: bytes) -> Mapping[str, Any]:
    """Decode a JSON object payload and reject scalar top-level values."""
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidQueryError("request body is not valid JSON") from error
    if not isinstance(value, Mapping):
        raise InvalidQueryError("request body must be an object")
    return value


def _parse_integer(value: str, name: str) -> int:
    """Convert a bounded integer parameter into its canonical value."""
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if result < 0 or result > 1_000_000:
        raise ValueError(f"{name} is outside supported bounds")
    return result


def _json_response(status: int, value: Mapping[str, Any]) -> Response:
    """Serialize compact JSON with fixed response headers."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return Response(status, (("content-type", "application/json"),), payload)
