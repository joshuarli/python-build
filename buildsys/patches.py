"""Apply the project's small selected patch set.

Every patch records its upstream source and version, origin and license,
purpose, scope, applicability, and regression test.
Patches are applied against a freshly verified source tree and rejected
outright on any reject or unexpected preimage, rather than silently
skipped.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class PatchError(Exception):
    """A patch failed its applicability check or failed to apply."""


def apply_patch(source: Path, patch: Path, *, strip: int = 1) -> None:
    """Apply a unified diff to `source`, failing closed on any mismatch."""
    if not patch.is_file():
        raise PatchError(f"patch not found: {patch}")
    dry_run = subprocess.run(
        ["patch", f"-p{strip}", "--dry-run", "--forward", "-i", str(patch)],
        cwd=source, capture_output=True, text=True,
    )
    if dry_run.returncode != 0:
        raise PatchError(
            f"{patch.name} does not apply cleanly to {source}: {dry_run.stdout}{dry_run.stderr}"
        )
    result = subprocess.run(
        ["patch", f"-p{strip}", "--forward", "-i", str(patch)],
        cwd=source, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise PatchError(
            f"{patch.name} applied in dry-run but failed for real: {result.stdout}{result.stderr}"
        )


def apply_patch_set(source: Path, patch_dir: Path) -> list[Path]:
    """Apply every `*.patch` file in `patch_dir`, in sorted order."""
    applied = []
    for patch in sorted(patch_dir.glob("*.patch")):
        apply_patch(source, patch)
        applied.append(patch)
    return applied
