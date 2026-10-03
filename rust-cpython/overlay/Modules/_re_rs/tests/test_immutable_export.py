"""Observable contracts for the regex helper's immutable loader export."""
import importlib
import unittest

import _re_rs as native
import re


class ImmutableRegexExportTests(unittest.TestCase):
    def test_private_methods_keep_admission_spans_and_metadata(self):
        for pattern, subject, span in (
            ("a+", "zaaa", (1, 4)),
            (r"(ab|cd)+", "abcd!", (0, 4)),
            (r"\A\w+", "word!", (0, 4)),
            (r"\s+", " \t\n!", (0, 3)),
        ):
            with self.subTest(pattern=pattern):
                self.assertTrue(native.prepare(pattern, 0))
                self.assertTrue(native.prepare(pattern, re.UNICODE))
                self.assertEqual(native.search(pattern, subject, 0), (2, *span))
                self.assertEqual(re.search(pattern, subject).span(), span)
        self.assertEqual(native.search("a", "zzz", 0), (1, 0, 0))
        for pattern, subject, flags in (
            ("a", "a", re.IGNORECASE),
            ("é", "é", 0),
            ("a", "é", 0),
            (r"(?=a)", "a", 0),
        ):
            self.assertEqual(native.search(pattern, subject, flags), (0, 0, 0))
        for name, doc in (
            ("prepare", "Prepare a supported regular expression for searching."),
            ("search", "Search an ASCII string with a supported expression."),
        ):
            method = getattr(native, name)
            self.assertEqual(method.__name__, name)
            self.assertEqual(method.__module__, "_re_rs")
            self.assertEqual(method.__doc__, doc)
            self.assertIs(method.__self__, native)

    def test_private_bad_arity_and_flag_conversion_remain_nonexceptional(self):
        marker = RuntimeError("flag conversion marker")

        class Flag:
            def __index__(self):
                raise marker

        self.assertFalse(native.prepare())
        self.assertFalse(native.prepare("a"))
        self.assertEqual(native.search(), (0, 0, 0))
        self.assertEqual(native.search("a", "a"), (0, 0, 0))
        self.assertFalse(native.prepare("a", Flag()))
        self.assertEqual(native.search("a", "a", Flag()), (0, 0, 0))
        self.assertFalse(native.prepare(object(), 0))
        self.assertEqual(native.search("a", object(), 0), (0, 0, 0))
        self.assertEqual(native.search("a", "a", 0), (2, 0, 1))

    def test_public_dispatch_observes_method_monkeypatches_and_c_captures(self):
        original_prepare = native.prepare
        original_search = native.search
        original_loader = re._rust_re
        calls = []

        def prepare(pattern, flags):
            calls.append(("prepare", pattern, flags))
            return original_prepare(pattern, flags)

        def search(pattern, subject, flags):
            calls.append(("search", pattern, subject, flags))
            return original_search(pattern, subject, flags)

        try:
            re._rust_re = native
            native.prepare = prepare
            native.search = search
            pattern = r"slot-export-(\w+)"
            re.purge()
            match = re.search(pattern, "slot-export-value!")
            self.assertIs(type(match), re.Match)
            self.assertEqual(match.group(1), "value")
            self.assertTrue(any(call[0] == "prepare" for call in calls))
            self.assertTrue(any(call[0] == "search" for call in calls))
        finally:
            native.prepare = original_prepare
            native.search = original_search
            re._rust_re = original_loader
            re.purge()

    def test_reload_preserves_monkeypatch_and_held_native_methods(self):
        held_prepare = native.prepare
        held_search = native.search
        replacement = lambda *args: (0, 0, 0)
        try:
            native.search = replacement
            self.assertIs(importlib.reload(native), native)
            self.assertIs(native.search, replacement)
            self.assertIs(native.prepare, held_prepare)
            self.assertIs(held_prepare.__self__, native)
            self.assertTrue(held_prepare("slot-export-reload", 0))
            self.assertEqual(
                held_search("slot-export-reload", "slot-export-reload", 0),
                (2, 0, len("slot-export-reload")),
            )
            re.purge()
            self.assertEqual(held_search("a+", "aa", 0), (2, 0, 2))
        finally:
            native.search = held_search


if __name__ == "__main__":
    unittest.main()
