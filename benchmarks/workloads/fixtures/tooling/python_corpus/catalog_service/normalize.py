"""Canonical text and identifier normalization helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urlsplit, urlunsplit


_SPACE = re.compile(r"\s+")
_IDENTIFIER = re.compile(r"[^a-z0-9._:-]+")


def normalize_text(value: str) -> str:
    """Fold Unicode and collapse spacing for predictable matching."""
    folded = unicodedata.normalize("NFKC", value).casefold()
    return _SPACE.sub(" ", folded).strip()


def normalize_identifier(value: str) -> str:
    """Create a compact stable identifier from user-provided text."""
    candidate = normalize_text(value).replace(" ", "-")
    normalized = _IDENTIFIER.sub("-", candidate).strip("-.")
    if not normalized:
        raise ValueError("identifier has no usable characters")
    return normalized


def normalize_url(value: str) -> str:
    """Normalize URL spelling while retaining query and fragment data."""
    parts = urlsplit(value.strip())
    scheme = parts.scheme.casefold()
    host = (parts.hostname or "").casefold()
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    userinfo = ""
    if parts.username is not None:
        userinfo = quote(unquote(parts.username), safe="")
        if parts.password is not None:
            userinfo += f":{quote(unquote(parts.password), safe='')}"
        userinfo += "@"
    netloc = f"{userinfo}{host}"
    path = PurePosixPath(parts.path or "/").as_posix()
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parts.query, parts.fragment))


def content_identifier(payload: bytes, *, namespace: str = "entry") -> str:
    """Return a namespaced SHA-256 identifier for an immutable payload."""
    if not namespace or ":" in namespace:
        raise ValueError("namespace must be a nonempty token")
    digest = hashlib.sha256(payload).hexdigest()
    return f"{namespace}:{digest}"


def stable_key(parts: tuple[str, ...]) -> str:
    """Encode a sequence of normalized strings without delimiter clashes."""
    encoded = "/".join(quote(normalize_text(part), safe="") for part in parts)
    if not encoded:
        raise ValueError("a stable key needs at least one component")
    return encoded
