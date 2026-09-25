"""Build a decoder extension and matching installed-stage copies."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import sysconfig


HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1] / "work/url-unquote-proof-20260925a"
SOURCE = Path("/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage")
PARSER_SHA = "85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee"
ANCHOR = "    return ''.join(_generate_unquoted_parts(string, encoding, errors))\n"
GUARD = (
    "    if (type(string) is str and type(encoding) is str and\n"
    "            type(errors) is str and encoding == 'utf-8' and errors == 'replace'):\n"
    "        decoded = _rust_url_quote.unquote_ascii(string)\n"
    "        if decoded is not NotImplemented:\n"
    "            return decoded\n"
)


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", *command, flush=True)
    subprocess.run(command, check=True, env=env)


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("macOS proof only")
    parser = SOURCE / "lib/python3.16/urllib/parse.py"
    source = parser.read_bytes()
    if hashlib.sha256(source).hexdigest() != PARSER_SHA:
        raise SystemExit("accepted parser identity changed")
    changed = source.decode().replace(ANCHOR, GUARD + ANCHOR, 1)
    if changed == source.decode() or source.decode().count(ANCHOR) != 1:
        raise SystemExit("parser anchor mismatch")
    rebuild = len(sys.argv) == 2 and sys.argv[1] == "--rebuild-extension"
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and not rebuild):
        raise SystemExit("usage: build.py [--rebuild-extension]")
    WORK.mkdir(parents=True, exist_ok=True)
    if not rebuild:
        for side in ("control", "candidate"):
            dest = WORK / side
            if dest.exists():
                raise SystemExit(f"stage clone exists: {dest}")
            run(["cp", "-cR", str(SOURCE), str(dest)])
        candidate = WORK / "candidate"
        (candidate / "lib/python3.16/urllib/parse.py").write_text(changed)
    else:
        candidate = WORK / "candidate"
        if (candidate / "lib/python3.16/urllib/parse.py").read_text() != changed:
            raise SystemExit("candidate parser changed before extension rebuild")

    sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
    include = SOURCE / "include/python3.16"
    configured_cc = subprocess.check_output(
        [str(SOURCE / "bin/python3.16"), "-c", "import sysconfig; print(sysconfig.get_config_var('CC'))"],
        text=True,
    ).strip()
    clang = configured_cc.split()[0]
    if not Path(clang).is_file():
        raise SystemExit(f"configured compiler unavailable: {clang}")
    print(f"configured_cc={configured_cc}", flush=True)
    archive = WORK / "libquote_unquote.a"
    c_object = WORK / "module.o"
    extension = candidate / "lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so"
    env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET="26.0")
    run(["rustup", "run", "nightly-2026-09-15", "rustc", "--edition=2024",
         "--crate-type=staticlib", "-O", "-C", "panic=abort", str(HERE / "quote.rs"),
         "-o", str(archive)], env=env)
    run([clang, "-O3", "-fPIC", "-mmacosx-version-min=26.0", "-isysroot", sdk,
         "-I", str(include), "-c", str(HERE / "module.c"), "-o", str(c_object)], env=env)
    run([clang, "-bundle", "-undefined", "dynamic_lookup", "-mmacosx-version-min=26.0",
         "-isysroot", sdk, str(c_object), str(archive), "-o", str(extension)], env=env)
    for side in (() if rebuild else ("control", "candidate")):
        staged_parser = WORK / side / "lib/python3.16/urllib/parse.py"
        cache = staged_parser.parent / "__pycache__/parse.cpython-316.pyc"
        cache.unlink(missing_ok=True)
        run([str(WORK / side / "bin/python3.16"), "-m", "compileall", "-q", "--invalidation-mode",
             "checked-hash", str(staged_parser)])
    print(f"control={WORK / 'control'}\ncandidate={candidate}")


if __name__ == "__main__":
    main()
