"""Two independent, cache-busted sealed builds compared file-by-file (plan 8.3).

Both builds run through the same `sealed` Dockerfile stage with `--no-cache`,
so reusing compiled objects across the two runs cannot masquerade as
reproducibility; only the immutable `.cache/objects` downloads are shared,
which plan 8.3 explicitly allows.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.inputs import canonical_json  # noqa: E402
from buildsys.reproduce import compare_trees  # noqa: E402
from buildsys.targets import target_for_triple  # noqa: E402


def _method(platform: str) -> str:
    return (
        f"Two independent `docker build --platform {platform} --no-cache "
        "--target sealed` runs (cache fully busted, offline dependency+"
        "CPython build both times), staged installs extracted and compared "
        "file-by-file before stripping/packaging."
    )


def _build_sealed(tag: str, platform: str) -> None:
    subprocess.run(
        ["docker", "build", "--platform", platform, "--target", "sealed",
         "--no-cache", "-t", tag, "."],
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    target = target_for_triple(args.target)
    tags = (f"python-build-m1:reproduce-a-{target.alpine_arch}",
            f"python-build-m1:reproduce-b-{target.alpine_arch}")

    work = REPO / "build" / "reproduce-work" / target.alpine_arch
    if work.exists():
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True)

    trees = []
    for tag in tags:
        print(f"BUILD {tag} (--no-cache, sealed, {target.docker_platform})", flush=True)
        _build_sealed(tag, target.docker_platform)
        dest = work / tag.split(":")[-1] / "install"
        trees.append(_extract_staged(tag, dest))

    report = compare_trees(trees[0], trees[1])
    report["method"] = _method(target.docker_platform)
    report["target"] = target.triple
    dist = REPO / "dist" / target.triple
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "reproducibility.json").write_text(canonical_json(report) + "\n")
    print(f"OK    reproduce -> byte_identical={report['byte_identical']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
