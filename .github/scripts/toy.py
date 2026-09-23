"""Toy program for the CI uv smoke test.

Exercised against a `uv`-installed copy of this project's distribution on
every shipped triple. Standard library only: the distribution deliberately
ships no `pip`, `ensurepip`, `venv`, or `tkinter`, so none of those may be
touched here.
"""

import bz2
import ctypes
import decimal
import hashlib
import lzma
import os
import sqlite3
import sys
import tempfile
import uuid
import zlib

import compression.zstd


def main() -> int:
    assert sys.version_info[:3] == (3, 14, 6), sys.version_info
    assert hashlib.sha256(b"abc").hexdigest() == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert zlib.decompress(zlib.compress(b"a" * 4096)) == b"a" * 4096
    assert bz2.decompress(bz2.compress(b"b" * 4096)) == b"b" * 4096
    assert lzma.decompress(lzma.compress(b"c" * 4096)) == b"c" * 4096
    assert compression.zstd.decompress(compression.zstd.compress(b"d" * 4096)) == b"d" * 4096
    assert str(decimal.Decimal(2).sqrt())[:9] == "1.4142135"
    assert len(uuid.uuid4().hex) == 32

    libc = ctypes.CDLL(None)
    strlen = libc.strlen
    strlen.argtypes = [ctypes.c_char_p]
    strlen.restype = ctypes.c_size_t
    assert strlen(b"hello") == 5

    with tempfile.TemporaryDirectory() as scratch:
        path = os.path.join(scratch, "toy.db")
        connection = sqlite3.connect(path)
        connection.execute("create table t(a)")
        connection.execute("insert into t values (?)", (42,))
        assert connection.execute("select a from t").fetchone() == (42,)
        connection.close()

    import ssl

    print(f"toy ok: {sys.version.split()[0]} ({ssl.OPENSSL_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
