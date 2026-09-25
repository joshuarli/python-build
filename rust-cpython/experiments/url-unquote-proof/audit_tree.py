"""Compare every installed regular file and symlink in the cloned stages."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys


WORK = Path(__file__).resolve().parents[2] / "work/url-unquote-proof-20260925a"


def inventory(root: Path) -> dict[str, tuple[str, str]]:
    found = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(base) / name
            key = str(path.relative_to(root))
            if path.is_symlink():
                found[key] = ("symlink", os.readlink(path))
            elif path.is_file():
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                found[key] = ("file", digest.hexdigest())
            elif path.is_dir():
                found[key] = ("directory", "")
            else:
                found[key] = ("other", "")
    return found


def main() -> None:
    comparator = sys.argv[1] if len(sys.argv) == 2 else "control"
    if comparator not in {"control", "matched-control"}:
        raise SystemExit("usage: audit_tree.py [control|matched-control]")
    if not (WORK / comparator).is_dir() or not (WORK / "candidate").is_dir():
        raise RuntimeError("stage clones are missing")
    control = inventory(WORK / comparator)
    candidate = inventory(WORK / "candidate")
    difference = {key: {"control": control.get(key), "candidate": candidate.get(key)}
                  for key in control.keys() | candidate.keys() if control.get(key) != candidate.get(key)}
    print(json.dumps({"comparator": comparator, "control_entries": len(control), "candidate_entries": len(candidate),
                      "differences": difference}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
