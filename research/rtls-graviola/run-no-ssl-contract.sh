#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work_parent="$repo_root/.work/tmp"

case "$(uname -s):$(uname -m)" in
    Darwin:arm64) ;;
    *) printf '%s\n' 'This replay covers native Apple Silicon macOS only.' >&2; exit 2 ;;
esac

if [ "$#" -ne 2 ]; then
    printf 'usage: %s <cpython-3.15.1-install> <cpython-test-certdata>\n' \
        "$0" >&2
    exit 2
fi

source_prefix=$(CDPATH= cd -- "$1" && pwd)
certdata=$(CDPATH= cd -- "$2" && pwd)
python="$source_prefix/bin/python3.15"
version=$(
    "$python" -I -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
)
if [ "$version" != 3.15.1 ]; then
    printf 'Expected CPython 3.15.1, found %s\n' "$version" >&2
    exit 1
fi

mkdir -p "$work_parent"
work_dir=$(mktemp -d "$work_parent/rtls-no-ssl.XXXXXX")
candidate="$work_dir/python"
checkout="$work_dir/rtls"
harness="$work_dir/no_ssl_contract.py"
mkdir -p "$work_dir/tmp"
export CARGO_HOME="$work_dir/cargo-home"
/usr/bin/ditto "$source_prefix" "$candidate"
cp "$repo_root/research/rtls-graviola/no_ssl_contract.py" "$harness"

git clone --depth 1 --branch 2026.10.3 \
    https://github.com/jawah/rtls.git "$checkout"
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
for adapter_patch in trust-context.patch tls-controls.patch ssl-api.patch; do
    git -C "$checkout" apply --unidiff-zero --check \
        "$repo_root/research/rtls-graviola/$adapter_patch"
    git -C "$checkout" apply --unidiff-zero \
        "$repo_root/research/rtls-graviola/$adapter_patch"
done

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

export TMPDIR="$work_dir/tmp"
export CARGO_TARGET_DIR="$work_dir/target"
export PYO3_BUILD_EXTENSION_MODULE=1
export PYO3_PYTHON="$candidate/bin/python3.15"
export RUSTFLAGS='-C link-arg=-undefined -C link-arg=dynamic_lookup'
webpki_archive="$work_dir/rustls-webpki.crate"
"$python" "$repo_root/research/rtls-graviola/prepare_webpki.py" fetch "$webpki_archive"
"$python" "$repo_root/research/rtls-graviola/prepare_webpki.py" prepare "$webpki_archive" "$checkout"
rustup run "$rust_toolchain" cargo build \
    --manifest-path "$checkout/rust/Cargo.toml" --locked
cp "$CARGO_TARGET_DIR/debug/lib_rustls.dylib" \
    "$checkout/src/rtls/_rustls.abi3.so"

stdlib="$candidate/lib/python3.15"
module_dir="$stdlib"
dynload="$stdlib/lib-dynload"
mkdir -p "$module_dir"
if [ -e "$module_dir/rtls" ]; then
    mv "$module_dir/rtls" "$work_dir/original-rtls"
fi
cp -R "$checkout/src/rtls" "$module_dir/rtls"
cp "$repo_root/research/rtls-graviola/ssl_facade.py" "$stdlib/ssl.py"
cp "$repo_root/research/rtls-graviola/ssl_native_compat.py" "$stdlib/_ssl.py"
cp "$repo_root/research/rtls-graviola/ssl_metadata.py" "$stdlib/_ssl_metadata.py"
cp "$certdata/capath/ceff1710.0" "$stdlib/python-build-cacert.pem"

extension_count=0
mkdir -p "$work_dir/removed"
for extension in "$dynload"/_ssl*.so; do
    if [ -f "$extension" ]; then
        extension_count=$((extension_count + 1))
        mv "$extension" "$work_dir/removed/$(basename "$extension")"
    fi
done
if [ "$extension_count" -ne 1 ]; then
    printf 'Expected one _ssl extension, found %s\n' "$extension_count" >&2
    exit 1
fi

export PYTHONPYCACHEPREFIX="$work_dir/pycache"
"$python" -B -I "$harness" "$certdata" --openssl-reference

candidate_status=0
"$candidate/bin/python3.15" -B -I \
    "$harness" "$certdata" \
    || candidate_status=$?
environment_status=0
"$candidate/bin/python3.15" -B -E -s \
    "$harness" "$certdata" \
    || environment_status=$?
printf 'OpenSSL-free isolated candidate exit status: %s\n' "$candidate_status"
printf 'OpenSSL-free -E candidate exit status: %s\n' "$environment_status"
printf 'Disposable interpreter and RTLS build: %s\n' "$work_dir"
if [ "$candidate_status" -ne 0 ]; then
    exit "$candidate_status"
fi
exit "$environment_status"
