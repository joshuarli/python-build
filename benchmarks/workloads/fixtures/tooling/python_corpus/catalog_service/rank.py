"""Term weighting and stable hit ordering for catalog search."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from catalog_service.model import CatalogEntry, SearchHit
from catalog_service.tokenizer import frequencies, terms


@dataclass(frozen=True, slots=True)
class RankConfig:
    """Tunable but deterministic scoring constants."""

    title_weight: float = 3.0
    label_weight: float = 2.0
    body_weight: float = 1.0
    exact_phrase_bonus: float = 1.5
    minimum_score: float = 0.0


def inverse_document_frequency(document_count: int, containing_count: int) -> float:
    """Calculate a smoothed positive IDF score."""
    if document_count < 0 or containing_count < 0 or containing_count > document_count:
        raise ValueError("document counts are inconsistent")
    return math.log1p((document_count - containing_count + 0.5) / (containing_count + 0.5))


def score_entry(
    entry: CatalogEntry,
    query_terms: Iterable[str],
    document_frequency: Mapping[str, int],
    document_count: int,
    *,
    config: RankConfig = RankConfig(),
) -> SearchHit | None:
    """Score one entry and retain the terms that contributed to its score."""
    wanted = tuple(dict.fromkeys(query_terms))
    if not wanted:
        return None
    title_counts = frequencies(entry.title)
    label_counts = Counter(term for label in entry.labels for term in terms(label))
    body_counts = frequencies(entry.body)
    score = 0.0
    matched: list[str] = []
    for term in wanted:
        term_score = (
            config.title_weight * title_counts[term]
            + config.label_weight * label_counts[term]
            + config.body_weight * body_counts[term]
        )
        if term_score:
            matched.append(term)
            score += term_score * inverse_document_frequency(
                document_count, document_frequency.get(term, 0)
            )
    if not matched or score < config.minimum_score:
        return None
    excerpt = _excerpt(entry.body or entry.title, matched[0])
    return SearchHit(entry, score, tuple(matched), excerpt)


def rank_entries(
    entries: Iterable[CatalogEntry],
    query_terms: Iterable[str],
    document_frequency: Mapping[str, int],
    document_count: int,
) -> tuple[SearchHit, ...]:
    """Return matches sorted by descending score, then stable identity."""
    hits = (
        hit
        for entry in entries
        if (hit := score_entry(entry, query_terms, document_frequency, document_count))
        is not None
    )
    return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.entry.identifier)))


def _excerpt(text: str, term: str, width: int = 180) -> str:
    """Choose a compact excerpt around a matched token."""
    folded = text.casefold()
    position = folded.find(term.casefold())
    start = max(0, position - width // 3) if position >= 0 else 0
    end = min(len(text), start + width)
    excerpt = text[start:end].strip()
    return f"…{excerpt}" if start else excerpt
