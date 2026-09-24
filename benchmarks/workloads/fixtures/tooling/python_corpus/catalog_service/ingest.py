"""Batch ingestion and deterministic entry construction."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

from catalog_service.model import CatalogEntry, EntryKind
from catalog_service.normalize import content_identifier, normalize_identifier


@dataclass(frozen=True, slots=True)
class IngestReport:
    """Per-batch counters returned to import callers."""

    accepted: int
    rejected: int
    identifiers: tuple[str, ...]


def from_mapping(record: Mapping[str, object]) -> CatalogEntry:
    """Validate a generic mapping and convert it to a catalog entry."""
    title = str(record.get("title", "")).strip()
    kind = EntryKind(str(record.get("kind", EntryKind.DOCUMENT.value)))
    body = str(record.get("body", ""))
    identifier = str(record.get("id") or content_identifier(body.encode(), namespace=kind.value))
    labels = tuple(str(label) for label in record.get("labels", ()))
    attributes = {
        str(key): str(value)
        for key, value in dict(record.get("attributes", {})).items()
    }
    return CatalogEntry(identifier, title, kind, body, labels, attributes)


def read_json_lines(payload: str) -> Iterator[CatalogEntry]:
    """Yield validated entries from newline-delimited JSON input."""
    for number, line in enumerate(payload.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON on line {number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"expected an object on line {number}")
        yield from (from_mapping(value),)


def read_csv(payload: str) -> Iterator[CatalogEntry]:
    """Yield entries from a CSV document with stable field handling."""
    reader = csv.DictReader(io.StringIO(payload))
    required = {"title", "kind", "body"}
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError("CSV header is missing required fields")
    for row in reader:
        labels = tuple(part.strip() for part in row.get("labels", "").split("|"))
        yield from_mapping({**row, "labels": labels})


def prepare_batch(records: Iterable[Mapping[str, object]]) -> tuple[CatalogEntry, ...]:
    """Normalize a batch and reject duplicate generated identifiers."""
    prepared: dict[str, CatalogEntry] = {}
    for record in records:
        entry = from_mapping(record)
        identifier = normalize_identifier(entry.identifier)
        normalized = CatalogEntry(
            identifier,
            entry.title,
            entry.kind,
            entry.body,
            entry.labels,
            entry.attributes,
            entry.revision,
        )
        if identifier in prepared:
            raise ValueError(f"duplicate identifier in batch: {identifier}")
        prepared[identifier] = normalized
    return tuple(prepared[key] for key in sorted(prepared))


def ingest(records: Iterable[Mapping[str, object]]) -> IngestReport:
    """Build a compact result suitable for a batch import response."""
    entries = prepare_batch(records)
    return IngestReport(len(entries), 0, tuple(entry.identifier for entry in entries))
