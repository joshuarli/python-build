"""Streaming export formats for catalog query results."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from catalog_service.codec import encode_entry
from catalog_service.model import CatalogEntry, Page, SearchHit
from catalog_service.search import explain


def export_json(entries: Iterable[CatalogEntry]) -> bytes:
    """Encode entries as a sorted compact JSON array."""
    values = [json.loads(encode_entry(entry)) for entry in entries]
    values.sort(key=lambda value: value["id"])
    return json.dumps(values, sort_keys=True, separators=(",", ":")).encode()


def export_csv(entries: Iterable[CatalogEntry]) -> str:
    """Write a stable CSV representation with escaped labels."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=("id", "kind", "title", "revision", "labels", "body"),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for entry in sorted(entries, key=lambda item: item.identifier):
        writer.writerow(
            {
                "id": entry.identifier,
                "kind": entry.kind.value,
                "title": entry.title,
                "revision": entry.revision,
                "labels": "|".join(entry.labels),
                "body": entry.body,
            }
        )
    return output.getvalue()


def export_page(page: Page) -> dict[str, Any]:
    """Return a page response including summaries and pagination metadata."""
    return {
        "items": [explain(hit) for hit in page.items],
        "limit": page.limit,
        "offset": page.offset,
        "total": page.total,
        "has_next": page.has_next,
    }


def iter_json_lines(entries: Iterable[CatalogEntry]) -> Iterator[bytes]:
    """Yield one self-contained encoded record per line."""
    for entry in entries:
        yield encode_entry(entry) + b"\n"


def group_by_kind(entries: Iterable[CatalogEntry]) -> Mapping[str, tuple[CatalogEntry, ...]]:
    """Group entries into a stable kind-to-record mapping."""
    groups: dict[str, list[CatalogEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.kind.value, []).append(entry)
    return {
        kind: tuple(sorted(values, key=lambda item: item.identifier))
        for kind, values in sorted(groups.items())
    }
