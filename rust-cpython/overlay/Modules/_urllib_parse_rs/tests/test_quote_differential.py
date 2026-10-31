"""The Rust quote and unquote fast paths agree with the pure Python code."""
import importlib.util
import random
import sys
import unittest
import urllib.parse as accelerated

if accelerated._rust_parse is None:
    raise unittest.SkipTest("urllib.parse is not using _urllib_parse_rs")


def load_pure_python():
    sentinel = object()
    previous = sys.modules.get("_urllib_parse_rs", sentinel)
    sys.modules["_urllib_parse_rs"] = None
    try:
        spec = importlib.util.spec_from_file_location(
            "urllib_parse_pure_python", accelerated.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous is sentinel:
            del sys.modules["_urllib_parse_rs"]
        else:
            sys.modules["_urllib_parse_rs"] = previous
    assert module._rust_parse is None
    return module


pure = load_pure_python()

ALPHABET = (
    "abcXYZ019_.-~/ +%&=?#:@!$'()*,;[]\"<>\\^`{|}\t\n\x00\x7f"
    "\xe9€日\U0001f600"
)
SAFE_ALPHABET = "/ +%&=?#:@!$'()*,;[]~\x00\x7f\xe9€"


def random_text(rng, limit):
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, limit)))


def random_safe(rng):
    return "".join(rng.choice(SAFE_ALPHABET) for _ in range(rng.randint(0, 6)))


def random_escapes(rng, limit):
    pieces = ["%", "%4", "%41", "%zz", "%0g", "%e2%82%ac", "%FF", "+", "a", "/", "\xe9", " "]
    return "".join(rng.choice(pieces) for _ in range(rng.randint(0, limit)))


class SameResult:
    def assert_same(self, function, *args, **kwargs):
        try:
            expected = getattr(pure, function)(*args, **kwargs)
        except Exception as error:
            with self.assertRaises(type(error), msg=(function, args, kwargs)) as caught:
                getattr(accelerated, function)(*args, **kwargs)
            self.assertEqual(str(caught.exception), str(error), (function, args, kwargs))
            return
        found = getattr(accelerated, function)(*args, **kwargs)
        self.assertEqual(type(found), type(expected), (function, args, kwargs))
        self.assertEqual(found, expected, (function, args, kwargs))


