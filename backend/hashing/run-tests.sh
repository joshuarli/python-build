#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    printf '%s\n' 'usage: run-tests.sh <candidate-prefix-under-.work> <cpython-3.15.1-source>' >&2
    exit 2
fi

lane_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$lane_dir/../.." && pwd)
prefix=$(CDPATH= cd -- "$1" && pwd)
source_root=$(CDPATH= cd -- "$2" && pwd)
python="$prefix/bin/python3.15"
stdlib="$prefix/lib/python3.15"
dynload="$stdlib/lib-dynload"
work="$repo_root/.work/tmp"
cargo_target="$work/rtls-hashing-cargo-target"

case "$prefix/" in
    "$repo_root/.work/"*) ;;
    *)
        printf '%s\n' 'candidate prefix must be inside this repository .work directory' >&2
        exit 2
        ;;
esac

if [ ! -x "$python" ]; then
    printf 'missing CPython executable: %s\n' "$python" >&2
    exit 2
fi

for module in "$dynload"/_hashlib.cpython-*.so "$dynload"/_hashlib.abi3.so; do
    if [ -e "$module" ]; then
        printf '%s\n' 'candidate still contains a native _hashlib extension' >&2
        exit 2
    fi
done

for module in "$dynload"/_ssl.cpython-*.so "$dynload"/_ssl.abi3.so; do
    if [ -e "$module" ]; then
        printf '%s\n' 'candidate still contains a native _ssl extension' >&2
        exit 2
    fi
done

"$python" -c 'import platform, sys; assert sys.implementation.name == "cpython"; assert sys.version_info[:3] == (3, 15, 1); assert sys.platform == "darwin"; assert platform.machine() == "arm64"'

mkdir -p "$work"
TMPDIR="$work" CARGO_TARGET_DIR="$cargo_target" cargo fetch --locked --manifest-path "$lane_dir/Cargo.toml"
TMPDIR="$work" CARGO_TARGET_DIR="$cargo_target" RUSTC_WRAPPER=kache cargo build --offline --locked --manifest-path "$lane_dir/Cargo.toml"

cp "$lane_dir/_hashlib.py" "$stdlib/_hashlib.py"
cp "$cargo_target/debug/lib_hashlib_graviola.dylib" "$dynload/_hashlib_graviola.abi3.so"

"$python" -I -B - <<'PY'
import importlib.util
from pathlib import Path
import _hashlib
import sys

spec = importlib.util.find_spec("_ssl")
if spec is not None:
    origin = Path(spec.origin) if spec.origin is not None else None
    if (
        origin is None
        or not origin.is_relative_to(Path(sys.prefix, "lib/python3.15"))
        or origin.name != "_ssl.py"
        or "_RUSTLS_BACKEND = True" not in origin.read_text()
    ):
        raise SystemExit("candidate _ssl must be a Python marker shim or absent")
print(_hashlib.__file__)
print(sys.modules["_hashlib_graviola"].__file__)
print(spec.origin if spec is not None else "_ssl unavailable")
PY

mkdir -p "$work/hashlib-test-run"
cd "$work/hashlib-test-run"
if [ ! -d "$stdlib/test" ]; then
    cp -R "$source_root/Lib/test" "$stdlib/test"
fi
TMPDIR="$work" "$python" -I -B -m test test_hashlib test_hmac
TMPDIR="$work" "$python" -I -B -m unittest test.test_support.TestHashlibSupport
TMPDIR="$work" "$python" -I -B "$lane_dir/testdrivers/allocation_failures.py"
TMPDIR="$work" "$python" -I -B "$lane_dir/testdrivers/public_attributes.py"
TMPDIR="$work" "$python" -E -s -B "$lane_dir/testdrivers/subinterpreters.py"
