"""Two independent, cache-busted sealed builds compared file-by-file (plan 8.3).

Both builds run through the same `sealed` Dockerfile stage with `--no-cache`,
so reusing compiled objects across the two runs cannot masquerade as
reproducibility; only the immutable `.cache/objects` downloads are shared,
which plan 8.3 explicitly allows.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.inputs import canonical_json  # noqa: E402
from buildsys.reproduce import compare_trees  # noqa: E402

TAGS = ("python-build-m1:reproduce-a", "python-build-m1:reproduce-b")
METHOD = (
    "Two independent `docker build --no-cache --target sealed` runs "
    "(cache fully busted, offline dependency+CPython build both times), "
    "staged installs extracted and compared file-by-file before "
    "stripping/packaging."
)


def _build_sealed(tag: str) -> None:
    subprocess.run(
        ["docker", "build", "--target", "sealed", "--no-cache", "-t", tag, "."],
        cwd=REPO, check=True,
    )


def _extract_staged(tag: str, dest: Path) -> Path:
    container = subprocess.run(
        ["docker", "create", tag], capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        subprocess.run(
            ["docker", "cp", f"{container}:/work/build/stage/cpython-staged/install", str(dest)],
            check=True,
        )
    finally:
        subprocess.run(["docker", "rm", container], capture_output=True)
    return dest


def main() -> int:
    work = REPO / "build" / "reproduce-work"
    if work.exists():
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True)

    trees = []
    for tag in TAGS:
        print(f"BUILD {tag} (--no-cache, sealed)", flush=True)
        _build_sealed(tag)
        dest = work / tag.split(":")[-1] / "install"
        trees.append(_extract_staged(tag, dest))

    report = compare_trees(trees[0], trees[1])
    report["method"] = METHOD
    dist = REPO / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "reproducibility.json").write_text(canonical_json(report) + "\n")
    print(f"OK    reproduce -> byte_identical={report['byte_identical']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
