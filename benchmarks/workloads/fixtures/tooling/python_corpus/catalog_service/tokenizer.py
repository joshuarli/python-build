"""Unicode-aware tokenization used by indexing and query planning."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Iterator

from catalog_service.normalize import normalize_text


_TOKEN = re.compile(r"[\w]+(?:['’][\w]+)?", re.UNICODE)
_DEFAULT_STOP_WORDS = frozenset(
    {"a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with"}
)


@dataclass(frozen=True, slots=True)
class Token:
    """A term and its character range in normalized source text."""

    value: str
    start: int
    end: int
    ordinal: int


def iter_tokens(text: str, *, stop_words: frozenset[str] = _DEFAULT_STOP_WORDS) -> Iterator[Token]:
    """Yield lowercased terms while keeping source offsets for excerpts."""
    normalized = normalize_text(text)
    for ordinal, match in enumerate(_TOKEN.finditer(normalized)):
        term = match.group(0)
        if term not in stop_words and not term.isdecimal():
            yield Token(term, match.start(), match.end(), ordinal)


def terms(text: str, *, stop_words: frozenset[str] = _DEFAULT_STOP_WORDS) -> tuple[str, ...]:
    """Collect the ordered token values from one source string."""
    return tuple(token.value for token in iter_tokens(text, stop_words=stop_words))


def frequencies(text: str, *, stop_words: frozenset[str] = _DEFAULT_STOP_WORDS) -> Counter[str]:
    """Count normalized terms while preserving the Counter API."""
    return Counter(token.value for token in iter_tokens(text, stop_words=stop_words))


def ngrams(values: Iterable[str], width: int) -> Iterator[tuple[str, ...]]:
    """Yield adjacent token groups with bounded, explicit width."""
    if width < 1:
        raise ValueError("ngram width must be positive")
    window: list[str] = []
    for value in values:
        window.append(unicodedata.normalize("NFKC", value).casefold())
        if len(window) == width:
            yield tuple(window)
            del window[0]
