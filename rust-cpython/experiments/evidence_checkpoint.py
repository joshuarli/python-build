"""Reserve a run's evidence path and replace each checkpoint atomically."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def reserve_evidence(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise SystemExit(f"evidence already exists: {path}; choose a new output path or run ID") from exc
    os.close(descriptor)


def checkpoint_evidence(path: Path, data: dict[str, object], *, sort_keys: bool = False,
                        indent: int | None = 2,
                        separators: tuple[str, str] | None = None) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=indent, sort_keys=sort_keys,
                      separators=separators)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
