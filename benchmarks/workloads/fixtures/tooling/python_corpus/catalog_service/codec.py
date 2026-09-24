"""Canonical JSON encoding and decoding for catalog records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from catalog_service.model import CatalogEntry, EntryKind


def encode_entry(entry: CatalogEntry) -> bytes:
    """Encode one entry with fixed key order and UTF-8 output."""
    payload = {
        "attributes": dict(entry.attributes),
        "body": entry.body,
        "id": entry.identifier,
        "kind": entry.kind.value,
        "labels": list(entry.labels),
        "revision": entry.revision,
        "title": entry.title,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_entry(payload: bytes | str) -> CatalogEntry:
    """Decode a mapping and validate each field through the model type."""
    value = json.loads(payload)
    if not isinstance(value, Mapping):
        raise ValueError("an encoded entry must be a JSON object")
    attributes = value.get("attributes", {})
    if not isinstance(attributes, Mapping):
        raise ValueError("entry attributes must be an object")
    labels = value.get("labels", ())
    if not isinstance(labels, (list, tuple)):
        raise ValueError("entry labels must be an array")
    return CatalogEntry(
        str(value["id"]),
        str(value["title"]),
        EntryKind(str(value["kind"])),
        str(value.get("body", "")),
        tuple(str(label) for label in labels),
        {str(key): str(item) for key, item in attributes.items()},
        int(value.get("revision", 1)),
    )


def canonical_mapping(value: Mapping[str, Any]) -> str:
    """Serialize an arbitrary mapping for signatures and cache keys."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
