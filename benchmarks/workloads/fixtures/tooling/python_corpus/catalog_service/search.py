"""Search orchestration, filtering, ranking, and pagination."""

from __future__ import annotations

from collections.abc import Iterable

from catalog_service.index import InvertedIndex
from catalog_service.model import CatalogEntry, Page, SearchHit
from catalog_service.query import SearchPlan
from catalog_service.rank import rank_entries


def search(
    entries: Iterable[CatalogEntry],
    index: InvertedIndex,
    plan: SearchPlan,
    *,
    offset: int = 0,
    limit: int = 25,
) -> Page:
    """Filter indexed candidates, score them, and return one page."""
    if offset < 0 or limit < 1:
        raise ValueError("offset must be nonnegative and limit positive")
    entry_map = {entry.identifier: entry for entry in entries}
    identifiers = index.candidates(plan.positive_terms)
    candidates = [entry_map[key] for key in identifiers if key in entry_map]
    if plan.kinds:
        candidates = [entry for entry in candidates if entry.kind.value in plan.kinds]
    negative = set(plan.negative_terms)
    candidates = [
        entry
        for entry in candidates
        if not any(term in entry.searchable_text.casefold() for term in negative)
    ]
    ranked = rank_entries(
        candidates,
        plan.positive_terms,
        index.document_frequencies(),
        len(entry_map),
    )
    page = ranked[offset : offset + limit]
    return Page(page, len(ranked), offset, limit)


def explain(hit: SearchHit) -> dict[str, object]:
    """Create a serializable score explanation for a search result."""
    return {
        "identifier": hit.entry.identifier,
        "kind": hit.entry.kind.value,
        "score": round(hit.score, 8),
        "matched_terms": list(hit.matched_terms),
        "excerpt": hit.excerpt,
    }
