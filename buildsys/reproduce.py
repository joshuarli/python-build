"""Compare two clean-build install trees for internal reproducibility (plan 8.3).

Sharing immutable downloaded inputs is fine; this compares *build outputs*
from two independent, cache-busted sealed builds, so any prior-object reuse
would show up as a suspiciously-easy match rather than real evidence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def _relative_files(root: Path) -> dict[str, Path]:
    return {
        str(path.relative_to(root)): path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def compare_trees(first: Path, second: Path) -> dict:
    """Report path-set and content-hash differences between two install trees."""
    a, b = _relative_files(first), _relative_files(second)
    only_in_first = sorted(a.keys() - b.keys())
    only_in_second = sorted(b.keys() - a.keys())
    differing = sorted(
        name for name in (a.keys() & b.keys())
        if _sha256(a[name]) != _sha256(b[name])
    )
    identical = len(a) - len(differing) - len(only_in_first)
    return {
        "files_compared": len(a.keys() & b.keys()),
        "only_in_first": only_in_first,
        "only_in_second": only_in_second,
        "content_differs": differing,
        "byte_identical": not only_in_first and not only_in_second and not differing,
        "identical_file_count": max(identical, 0),
    }
