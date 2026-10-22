from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


def verify_identity(
    install_dir: str | Path,
    expected_version: tuple[int, int, int],
    actual_version: tuple[int, int, int],
    expected_platform: str,
    expected_machine: str,
    implementation: str,
    actual_platform: str,
    actual_machine: str,
    executable: str | Path,
    prefix: str | Path,
) -> None:
    if actual_version != expected_version:
        raise ValueError(f"unexpected Python version: {actual_version}")
    if implementation != "cpython" or actual_platform != expected_platform:
        raise ValueError(f"unexpected interpreter identity: {implementation} {actual_platform}")
    if actual_machine != expected_machine:
        raise ValueError(f"unexpected machine: {actual_machine}")
    root = Path(install_dir).resolve()
    for label, path in (("executable", executable), ("prefix", prefix)):
        resolved = Path(path).resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"{label} escaped fresh uv install directory: {resolved}")


def main() -> int:
    try:
        expected_version = tuple(map(int, os.environ["PYTHON_VERSION"].split(".")))
        verify_identity(
            sys.argv[1],
            expected_version,
            sys.version_info[:3],
            os.environ["EXPECTED_PLATFORM"],
            os.environ["EXPECTED_MACHINE"],
            sys.implementation.name,
            sys.platform,
            platform.machine(),
            sys.executable,
            sys.prefix,
        )
        print(f"verified uv interpreter: {sys.executable}")
    except (IndexError, KeyError, ValueError) as error:
        print(f"uv interpreter verification failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
