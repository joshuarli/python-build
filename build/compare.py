from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.comparison import ComparisonError, compare_completed_artifact
from buildsys.inputs import InputError
from buildsys.targets import UnsupportedTargetError, native_target, target_for_triple


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a completed package artifact")
    parser.add_argument("--target", required=True)
    arguments = parser.parse_args(argv)
    try:
        target = target_for_triple(arguments.target)
        if target != native_target():
            raise ComparisonError(
                f"requested target {target.triple} does not match this machine"
            )
        report = compare_completed_artifact(
            REPO / "dist" / target.triple,
            target,
            lock_path=REPO / "sources.lock.json",
            cache_root=REPO / ".cache",
            scratch_root=REPO / ".work" / "tmp",
        )
    except (ComparisonError, InputError, UnsupportedTargetError) as error:
        print(f"FAIL compare-reference: {error}")
        return 1
    print(f"OK    compare-reference -> {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
