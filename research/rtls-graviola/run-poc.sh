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

git -C "$checkout" apply --unidiff-zero --check \
    "$repo_root/research/rtls-graviola/rtls-graviola.patch"
git -C "$checkout" apply --unidiff-zero \
    "$repo_root/research/rtls-graviola/rtls-graviola.patch"

mkdir -p "$work_dir/tmp"
export TMPDIR="$work_dir/tmp"
export CARGO_HOME="$work_dir/cargo-home"
export CARGO_TARGET_DIR="$work_dir/target"
rust_toolchain=${RTLS_RUST_TOOLCHAIN:-stable}
expected_rust_version=1.99.1
rust_version_output=$(rustup run "$rust_toolchain" rustc --version) || {
    printf '%s\n' 'Install rustup and Rust 1.99.1 to replay this prototype.' >&2
    exit 1
}
rust_version=$(printf '%s\n' "$rust_version_output" | awk '{print $2}')
if [ "$rust_version" != "$expected_rust_version" ]; then
    printf 'Expected Rust %s, found %s.\n' \
        "$expected_rust_version" "$rust_version" >&2
    exit 1
fi
if [ "${RUSTC_WRAPPER+x}" != x ]; then
    if command -v kache >/dev/null 2>&1; then
        RUSTC_WRAPPER=$(command -v kache)
    else
        RUSTC_WRAPPER=
    fi
    export RUSTC_WRAPPER
fi
export PYO3_BUILD_EXTENSION_MODULE=1
export RUSTFLAGS='-C link-arg=-undefined -C link-arg=dynamic_lookup'

webpki_archive="$work_dir/rustls-webpki.crate"
python3.15 "$repo_root/research/rtls-graviola/prepare_webpki.py" fetch "$webpki_archive"
python3.15 "$repo_root/research/rtls-graviola/prepare_webpki.py" prepare "$webpki_archive" "$checkout"
rustls_archive="$work_dir/rustls.crate"
python3.15 "$repo_root/research/rtls-graviola/prepare_rustls.py" fetch "$rustls_archive"
python3.15 "$repo_root/research/rtls-graviola/prepare_rustls.py" prepare "$rustls_archive" "$checkout"
rustup run "$rust_toolchain" cargo build \
    --manifest-path "$checkout/rust/Cargo.toml" --locked
cp "$CARGO_TARGET_DIR/debug/lib_rustls.dylib" "$checkout/src/rtls/_rustls.abi3.so"
env -u PYTHONHOME -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 \
    python3.15 "$repo_root/research/rtls-graviola/local_tls_smoke.py" "$checkout"
printf 'Prototype checkout and build tree: %s\n' "$work_dir"
