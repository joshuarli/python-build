"""Thread-safe in-memory repository with snapshot transactions."""

from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from catalog_service.errors import DuplicateEntryError, EntryNotFoundError, TransactionError
from catalog_service.model import CatalogEntry, EntrySnapshot


@dataclass(slots=True)
class _Transaction:
    generation: int
    entries: dict[str, CatalogEntry]
    dirty: bool = False


class CatalogRepository:
    """Coordinate immutable entries and monotonically increasing snapshots."""

    def __init__(self, entries: Iterable[CatalogEntry] = ()) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, CatalogEntry] = {}
        self._generation = 0
        for entry in entries:
            self.insert(entry)

    @property
    def generation(self) -> int:
        """Return the current repository generation under its lock."""
        with self._lock:
            return self._generation

    def insert(self, entry: CatalogEntry) -> None:
        """Insert one unique identifier and advance the generation."""
        with self._lock:
            if entry.identifier in self._entries:
                raise DuplicateEntryError(entry.identifier)
            self._entries[entry.identifier] = entry
            self._generation += 1

    def replace(self, entry: CatalogEntry) -> None:
        """Replace an existing identifier with its next revision."""
        with self._lock:
            current = self._entries.get(entry.identifier)
            if current is None:
                raise EntryNotFoundError(entry.identifier)
            if entry.revision <= current.revision:
                raise TransactionError("replacement revision must increase")
            self._entries[entry.identifier] = entry
            self._generation += 1

    def remove(self, identifier: str) -> CatalogEntry:
        """Remove and return an entry, raising for an unknown identifier."""
        with self._lock:
            try:
                entry = self._entries.pop(identifier)
            except KeyError as error:
                raise EntryNotFoundError(identifier) from error
            self._generation += 1
            return entry

    def get(self, identifier: str) -> CatalogEntry:
        """Return one entry by identifier."""
        with self._lock:
            try:
                return self._entries[identifier]
            except KeyError as error:
                raise EntryNotFoundError(identifier) from error

    def snapshot(self) -> EntrySnapshot:
        """Copy entries into a stable, identifier-sorted value."""
        with self._lock:
            ordered = tuple(self._entries[key] for key in sorted(self._entries))
            return EntrySnapshot(self._generation, ordered)

    @contextmanager
    def transaction(self) -> Iterator[dict[str, CatalogEntry]]:
        """Yield an isolated mapping and atomically publish its changes."""
        with self._lock:
            original = self._entries
            working = dict(original)
            transaction = _Transaction(self._generation, working)
            try:
                yield transaction.entries
                if transaction.entries != original:
                    self._entries = transaction.entries
                    self._generation = transaction.generation + 1
            except Exception:
                self._entries = original
                raise

    def __iter__(self) -> Iterator[CatalogEntry]:
        """Iterate over one immutable snapshot."""
        return iter(self.snapshot().entries)
