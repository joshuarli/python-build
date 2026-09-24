"""Incremental inverted index built from repository snapshots."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from catalog_service.model import CatalogEntry, EntrySnapshot
from catalog_service.tokenizer import terms


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Counts describing one published index generation."""

    generation: int
    documents: int
    unique_terms: int
    total_terms: int


class InvertedIndex:
    """Map terms to entry identifiers and maintain document frequencies."""

    def __init__(self) -> None:
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._entry_terms: dict[str, Counter[str]] = {}
        self._generation = -1

    @property
    def generation(self) -> int:
        """Return the generation the index currently represents."""
        return self._generation

    def rebuild(self, snapshot: EntrySnapshot) -> IndexStats:
        """Replace all index state from a repository snapshot."""
        postings: dict[str, set[str]] = defaultdict(set)
        entry_terms: dict[str, Counter[str]] = {}
        for entry in snapshot.entries:
            counts = Counter(terms(entry.searchable_text))
            entry_terms[entry.identifier] = counts
            for term, count in counts.items():
                if count:
                    postings[term].add(entry.identifier)
        self._postings = postings
        self._entry_terms = entry_terms
        self._generation = snapshot.generation
        return self.stats()

    def add(self, entry: CatalogEntry) -> None:
        """Add terms from a single newly inserted entry."""
        if entry.identifier in self._entry_terms:
            raise ValueError(f"entry already indexed: {entry.identifier}")
        counts = Counter(terms(entry.searchable_text))
        self._entry_terms[entry.identifier] = counts
        for term in counts:
            self._postings[term].add(entry.identifier)

    def remove(self, identifier: str) -> Counter[str]:
        """Remove one entry and discard posting lists that become empty."""
        try:
            counts = self._entry_terms.pop(identifier)
        except KeyError as error:
            raise KeyError(f"entry is not indexed: {identifier}") from error
        for term in counts:
            posting = self._postings[term]
            posting.remove(identifier)
            if not posting:
                del self._postings[term]
        return counts

    def lookup(self, term: str) -> frozenset[str]:
        """Return identifiers containing a normalized term."""
        return frozenset(self._postings.get(term, ()))

    def candidates(self, query_terms: Iterable[str]) -> frozenset[str]:
        """Return the union of postings for a disjunctive query."""
        result: set[str] = set()
        for term in query_terms:
            result.update(self._postings.get(term, ()))
        return frozenset(result)

    def document_frequencies(self) -> dict[str, int]:
        """Return the number of entries containing each term."""
        return {term: len(ids) for term, ids in self._postings.items()}

    def stats(self) -> IndexStats:
        """Calculate index cardinality without mutating its postings."""
        total = sum(sum(counts.values()) for counts in self._entry_terms.values())
        return IndexStats(self._generation, len(self._entry_terms), len(self._postings), total)
