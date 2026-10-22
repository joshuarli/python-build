from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buildsys.uvmirror import UvMirrorError, record_runtime_container


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--execution", choices=("native", "emulated"), required=True)
    arguments = parser.parse_args(argv)
    try:
        manifest = record_runtime_container(
            arguments.directory,
            arguments.target,
            arguments.revision,
            arguments.execution,
        )
    except UvMirrorError as error:
        print(f"FAIL runtime qualification: {error}", file=sys.stderr)
        return 1
    print(
        f"OK    runtime qualification {arguments.target}: "
        f"{manifest['archive']['sha256']} ({arguments.execution})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
