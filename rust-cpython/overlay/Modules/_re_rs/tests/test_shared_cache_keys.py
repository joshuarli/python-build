"""Public pattern identity and native cache eviction keep separate ownership."""
import re
import unittest
import weakref

import _re_rs as native


class SharedRegexKeyContracts(unittest.TestCase):
    def test_public_pattern_cache_identity_weakrefs_and_held_match(self):
        re.purge()
        pattern = re.compile(r"shared-key-public-(\w+)")
        reference = weakref.ref(pattern)
        self.assertIs(re.compile(pattern.pattern), pattern)
        self.assertIs(re.compile(pattern), pattern)
        match = re.search(pattern, "shared-key-public-value")
        self.assertIs(match.re, pattern)
        self.assertEqual(match.group(1), "value")
        re.purge()
        self.assertIs(reference(), pattern)
        del pattern
        self.assertIs(reference(), match.re)
        self.assertEqual(match.group(1), "value")
        del match
        self.assertIsNone(reference())

    def test_native_fifo_churn_preserves_public_patterns_and_fallback(self):
        pattern = re.compile(r"shared-key-held-(\w+)")
        held = pattern.search("shared-key-held-value")
        for index in range(514):
            text = f"shared-key-churn-{index}"
            self.assertEqual(native.search(text, text, 0), (2, 0, len(text)))
        self.assertEqual(held.group(1), "value")
        self.assertIs(held.re, pattern)
        self.assertEqual(re.search(pattern, "shared-key-held-value").group(1), "value")
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
