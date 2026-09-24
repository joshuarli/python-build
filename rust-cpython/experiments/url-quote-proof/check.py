"""Differential public URL quotation checks against installed pinned parse.py."""

from __future__ import annotations

import importlib.util
import sysconfig
import urllib.parse as candidate
from pathlib import Path


class BytesSubclass(bytes):
    pass


class BytearraySubclass(bytearray):
    pass


def outcome(function, *args):
    try:
        result = function(*args)
    except Exception as exc:
        return ("exception", type(exc).__name__, str(exc))
    return ("value", type(result).__name__, result)


def main() -> None:
    source = Path(sysconfig.get_path("stdlib")) / "urllib" / "parse.py"
    spec = importlib.util.spec_from_file_location("control_urllib_parse", source)
    assert spec is not None and spec.loader is not None
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    assert candidate.__file__ != str(source), "overlay was not loaded"
    assert candidate._rust_url_quote.__file__.endswith(".so")

    cases = 0
    safe_values = (b"", b"/", b"?&=%", b"\0 \x7f\x80\xff", "é/雪", "\0é", [0, 47, 127, 128], bytearray(b"/"))
    inputs = [bytes(range(256)), bytes(range(255, -1, -1)), b"", b"all-safe_~/-", b"x y", b"\0\x7f\xff", b"x" * 17 + b" ", b"a" * 199998 + b" ", b"a" * 199999 + b" "]
    inputs.extend(bytes((i,)) for i in range(256))
    inputs.extend((BytesSubclass(b"a b"), BytearraySubclass(b"a b"), bytearray(b"a b")))
    for bs in inputs:
        for safe in safe_values:
            expected = outcome(control.quote_from_bytes, bs, safe)
            actual = outcome(candidate.quote_from_bytes, bs, safe)
            assert actual == expected, (bs[:30], safe, expected, actual)
            cases += 1
    for bs, safe in (("str", "/"), (1, "/"), (memoryview(b"x"), "/"), (b"x ", 3),
                     (b"x ", [256]), (b"x ", [-1]), (b"x ", ["/"]),
                     (b"x ", object()), (b"", object())):
        expected = outcome(control.quote_from_bytes, bs, safe)
        actual = outcome(candidate.quote_from_bytes, bs, safe)
        assert actual == expected, (bs, safe, expected, actual)
        cases += 1
    for bs in ("é /", b"a b", bytearray(b"a b")):
        for safe in ("", "/", b"/", "é/"):
            assert outcome(candidate.quote, bs, safe) == outcome(control.quote, bs, safe)
            assert outcome(candidate.quote_plus, bs, safe) == outcome(control.quote_plus, bs, safe)
            cases += 2

    hits = 0
    original = candidate._rust_url_quote.quote_bytes
    def observed(*args):
        nonlocal hits
        hits += 1
        return original(*args)
    candidate._rust_url_quote.quote_bytes = observed
    try:
        assert candidate.quote(b"a b", safe="") == "a%20b"
        assert candidate.quote_from_bytes(bytearray(b"a b"), safe="") == "a%20b"
        assert candidate.quote_from_bytes(b"a/b", safe="/") == "a/b"
    finally:
        candidate._rust_url_quote.quote_bytes = original
    assert hits == 1, hits
    print(f"differential_cases={cases} native_public_path_hits={hits}")


if __name__ == "__main__":
    main()
