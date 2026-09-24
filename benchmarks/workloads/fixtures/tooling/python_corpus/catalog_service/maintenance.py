"""Offline consistency checks and index repair operations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from catalog_service.index import InvertedIndex
from catalog_service.model import CatalogEntry, EntrySnapshot
from catalog_service.repository import CatalogRepository
from catalog_service.tokenizer import terms


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Comparison of repository content and derived index state."""

    checked_entries: int
    missing_identifiers: tuple[str, ...]
    extra_identifiers: tuple[str, ...]
    mismatched_terms: tuple[str, ...]

    @property
    def healthy(self) -> bool:
        return not (self.missing_identifiers or self.extra_identifiers or self.mismatched_terms)


def audit(snapshot: EntrySnapshot, index: InvertedIndex) -> AuditReport:
    """Compare exact token postings against one immutable repository view."""
    expected: dict[str, Counter[str]] = {
        entry.identifier: Counter(terms(entry.searchable_text))
        for entry in snapshot.entries
    }
    indexed_ids = set(index._entry_terms)
    expected_ids = set(expected)
    mismatched = tuple(
        sorted(
            identifier
            for identifier in expected_ids & indexed_ids
            if index._entry_terms[identifier] != expected[identifier]
        )
    )
    return AuditReport(
        len(snapshot.entries),
        tuple(sorted(expected_ids - indexed_ids)),
        tuple(sorted(indexed_ids - expected_ids)),
        mismatched,
    )


def repair(repository: CatalogRepository, index: InvertedIndex) -> AuditReport:
    """Rebuild the derived index and return its post-repair audit."""
    snapshot = repository.snapshot()
    index.rebuild(snapshot)
    return audit(snapshot, index)


def duplicate_titles(entries: Iterable[CatalogEntry]) -> dict[str, tuple[str, ...]]:
    """Find normalized title groups with more than one identifier."""
    groups: dict[str, list[str]] = {}
    for entry in entries:
        key = " ".join(entry.title.casefold().split())
        groups.setdefault(key, []).append(entry.identifier)
    return {
        title: tuple(sorted(identifiers))
        for title, identifiers in sorted(groups.items())
        if len(identifiers) > 1
    }
