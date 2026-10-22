#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work_parent="$repo_root/.work/tmp"

case "$(uname -s):$(uname -m)" in
    Darwin:arm64) ;;
    *) printf '%s\n' 'This replay covers native Apple Silicon macOS only.' >&2; exit 2 ;;
esac

mkdir -p "$work_parent"
work_dir=$(mktemp -d "$work_parent/rtls-graviola.XXXXXX")
checkout="$work_dir/rtls"

git clone --depth 1 --branch 2026.10.3 https://github.com/jawah/rtls.git "$checkout"
actual=$(git -C "$checkout" rev-parse HEAD)
expected=302423b49e494863d07630d50b15a9488ec85ef7
if [ "$actual" != "$expected" ]; then
    printf 'RTLS source mismatch: expected %s, found %s\n' "$expected" "$actual" >&2
    exit 1
fi

git -C "$checkout" apply --check "$repo_root/research/rtls-graviola/rtls-graviola.patch"
git -C "$checkout" apply "$repo_root/research/rtls-graviola/rtls-graviola.patch"

mkdir -p "$work_dir/tmp"
export TMPDIR="$work_dir/tmp"
export CARGO_TARGET_DIR="$work_dir/target"
rustc_wrapper=$(command -v kache) || {
    printf '%s\n' 'kache is required for Rust compilation.' >&2
    exit 1
}
export RUSTC_WRAPPER="$rustc_wrapper"
export PYO3_BUILD_EXTENSION_MODULE=1
export RUSTFLAGS='-C link-arg=-undefined -C link-arg=dynamic_lookup'

cargo build --manifest-path "$checkout/rust/Cargo.toml" --locked
cp "$CARGO_TARGET_DIR/debug/lib_rustls.dylib" "$checkout/src/rtls/_rustls.abi3.so"
env -u PYTHONHOME -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 \
    python3.15 "$repo_root/research/rtls-graviola/local_tls_smoke.py" "$checkout"
printf 'Prototype checkout and build tree: %s\n' "$work_dir"
