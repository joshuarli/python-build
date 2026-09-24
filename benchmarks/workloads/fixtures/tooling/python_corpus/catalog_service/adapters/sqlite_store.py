"""SQLite adapter with schema migration and batched upserts."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from catalog_service.codec import decode_entry, encode_entry
from catalog_service.model import CatalogEntry


_SCHEMA_VERSION = 2
_CREATE_ENTRIES = """
CREATE TABLE IF NOT EXISTS catalog_entries (
    identifier TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload BLOB NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class SQLiteStore:
    """Persist encoded records with explicit transaction boundaries."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self) -> None:
        """Create current tables and reject databases from newer versions."""
        with self._connection:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise RuntimeError("database schema is newer than this adapter")
            self._connection.execute(_CREATE_ENTRIES)
            self._connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")

    def upsert_many(self, entries: Iterable[CatalogEntry]) -> int:
        """Write a batch through one transaction and report affected rows."""
        records = [
            (entry.identifier, entry.kind.value, entry.revision, encode_entry(entry))
            for entry in entries
        ]
        statement = """
        INSERT INTO catalog_entries(identifier, kind, revision, payload)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(identifier) DO UPDATE SET
          kind=excluded.kind,
          revision=excluded.revision,
          payload=excluded.payload,
          updated_at=CURRENT_TIMESTAMP
        WHERE excluded.revision >= catalog_entries.revision
        """
        with self._connection:
            cursor = self._connection.executemany(statement, records)
        return cursor.rowcount

    def get(self, identifier: str) -> CatalogEntry | None:
        """Decode one record or return None when the key is absent."""
        row = self._connection.execute(
            "SELECT payload FROM catalog_entries WHERE identifier=?", (identifier,)
        ).fetchone()
        return decode_entry(row["payload"]) if row is not None else None

    def iterate(self, *, kind: str | None = None) -> tuple[CatalogEntry, ...]:
        """Read records in identifier order, optionally filtering by kind."""
        if kind is None:
            rows = self._connection.execute(
                "SELECT payload FROM catalog_entries ORDER BY identifier"
            )
        else:
            rows = self._connection.execute(
                "SELECT payload FROM catalog_entries WHERE kind=? ORDER BY identifier",
                (kind,),
            )
        return tuple(decode_entry(row[0]) for row in rows)

    def close(self) -> None:
        """Close the underlying database handle."""
        self._connection.close()
