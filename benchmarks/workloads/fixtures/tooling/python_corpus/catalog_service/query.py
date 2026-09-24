"""Query text parsing and immutable search plans."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Iterable

from catalog_service.errors import InvalidQueryError
from catalog_service.normalize import normalize_text
from catalog_service.tokenizer import terms


@dataclass(frozen=True, slots=True)
class QueryTerm:
    """One positive or excluded term in a query expression."""

    value: str
    field: str | None = None
    excluded: bool = False
    phrase: bool = False


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """Parsed terms, kind restrictions, and sorting behavior."""

    terms: tuple[QueryTerm, ...]
    kinds: tuple[str, ...] = ()
    sort_by: str = "score"
    descending: bool = True

    @property
    def positive_terms(self) -> tuple[str, ...]:
        return tuple(term.value for term in self.terms if not term.excluded)

    @property
    def negative_terms(self) -> tuple[str, ...]:
        return tuple(term.value for term in self.terms if term.excluded)


def parse_query(text: str, *, allowed_fields: Iterable[str] = ("title", "body", "label")) -> SearchPlan:
    """Parse a small fielded query language into a stable search plan."""
    normalized = normalize_text(text)
    allowed = frozenset(allowed_fields)
    parsed: list[QueryTerm] = []
    try:
        pieces = shlex.split(normalized)
    except ValueError as error:
        raise InvalidQueryError(str(error)) from error
    for piece in pieces:
        excluded = piece.startswith("-") and len(piece) > 1
        token = piece[1:] if excluded else piece
        field: str | None = None
        if ":" in token:
            field, token = token.split(":", 1)
            if field not in allowed:
                raise InvalidQueryError(f"unsupported field: {field}")
        values = terms(token)
        if not values:
            continue
        phrase = " " in token
        parsed.extend(QueryTerm(value, field, excluded, phrase) for value in values)
    if not parsed:
        raise InvalidQueryError("query contains no searchable terms")
    return SearchPlan(tuple(parsed))


def combine_queries(plans: Iterable[SearchPlan]) -> SearchPlan:
    """Join plans while retaining first-seen term order and kind filters."""
    unique: dict[tuple[str, str | None, bool], QueryTerm] = {}
    kinds: set[str] = set()
    for plan in plans:
        kinds.update(plan.kinds)
        for term in plan.terms:
            unique.setdefault((term.value, term.field, term.excluded), term)
    return SearchPlan(tuple(unique.values()), tuple(sorted(kinds)))
