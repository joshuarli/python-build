"""Inspect optional zlib patch composition on fresh verified source trees."""

import hashlib
import json
import sys
from pathlib import Path


LANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LANE))
import build


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changed_paths(records: list[dict[str, str]]) -> list[str]:
    paths = set()
    for record in records:
        patch = LANE / "patches" / record["file"]
        for line in patch.read_text().splitlines():
            if line.startswith("+++ b/"):
                paths.add(line.removeprefix("+++ b/"))
    return sorted(paths)


def selection(name: str, options: dict[str, bool]) -> dict[str, object]:
    source = build._extract_fresh(build.WORK / f"zlib-selection-{name}")
    records = build._source_patch_inputs(**options)["patches"]
    paths = changed_paths(records)
    before = {name: digest(source / name) if (source / name).is_file() else None for name in paths}
    result = build._apply_source_patches(source, **options)
    after = {name: digest(source / name) if (source / name).is_file() else None for name in paths}
    unchanged = [name for name in paths if before[name] == after[name]]
    if unchanged:
        raise RuntimeError(f"selected patch paths did not change: {unchanged}")
    return {"patches": [record["file"] for record in result["patches"]],
            "changed_paths": paths, "before_sha256": before, "after_sha256": after,
            "per_patch_forward_reverse_checks": "passed"}


def main() -> None:
    optional = {"url_unquote", "tar_checksum", "ipv4_scan", "strptime_numeric",
                "uuid_canonical", "shlex_split", "fraction_rational"}
    cases = {
        "default": {},
        "adaptive": {"zlib_adaptive": True},
        "adaptive_all_optional": {"zlib_adaptive": True, **{name: True for name in optional}},
    }
    print(json.dumps({"recipe": "python3.14 rust-cpython/experiments/zlib_adaptive_patch_selection.py",
                      "source_commit": build._read_lock()[0]["commit"],
                      "cases": {name: selection(name, options) for name, options in cases.items()}},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
