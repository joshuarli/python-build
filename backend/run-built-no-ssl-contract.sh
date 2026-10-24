#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
work_parent="$repo_root/.work/tmp"

case "$(uname -s):$(uname -m)" in
    Darwin:arm64) ;;
    *) printf '%s\n' 'This replay covers native Apple Silicon macOS only.' >&2; exit 2 ;;
esac

if [ "$#" -ne 3 ]; then
    printf 'usage: %s <OpenSSL-free-prefix-under-.work> <cpython-test-certdata> <reference-python>\n' \
        "$0" >&2
    exit 2
fi

source_prefix=$(CDPATH= cd -- "$1" && pwd)
certdata=$(CDPATH= cd -- "$2" && pwd)
reference_python=$3
stdlib_source=$(CDPATH= cd -- "$certdata/../.." && pwd)
case "$source_prefix/" in
    "$repo_root/.work/"*) ;;
    *) printf '%s\n' 'Candidate prefix must be inside this worktree .work directory.' >&2; exit 2 ;;
esac

mkdir -p "$work_parent"
work_dir=$(mktemp -d "$work_parent/rtls-built-no-ssl.XXXXXX")
candidate="$work_dir/python"
stdlib="$candidate/lib/python3.15"
dynload="$stdlib/lib-dynload"
mkdir -p "$work_dir/tmp" "$work_dir/home"
/usr/bin/ditto "$source_prefix" "$candidate"
/usr/bin/ditto "$stdlib_source/test" "$stdlib/test"
cp "$repo_root/backend/no_ssl_contract.py" "$work_dir/no_ssl_contract.py"
cp "$repo_root/backend/trust_policy_contract.py" \
    "$work_dir/trust_policy_contract.py"
cp "$repo_root/backend/ssl_utilities_contract.py" \
    "$work_dir/ssl_utilities_contract.py"
cp "$certdata/capath/ceff1710.0" "$stdlib/python-build-cacert.pem"

for module in "$dynload"/_ssl.cpython-*.so "$dynload"/_ssl.abi3.so \
    "$dynload"/_ssl.so "$dynload"/_ssl.dylib \
    "$dynload"/_hashlib.cpython-*.so "$dynload"/_hashlib.abi3.so \
    "$dynload"/_hashlib.so "$dynload"/_hashlib.dylib; do
    if [ -e "$module" ]; then
        printf 'Candidate contains a native TLS or hashing module: %s\n' \
            "$module" >&2
        exit 1
    fi
done

unset SSL_CERT_FILE SSL_CERT_DIR PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE
utilities_reference_status=0
env -i HOME="$work_dir/home" PATH="$PATH" TMPDIR="$work_dir/tmp" \
    "$reference_python" -B -I \
    "$work_dir/ssl_utilities_contract.py" "$certdata/nullbytecert.pem" \
    || utilities_reference_status=$?
utilities_candidate_status=0
env -i HOME="$work_dir/home" PATH="$PATH" TMPDIR="$work_dir/tmp" \
    "$candidate/bin/python3.15" -B -I -S \
    "$work_dir/ssl_utilities_contract.py" "$certdata/nullbytecert.pem" \
    || utilities_candidate_status=$?
isolated_status=0
env -i HOME="$work_dir/home" PATH="$PATH" TMPDIR="$work_dir/tmp" \
    "$candidate/bin/python3.15" -B -I -S \
    "$work_dir/no_ssl_contract.py" "$certdata" || isolated_status=$?
environment_status=0
env -i HOME="$work_dir/home" PATH="$PATH" TMPDIR="$work_dir/tmp" \
    "$candidate/bin/python3.15" -B -E -S -s \
    "$work_dir/no_ssl_contract.py" "$certdata" || environment_status=$?
cp "$source_prefix/lib/python3.15/python-build-cacert.pem" \
    "$stdlib/python-build-cacert.pem"
trust_status=0
env -i HOME="$work_dir/home" PATH="$PATH" TMPDIR="$work_dir/tmp" \
    "$candidate/bin/python3.15" -B -I -S \
    "$work_dir/trust_policy_contract.py" "$certdata" \
    "$stdlib/python-build-cacert.pem" "$reference_python" || trust_status=$?
hash_status=0
(cd "$work_dir" && \
    env -i HOME="$work_dir/home" PATH="$PATH" TMPDIR="$work_dir/tmp" \
        "$candidate/bin/python3.15" -B -I -S -m test test_hashlib test_hmac) \
    || hash_status=$?
ssl_status=0
(cd "$work_dir" && \
    env -i HOME="$work_dir/home" PATH="$PATH" TMPDIR="$work_dir/tmp" \
        "$candidate/bin/python3.15" -B -I -S -m test --timeout=120 test_ssl) \
    || ssl_status=$?
printf 'Fresh OpenSSL-free isolated candidate exit status: %s\n' \
    "$isolated_status"
printf 'OpenSSL utility contract reference exit status: %s\n' \
    "$utilities_reference_status"
printf 'OpenSSL-free utility contract exit status: %s\n' \
    "$utilities_candidate_status"
printf 'Fresh OpenSSL-free -E candidate exit status: %s\n' \
    "$environment_status"
printf 'Fresh OpenSSL-free trust-policy exit status: %s\n' "$trust_status"
printf 'Fresh OpenSSL-free hash-suite exit status: %s\n' "$hash_status"
printf 'Fresh OpenSSL-free test_ssl exit status: %s\n' "$ssl_status"
printf 'Disposable interpreter: %s\n' "$work_dir"
if [ "$isolated_status" -ne 0 ]; then
    exit "$isolated_status"
fi
if [ "$utilities_reference_status" -ne 0 ]; then
    exit "$utilities_reference_status"
fi
if [ "$utilities_candidate_status" -ne 0 ]; then
    exit "$utilities_candidate_status"
fi
if [ "$environment_status" -ne 0 ]; then
    exit "$environment_status"
fi
if [ "$trust_status" -ne 0 ]; then
    exit "$trust_status"
fi
if [ "$hash_status" -ne 0 ]; then
    exit "$hash_status"
fi
exit "$ssl_status"
