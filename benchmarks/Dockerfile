# Fair pyperformance benchmark image: ours vs Astral PBS on the same userland.
#
# Scope is deliberately narrow: x86_64-unknown-linux-musl only, compared
# against Astral's matching musl build. Methodology mirrors
# astral-sh/python-build-standalone PR #1192 (BENCHMARKS.md):
# pyperformance 1.14.0, `pyperformance run --rigorous --warmups 2`, full
# suite run at least twice. Fairness comes from running both interpreters
# sequentially inside the same container on the same host.
#
# The base is the same pinned Alpine image the sealed build stages use, so
# the musl loader both interpreters need is present natively. Our own
# tarball is NOT baked in: it is bind-mounted at run time
# (/inputs/ours.tar.gz), so rebuilding our Python never requires rebuilding
# this image. Only the PBS reference is downloaded here, verified by sha256
# against the `reference-pbs` pin in sources.lock.json.
#
# Build from the repository root (context is this directory, so the main
# .dockerignore does not apply):
#
#   docker build --platform linux/amd64 -t local-pybench-musl benchmarks/
FROM alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

# This image is x86_64-only: the comparison target is
# x86_64-unknown-linux-musl and cross-arch emulation would invalidate
# timing fairness. Fail closed on any other machine.
RUN apk add --no-cache curl ca-certificates tar \
    && [ "$(uname -m)" = "x86_64" ] \
    || (echo "benchmark image is x86_64-only" >&2; exit 1)

# Astral python-build-standalone reference, byte-identical pin to
# sources.lock.json `reference-pbs` (release 20260610, CPython 3.14.6).
ARG PBS_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.14.6+20260610-x86_64-unknown-linux-musl-install_only_stripped.tar.gz
ARG PBS_SHA256=54eca143d09ed3c596ecad5e3bfcb7724387818f8f984f44f3d8c0e9f36681d3
RUN curl -fsSL -o /tmp/pbs.tar.gz "$PBS_URL" \
    && echo "$PBS_SHA256  /tmp/pbs.tar.gz" | sha256sum -c - \
    && mkdir -p /bench/pbs \
    && tar -xzf /tmp/pbs.tar.gz -C /bench/pbs \
    && rm /tmp/pbs.tar.gz \
    && /bench/pbs/python/bin/python3.14 -c "import sys; assert sys.version_info[:3] == (3, 14, 6), sys.version_info"

COPY run_single.sh run_suite.sh run_parallel.sh shard.py pool.py compare.py /bench/
RUN chmod +x /bench/run_single.sh /bench/run_suite.sh /bench/run_parallel.sh

# Vendored benchmark stack (benchmarks/vendor/, hashes in SHA256SUMS):
# installed into each venv with --no-index, so benchmark runs are fully
# offline and byte-pinned. No PyPI access at run time.
COPY vendor/ /bench/vendor/
RUN cd /bench/vendor && sha256sum -c SHA256SUMS && ls ./*.whl

# Alpine's bundle; our OpenSSL build uses system defaults only if told
# where they are, and pip needs this for the pyperformance download.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

CMD ["/bench/run_suite.sh"]