class QuoteTests(SameResult, unittest.TestCase):
    def test_str_with_str_and_bytes_safe(self):
        rng = random.Random(1)
        for limit in (3, 40, 340, 342, 900, 3000):
            for _ in range(150):
                text = random_text(rng, limit)
                safe = random_safe(rng)
                for function in ("quote", "quote_plus"):
                    self.assert_same(function, text, safe)
                    self.assert_same(function, text, safe.encode("utf-8"))
                    self.assert_same(function, text)

    def test_buffer_boundary_lengths(self):
        for size in range(335, 350):
            for text in ("a" * size, " " * size, "\xe9" * (size // 2), "%" * size):
                for function in ("quote", "quote_plus"):
                    self.assert_same(function, text, "")

    def test_bytes_and_bytearray(self):
        rng = random.Random(2)
        for limit in (3, 40, 340, 900, 3000):
            for _ in range(150):
                data = random_text(rng, limit).encode("utf-8", "surrogatepass")
                safe = random_safe(rng)
                for function in ("quote", "quote_plus", "quote_from_bytes"):
                    self.assert_same(function, data, safe)
                    self.assert_same(function, data, safe.encode())
                self.assert_same("quote_from_bytes", bytearray(data), safe)
                self.assert_same("quote_from_bytes", data)

    def test_empty_str_is_returned_unchanged(self):
        empty = ""
        self.assertIs(accelerated.quote(empty), empty)
        self.assertIs(accelerated.quote_plus(empty), empty)
        self.assertEqual(accelerated.quote_from_bytes(b""), "")

    def test_requests_outside_the_fast_path(self):
        class Text(str):
            pass

        class Data(bytes):
            pass

        cases = [
            ("quote", ("caf\xe9 €",), {"encoding": "latin-1", "errors": "replace"}),
            ("quote", ("caf\xe9 €", "/"), {"encoding": "ascii", "errors": "ignore"}),
            ("quote", (b"abc def",), {"encoding": "utf-8"}),
            ("quote", (b"abc def",), {"errors": "strict"}),
            ("quote", (Text("a b/c"), "/"), {}),
            ("quote_plus", (Text("a b/c"),), {}),
            ("quote", ("a b/c", ["/", " "]), {}),
            ("quote", ("a b/c", bytearray(b"/ ")), {}),
            ("quote_plus", ("a b/c", memoryview(b"/")), {}),
            ("quote_from_bytes", (Data(b"a b/c"), "/"), {}),
            ("quote_from_bytes", (b"a b/c", [47, 200]), {}),
            ("quote_from_bytes", ("not bytes",), {}),
            ("quote", (object(),), {}),
            ("quote", (None,), {}),
            ("quote", ("a",), {"safe": 5}),
        ]
        for function, args, kwargs in cases:
            self.assert_same(function, *args, **kwargs)

    def test_lone_surrogates_raise_the_python_error(self):
        for text in ("a\ud800b", "\udfff", "ok" * 400 + "\ud800"):
            for function in ("quote", "quote_plus"):
                self.assert_same(function, text)
                self.assert_same(function, text, "")
                self.assert_same(function, text, encoding="utf-8", errors="surrogatepass")
        self.assert_same("quote", "a\ud800b", "\ud800")
        self.assert_same("quote", "ab", "\ud800")

    def test_non_ascii_safe_characters_are_ignored(self):
        for safe in ("\xe9", "/\xe9", b"\xe9/", "€"):
            self.assert_same("quote", "a/\xe9 b", safe)
            self.assert_same("quote_plus", "a/\xe9 b", safe)

    def test_urlencode_uses_the_same_results(self):
        rng = random.Random(3)
        for _ in range(100):
            pairs = [(random_text(rng, 8), random_text(rng, 30)) for _ in range(rng.randint(0, 5))]
            self.assert_same("urlencode", pairs)
            self.assert_same("urlencode", pairs, safe="/ ")
            self.assert_same("urlencode", [(k, [v, v + "x"]) for k, v in pairs], doseq=True)


class UnquoteTests(SameResult, unittest.TestCase):
    def test_unquote_to_bytes_str_and_bytes(self):
        rng = random.Random(4)
        for limit in (3, 20, 100, 600, 3000):
            for _ in range(200):
                text = random_escapes(rng, limit)
                self.assert_same("unquote_to_bytes", text)
                self.assert_same("unquote_to_bytes", text.encode("utf-8"))
                self.assert_same("unquote_to_bytes", bytearray(text.encode("utf-8")))

    def test_unquote_and_unquote_plus(self):
        rng = random.Random(5)
        for limit in (3, 20, 100, 600):
            for _ in range(200):
                text = random_escapes(rng, limit)
                self.assert_same("unquote", text)
                self.assert_same("unquote_plus", text)
                self.assert_same("unquote", text.encode("utf-8"))
                self.assert_same("unquote", text, "latin-1", "strict")

    def test_query_parsing(self):
        rng = random.Random(6)
        for _ in range(300):
            query = "&".join(
                rng.choice(("", "a", "k=v", "k=%41+%e2%82%ac", "q=%ff", "x=%", "y=%zz+"))
                for _ in range(rng.randint(0, 8)))
            self.assert_same("parse_qsl", query, keep_blank_values=True)
            self.assert_same("parse_qsl", query)
            self.assert_same("parse_qs", query)
            self.assert_same("parse_qsl", query.encode(), keep_blank_values=True)

    def test_unquote_to_bytes_without_escapes_keeps_identity_of_bytes(self):
        data = b"no escapes here+/"
        self.assertIs(accelerated.unquote_to_bytes(data), data)
        self.assertEqual(accelerated.unquote_to_bytes(""), b"")
        self.assertEqual(accelerated.unquote_to_bytes(b""), b"")

    def test_unquote_to_bytes_invalid_input(self):
        class Data(bytes):
            pass

        for value in (None, 5, object(), Data(b"a%41"), "\ud800%41", ["a"]):
            self.assert_same("unquote_to_bytes", value)

    def test_round_trip(self):
        rng = random.Random(7)
        for _ in range(300):
            text = random_text(rng, 200).encode("utf-8", "ignore").decode("utf-8", "ignore")
            self.assertEqual(accelerated.unquote(accelerated.quote(text, "")), text)
            self.assertEqual(accelerated.unquote_plus(accelerated.quote_plus(text)), text)


if __name__ == "__main__":
    unittest.main()
