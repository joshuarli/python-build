# Acquisition stage: package installation is online; compilation is not.
# Bootstrap Python 3.14.7 is a tool, never the distributed CPython 3.14.6.
FROM --platform=linux/amd64 alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS toolchain

RUN apk add --no-cache \
        clang22=22.1.3-r2 \
        lld22=22.1.3-r0 \
        llvm22=22.1.3-r0 \
        build-base=0.5-r4 \
        bsd-compat-headers=0.7.2-r6 \
        linux-headers=7.0.0-r1 \
        python3=3.14.7-r1 \
        perl=5.42.2-r0 \
        pkgconf=2.5.1-r0 \
        autoconf=2.73-r0 \
        automake=1.18.1-r1 \
        libtool=2.6.0-r1 \
        patch=2.8-r0 \
        patchelf=0.18.0-r3 \
    && mkdir -p /opt/bootstrap \
    && apk info -v | sort > /opt/bootstrap/packages.txt \
    && cp /etc/apk/repositories /opt/bootstrap/repositories \
    && cp /etc/alpine-release /opt/bootstrap/alpine-release \
    && addgroup -g 1000 builder \
    && adduser -D -u 1000 -G builder builder \
    && mkdir -p /work/.cache /tmp/opencode \
    && chown builder:builder /work /work/.cache /tmp/opencode

ENV PATH="/usr/lib/llvm22/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    CC=clang CXX=clang++ AR=llvm-ar RANLIB=llvm-ranlib \
    LD=ld.lld NM=llvm-nm STRIP=llvm-strip \
    HOME=/home/builder LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
    PIP_CONFIG_FILE=/dev/null SOURCE_DATE_EPOCH=1704067200

USER builder
WORKDIR /work

# Executed during image construction, using only image toolchain and musl.
RUN printf '%s\n' 'int answer(void) { return 42; }' > /tmp/lto-library.c \
    && printf '%s\n' 'extern int answer(void); int main(void) { return answer() != 42; }' > /tmp/lto-main.c \
    && clang -O3 -march=x86-64 -fno-omit-frame-pointer -flto=thin -c /tmp/lto-library.c -o /tmp/lto-library.o \
    && llvm-ar cr /tmp/liblto.a /tmp/lto-library.o \
    && clang -O3 -march=x86-64 -flto=thin -fuse-ld=lld -Wl,-z,noexecstack /tmp/lto-main.c /tmp/liblto.a -o /tmp/lto-smoke \
    && /tmp/lto-smoke \
    && readelf -l /tmp/lto-smoke | grep '/lib/ld-musl-x86_64.so.1' \
    && clang --version \
    && clang -print-resource-dir \
    && ld.lld --version \
    && python3 --version \
    && rm /tmp/lto-library.c /tmp/lto-main.c /tmp/lto-library.o /tmp/liblto.a /tmp/lto-smoke

# NON-HERMETIC: convenience stage for rapid iteration (plan 7). It has no
# network restriction of its own; a `docker run --network none` container
# from this image is a dev-loop shortcut, not qualification evidence. Only
# the `sealed` stage below (built entirely inside RUN --network=none) is.
FROM toolchain AS development
COPY --chown=builder:builder build.py /work/build.py
COPY --chown=builder:builder buildsys/ /work/buildsys/
COPY --chown=builder:builder build/ /work/build/
COPY --chown=builder:builder patches/ /work/patches/
COPY --chown=builder:builder tests/ /work/tests/
COPY --chown=builder:builder sources.lock.json /work/sources.lock.json
CMD ["python3", "-m", "unittest", "discover", "-s", "tests"]

# SEALED qualification (plan 7, M1c): the dependency and interpreter build
# runs entirely inside one BuildKit RUN with no network access at all,
# using only inputs already verified against sources.lock.json by a prior
# `python3 build.py fetch` (acquisition is a separate, online process over
# the same recipes, not a separate toolchain). If BuildKit's --network=none
# were not actually enforced, any live network dependency introduced here
# would surface as a build failure, not a silent pass.
FROM development AS sealed
COPY --chown=builder:builder .cache/objects/ /work/.cache/objects/
RUN --network=none python3 -m unittest discover -s tests \
 && python3 build/deps.py \
 && python3 build/cpython.py

# Minimal runtime (plan 8.2): only the relocated install tree, no compiler
# or dev packages, so accidental reliance on build-root tooling cannot pass
# here. The smoke import below runs during the image build itself, so a
# regression fails `docker build`, not just a separately-remembered test.
FROM alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS runtime
COPY --from=sealed /work/build/stage/cpython-staged/install /opt/python
RUN /opt/python/bin/python3.14 -c "\
import sys, sysconfig; \
assert sys.version_info[:3] == (3, 14, 6), sys.version_info; \
import ssl, sqlite3, decimal, uuid, bz2, lzma, zlib, ctypes, readline, dbm, curses; \
import compression.zstd; \
assert 'build/prefix' not in sysconfig.get_config_var('LDFLAGS')"
