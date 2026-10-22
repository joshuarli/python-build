from __future__ import annotations

import math
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


_BASE_ENVIRONMENT_KEYS = ("LANG", "LC_ALL", "TZ")
_ALLOWED_OVERRIDES = frozenset(
    {
        "PYTHONHOME",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE",
        "TERM",
        "TERMINFO_DIRS",
        "DEVELOPER_DIR",
        "SDKROOT",
    }
)


def product_environment(
    install: Path,
    cwd: Path,
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    inherited = os.environ
    environment = {
        name: inherited[name]
        for name in _BASE_ENVIRONMENT_KEYS
        if name in inherited
    }
    working_directory = Path(cwd).resolve()
    product_bin = Path(install).resolve() / "bin"
    environment.update(
        {
            "PATH": os.pathsep.join((str(product_bin), os.defpath)),
            "HOME": str(working_directory),
            "TMPDIR": str(working_directory),
            "PYTHONNOUSERSITE": "1",
        }
    )
    if overrides is not None:
        supplied = dict(overrides)
        unsupported = [name for name in supplied if name not in _ALLOWED_OVERRIDES]
        if unsupported:
            names = ", ".join(sorted((str(name) for name in unsupported)))
            raise ValueError(f"unsupported product environment override names: {names}")
        if any(not isinstance(value, str) for value in supplied.values()):
            raise TypeError("product environment override values must be strings")
        environment.update(supplied)
    return environment


def run_product_process(
    argv: Sequence[str | Path],
    install: Path,
    cwd: Path,
    *,
    timeout_seconds: float,
    environment_overrides: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if isinstance(argv, (str, bytes, Path)) or not argv:
        raise ValueError("argv must be a non-empty sequence")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("timeout_seconds must be a finite positive number")
    try:
        timeout = float(timeout_seconds)
    except OverflowError as error:
        raise ValueError("timeout_seconds must be a finite positive number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be a finite positive number")
    command = [os.fspath(argument) for argument in argv]
    if not command or not command[0]:
        raise ValueError("argv must start with a non-empty executable")
    if any(not isinstance(argument, str) for argument in command):
        raise TypeError("argv entries must be strings or Path objects")
    return subprocess.run(
        command,
        cwd=Path(cwd).resolve(),
        env=product_environment(install, cwd, environment_overrides),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
