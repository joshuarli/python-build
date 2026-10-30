"""Compare two independently built release archives and write the verdict."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.inputs import canonical_json
from buildsys.reproduce import compare_archives


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(argv)
    scratch_root = REPO / ".work" / "tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reproduce-archives-", dir=scratch_root) as temporary:
        report = compare_archives(arguments.first, arguments.second, Path(temporary) / "trees")
    arguments.report.write_text(canonical_json(report) + "\n")
    print(json.dumps({key: report[key] for key in ("reproducible", "raw_archives_identical", "files_compared")}))
    if report["content_differences"]:
        print("content differences:", *report["content_differences"], sep="\n  ")
    return 0 if report["reproducible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
