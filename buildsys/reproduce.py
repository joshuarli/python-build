"""Compare two clean-build install trees for internal reproducibility.

Sharing immutable downloaded inputs is fine; this compares *build outputs*
from two independent, cache-busted sealed builds, so any prior-object reuse
would show up as a suspiciously-easy match rather than real evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat


@dataclass(frozen=True)
class _TreeEntry:
    kind: int
    mode: int
    content_digest: str | None = None
    symlink_target: str | None = None


def _relative_entries(root: Path) -> dict[str, _TreeEntry]:
    entries: dict[str, _TreeEntry] = {}
    for path in root.rglob("*"):
        info = path.lstat()
        kind = stat.S_IFMT(info.st_mode)
        entries[str(path.relative_to(root))] = _TreeEntry(
            kind=kind,
            mode=stat.S_IMODE(info.st_mode),
            content_digest=_sha256(path) if stat.S_ISREG(info.st_mode) else None,
            symlink_target=os.readlink(path) if stat.S_ISLNK(info.st_mode) else None,
        )
    return entries


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def macho_difference(first: Path, second: Path) -> dict:
    """Split a binary difference into signing metadata and everything else.

    "These two builds differ" and "these two builds differ only in their code
    signatures" are different claims, and a raw hash comparison cannot tell
    them apart. On Apple Silicon every Mach-O carries an ad-hoc signature that
    covers the whole image, so any difference at all — including the
    per-link LC_UUID — propagates into the signature bytes and makes a naive
    comparison look far worse than the underlying change.
    """
    from . import macho

    a, b = Path(first).read_bytes(), Path(second).read_bytes()
    if len(a) != len(b):
        return {"size_delta": len(a) - len(b), "comparable": False}
    metadata = set()
    for path in (first, second):
        for offset, size in macho.signature_metadata_ranges(path):
            metadata.update(range(offset, min(offset + size, len(a))))
    differing = [i for i in range(len(a)) if a[i] != b[i]]
    in_metadata = [i for i in differing if i in metadata]
    residual = [i for i in differing if i not in metadata]
    return {
        "comparable": True,
        "differing_bytes": len(differing),
        "signature_metadata_bytes": len(in_metadata),
        # Bytes outside the UUID and the signature: the compiled content.
        "compiled_content_bytes": len(residual),
        "compiled_content_identical": not residual,
        "first_residual_offsets": residual[:8],
    }


def compare_trees(first: Path, second: Path) -> dict:
    """Report entry identity differences between two install trees."""
    a, b = _relative_entries(first), _relative_entries(second)
    only_in_first = sorted(a.keys() - b.keys())
    only_in_second = sorted(b.keys() - a.keys())
    shared = a.keys() & b.keys()
    entry_type_differs = sorted(name for name in shared if a[name].kind != b[name].kind)
    mode_differs = sorted(name for name in shared if a[name].mode != b[name].mode)
    regular_files = {
        name for name in shared
        if a[name].kind == stat.S_IFREG and b[name].kind == stat.S_IFREG
    }
    content_differs = sorted(
        name for name in regular_files
        if a[name].content_digest != b[name].content_digest
    )
    symlink_target_differs = sorted(
        name for name in shared
        if a[name].kind == stat.S_IFLNK
        and b[name].kind == stat.S_IFLNK
        and a[name].symlink_target != b[name].symlink_target
    )
    identical = sum(
        a[name].content_digest == b[name].content_digest
        and a[name].mode == b[name].mode
        for name in regular_files
    )
    return {
        "files_compared": len(regular_files),
        "only_in_first": only_in_first,
        "only_in_second": only_in_second,
        "entry_type_differs": entry_type_differs,
        "mode_differs": mode_differs,
        "content_differs": content_differs,
        "symlink_target_differs": symlink_target_differs,
        "byte_identical": not any((
            only_in_first,
            only_in_second,
            entry_type_differs,
            mode_differs,
            content_differs,
            symlink_target_differs,
        )),
        "identical_file_count": identical,
    }
