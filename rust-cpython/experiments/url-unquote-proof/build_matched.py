"""Build a quote-only control extension with the candidate's LLVM toolchain."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

from build import SOURCE, WORK, run


ORIGINAL = Path(
    "/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/work/source/"
    "cpython-b812b4a7b9efaca46b98544a8633b7d7e454166b/Modules/_rust_url_quote"
)


def main() -> None:
    matched = WORK / "matched-control"
    if matched.exists():
        raise SystemExit(f"stage clone exists: {matched}")
    run(["cp", "-cR", str(SOURCE), str(matched)])
    sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
    configured_cc = subprocess.check_output(
        [str(SOURCE / "bin/python3.16"), "-c", "import sysconfig; print(sysconfig.get_config_var('CC'))"],
        text=True,
    ).strip()
    clang = configured_cc.split()[0]
    if not Path(clang).is_file():
        raise SystemExit(f"configured compiler unavailable: {clang}")
    print(f"configured_cc={configured_cc}", flush=True)
    archive = WORK / "libquote_matched.a"
    c_object = WORK / "module_matched.o"
    extension = matched / "lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so"
    env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET="26.0")
    run(["rustup", "run", "nightly-2026-09-15", "rustc", "--edition=2024",
         "--crate-type=staticlib", "-O", "-C", "panic=abort", str(ORIGINAL / "quote.rs"),
         "-o", str(archive)], env=env)
    run([clang, "-O3", "-fPIC", "-mmacosx-version-min=26.0", "-isysroot", sdk,
         "-I", str(SOURCE / "include/python3.16"), "-c", str(ORIGINAL / "module.c"),
         "-o", str(c_object)], env=env)
    run([clang, "-bundle", "-undefined", "dynamic_lookup", "-mmacosx-version-min=26.0",
         "-isysroot", sdk, str(c_object), str(archive), "-o", str(extension)], env=env)
    parser = matched / "lib/python3.16/urllib/parse.py"
    cache = parser.parent / "__pycache__/parse.cpython-316.pyc"
    cache.unlink(missing_ok=True)
    run([str(matched / "bin/python3.16"), "-m", "compileall", "-q", "--invalidation-mode",
         "checked-hash", str(parser)])
    print(f"matched_control={matched}")


if __name__ == "__main__":
    main()
