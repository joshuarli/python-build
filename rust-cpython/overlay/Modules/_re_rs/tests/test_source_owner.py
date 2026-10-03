"""Compiled-engine source ownership preserves public pattern lifetimes."""
import re
import unittest
import weakref

import _re_rs as native


class RegexSourceOwnerContracts(unittest.TestCase):
    def test_cache_identity_and_held_match_release_pattern(self):
        re.purge()
        pattern = re.compile(r"source-owner-public-(\w+)")
        reference = weakref.ref(pattern)
        self.assertIs(re.compile(pattern.pattern), pattern)
        self.assertIs(re.compile(pattern), pattern)
        match = re.search(pattern, "source-owner-public-value")
        self.assertIs(match.re, pattern)
        self.assertEqual(match.group(1), "value")
        re.purge()
        del pattern
        self.assertIs(reference(), match.re)
        self.assertEqual(match.group(1), "value")
        del match
        self.assertIsNone(reference())

    def test_native_eviction_reinsert_and_retained_public_pattern(self):
        re.purge()
        pattern = re.compile(r"source-owner-held-(\w+)")
        held = re.search(pattern, "source-owner-held-value")
        for index in range(514):
            text = f"source-owner-churn-{index}"
            self.assertEqual(native.search(text, text, 0), (2, 0, len(text)))
        self.assertEqual(native.search(pattern.pattern, "source-owner-held-value", 32), (2, 0, 23))
        self.assertIs(held.re, pattern)
        self.assertEqual(held.group(1), "value")
        self.assertEqual(re.search(pattern, "source-owner-held-value").group(1), "value")

    def test_native_routing_fallback_errors_and_method_reentry(self):
        original = native.search
        calls = []

        def traced(pattern, subject, flags):
            calls.append((pattern, flags))
            self.assertEqual(original("source-owner-inner", "source-owner-inner", 0), (2, 0, 18))
            return original(pattern, subject, flags)

        native.search = traced
        try:
            pattern = re.compile(r"source-owner-route-(\w+)")
            self.assertEqual(re.search(pattern, "source-owner-route-value").group(1), "value")
            self.assertIn((pattern.pattern, 32), calls)
        finally:
            native.search = original
        self.assertEqual(native.search("abc", "ABC", re.IGNORECASE), (0, 0, 0))
        self.assertEqual(re.search("abc", "ABC", re.IGNORECASE).span(), (0, 3))
        self.assertEqual(native.search(r"value=(\d+)$", "value=42", 0), (0, 0, 0))
        self.assertEqual(re.search(r"value=(\d+)$", "value=42").group(1), "42")
        with self.assertRaisesRegex(ValueError, "cannot process flags argument"):
            re.compile(pattern, re.IGNORECASE)
        with self.assertRaises(re.PatternError):
            re.compile("(")


if __name__ == "__main__":
    unittest.main()
