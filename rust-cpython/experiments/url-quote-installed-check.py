"""Run the lean URL differential check against an installed candidate.

`url-quote-lean-proof/check.py` compares an overlay `urllib.parse` with the
interpreter's own installed parser. For a fully installed candidate the
installed parser *is* the candidate, so this wrapper points the check's
control at a separate unpatched `urllib/parse.py` (for example from the
unpatched fork stage), after verifying that file's SHA-256.

Usage:
    <candidate python3.16> -I url-quote-installed-check.py CONTROL_STDLIB SHA256
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    control_stdlib = Path(sys.argv[1]).resolve()
    expected = sys.argv[2]
    parser = control_stdlib / "urllib" / "parse.py"
    found = hashlib.sha256(parser.read_bytes()).hexdigest()
    if found != expected:
        raise SystemExit(f"control parser digest {found} != {expected}")
    spec = importlib.util.spec_from_file_location("lean_check", HERE / "url-quote-lean-proof" / "check.py")
    assert spec is not None and spec.loader is not None
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    # The check reads only sysconfig.get_path("stdlib") to locate its control.
    check.sysconfig = types.SimpleNamespace(get_path=lambda name: str(control_stdlib))
    check.main()
    print(f"control parser {parser} sha256 {found}")


if __name__ == "__main__":
    main()
