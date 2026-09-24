"""Build an isolated extension and a guarded urllib.parse overlay.

The source interpreter is the pinned no-Rust CPython 3.16 control. All build
products and copied Python files stay under this experiment's ignored .work/.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORK = HERE / ".work"
PARSE_SHA256 = "178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825"
OLD_BRANCH = "    quoter = _byte_quoter_factory(safe)\n"
NEW_BRANCH = (
    "    # Experiment: cross the native boundary only after original fast exits.\n"
    "    if type(bs) is bytes and type(safe) is bytes and len(bs) < 200_000:\n"
    "        return _rust_url_quote.quote_bytes(bs, safe)\n"
    + OLD_BRANCH
)


def main() -> None:
    if sys.version_info[:2] != (3, 16):
        raise SystemExit("run with pinned CPython 3.16 control")
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise SystemExit("requires the GIL-enabled control")
    source = Path(sysconfig.get_path("stdlib")) / "urllib"
    parse = (source / "parse.py").read_bytes()
    if hashlib.sha256(parse).hexdigest() != PARSE_SHA256:
        raise SystemExit("installed urllib.parse source differs from pinned control")
    original = parse.decode("utf-8")
    if original.count(OLD_BRANCH) != 1 or original.count("import math\n") != 1:
        raise SystemExit("pinned source anchors changed")
    overlay = WORK / "overlay"
    package = overlay / "urllib"
    package.mkdir(parents=True, exist_ok=True)
    for module in source.glob("*.py"):
        shutil.copy2(module, package / module.name)
    changed = original.replace("import math\n", "import math\nimport _rust_url_quote\n", 1)
    changed = changed.replace(OLD_BRANCH, NEW_BRANCH, 1)
    (package / "parse.py").write_text(changed)

    include = sysconfig.get_path("include")
    clang = sysconfig.get_config_var("CC").split()[0]
    sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    rust_lib = WORK / "libquote_ascii.a"
    c_obj = WORK / "module.o"
    extension = overlay / ("_rust_url_quote" + suffix)
    env = dict(__import__("os").environ, MACOSX_DEPLOYMENT_TARGET="26.0")
    commands = (
        ["rustup", "run", "nightly-2026-09-15", "rustc", "--edition=2024",
         "--crate-type=staticlib", "-O", "-C", "panic=abort", str(HERE / "quote.rs"),
         "-o", str(rust_lib)],
        [clang, "-O3", "-fPIC", "-mmacosx-version-min=26.0", "-isysroot", sdk, "-I", include,
         "-c", str(HERE / "module.c"), "-o", str(c_obj)],
        [clang, "-bundle", "-undefined", "dynamic_lookup", "-mmacosx-version-min=26.0", "-isysroot", sdk,
         str(c_obj), str(rust_lib), "-o", str(extension)],
    )
    for command in commands:
        print("+", *command, flush=True)
        subprocess.run(command, check=True, env=env)
    print(f"overlay={overlay}")
    print(f"extension={extension}")


if __name__ == "__main__":
    main()
