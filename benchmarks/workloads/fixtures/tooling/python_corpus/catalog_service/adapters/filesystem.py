"""Directory adapter that discovers and reads catalog documents."""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from pathlib import Path

from catalog_service.ingest import from_mapping
from catalog_service.model import CatalogEntry, EntryKind
from catalog_service.normalize import content_identifier


_TEXT_TYPES = frozenset({"text/markdown", "text/plain", "application/json"})


def discover(root: Path, *, suffixes: frozenset[str] = frozenset({".md", ".txt", ".json"})) -> Iterator[Path]:
    """Yield regular files in normalized lexical order."""
    for path in sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix()):
        if path.is_file() and path.suffix.casefold() in suffixes:
            yield path


def load_file(path: Path, *, root: Path) -> CatalogEntry:
    """Read a supported text file and derive a relative stable identifier."""
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type not in _TEXT_TYPES:
        raise ValueError(f"unsupported file type: {path.name}")
    body = path.read_text(encoding="utf-8")
    relative = path.relative_to(root).as_posix()
    title = next((line.lstrip("# ").strip() for line in body.splitlines() if line.strip()), path.stem)
    identifier = content_identifier(relative.encode(), namespace="file")
    kind = EntryKind.SOURCE if path.suffix.casefold() in {".md", ".txt"} else EntryKind.DOCUMENT
    return from_mapping({"id": identifier, "title": title, "kind": kind.value, "body": body})


def scan(root: Path) -> tuple[CatalogEntry, ...]:
    """Load every supported file while isolating unreadable inputs."""
    entries = []
    for path in discover(root):
        try:
            entries.append(load_file(path, root=root))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    return tuple(entries)
