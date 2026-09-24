"""Immutable values exchanged by the catalog service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class EntryKind(str, Enum):
    """Supported kinds of records stored by the catalog."""

    DOCUMENT = "document"
    IMAGE = "image"
    PACKAGE = "package"
    SOURCE = "source"


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """A normalized, searchable record with stable identity."""

    identifier: str
    title: str
    kind: EntryKind
    body: str = ""
    labels: tuple[str, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)
    revision: int = 1

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("identifier must not be empty")
        if self.revision < 1:
            raise ValueError("revision must be positive")
        normalized_labels = tuple(sorted({label.casefold() for label in self.labels}))
        object.__setattr__(self, "labels", normalized_labels)
        object.__setattr__(self, "attributes", dict(sorted(self.attributes.items())))

    @property
    def searchable_text(self) -> str:
        """Return all human-readable fields in the order used by indexing."""
        fields = (self.title, self.body, *self.labels, *self.attributes.values())
        return " ".join(value for value in fields if value)


@dataclass(frozen=True, slots=True)
class EntrySnapshot:
    """A value object describing one repository generation."""

    generation: int
    entries: tuple[CatalogEntry, ...]

    def by_identifier(self) -> dict[str, CatalogEntry]:
        """Build an identifier map without changing snapshot ordering."""
        return {entry.identifier: entry for entry in self.entries}


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One ranked search result and its explanation data."""

    entry: CatalogEntry
    score: float
    matched_terms: tuple[str, ...]
    excerpt: str


@dataclass(frozen=True, slots=True)
class Page:
    """A stable slice of a larger result set."""

    items: tuple[SearchHit, ...]
    total: int
    offset: int
    limit: int

    @property
    def has_next(self) -> bool:
        return self.offset + len(self.items) < self.total
