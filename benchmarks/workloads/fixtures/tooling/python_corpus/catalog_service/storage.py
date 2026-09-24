"""Atomic filesystem storage for immutable catalog snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from catalog_service.codec import decode_entry, encode_entry
from catalog_service.errors import StorageError
from catalog_service.model import CatalogEntry, EntrySnapshot


def write_snapshot(path: Path, snapshot: EntrySnapshot) -> None:
    """Write a compact JSON snapshot using replace-on-success semantics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "generation": snapshot.generation,
        "entries": [json.loads(encode_entry(entry)) for entry in snapshot.entries],
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as error:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise StorageError(f"could not write snapshot: {path}") from error


def read_snapshot(path: Path) -> EntrySnapshot:
    """Load one snapshot and validate its entries before returning it."""
    try:
        document = json.loads(path.read_bytes())
        generation = int(document["generation"])
        entries = tuple(decode_entry(item) for item in document["entries"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise StorageError(f"could not read snapshot: {path}") from error
    identifiers = [entry.identifier for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        raise StorageError("snapshot contains duplicate identifiers")
    return EntrySnapshot(generation, entries)


def merge_snapshots(snapshots: Iterable[EntrySnapshot]) -> EntrySnapshot:
    """Merge entries by identifier, preferring the highest revision."""
    chosen: dict[str, CatalogEntry] = {}
    generation = 0
    for snapshot in snapshots:
        generation = max(generation, snapshot.generation)
        for entry in snapshot.entries:
            current = chosen.get(entry.identifier)
            if current is None or entry.revision > current.revision:
                chosen[entry.identifier] = entry
    ordered = tuple(chosen[key] for key in sorted(chosen))
    return EntrySnapshot(generation, ordered)
