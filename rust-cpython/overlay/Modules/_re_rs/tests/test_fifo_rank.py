"""Preserve public regex lifetimes and native calls through cache churn."""

import gc
import re
import threading
import unittest
import weakref

import _re_rs


class FifoRankTests(unittest.TestCase):
    def setUp(self):
        re.purge()
        self.addCleanup(re.purge)
        self.native_prepare = _re_rs.prepare
        self.native_search = _re_rs.search
        self.calls = []

        def prepare(pattern, flags):
            result = self.native_prepare(pattern, flags)
            self.calls.append(("prepare", pattern, flags, result))
            return result

        def search(pattern, subject, flags):
            result = self.native_search(pattern, subject, flags)
            self.calls.append(("search", pattern, flags, result))
            return result

        _re_rs.prepare = prepare
        _re_rs.search = search
        self.addCleanup(setattr, _re_rs, "prepare", self.native_prepare)
        self.addCleanup(setattr, _re_rs, "search", self.native_search)

    def test_pattern_identity_weakref_and_held_match_survive_native_fifo_churn(self):
        pattern = re.compile(r"item=([0-9]+)")
        reference = weakref.ref(pattern)
        self.assertIs(re.compile(pattern.pattern), pattern)
        match = re.search(pattern, "item=42")
        self.assertIs(match.re, pattern)
        self.assertEqual(match.groups(), ("42",))
        self.assertIn(("prepare", pattern.pattern, 32, True), self.calls)
        self.assertIn(("search", pattern.pattern, 32, (2, 0, 7)), self.calls)
        for index in range(520):
            text = f"public_{index}_42"
            found = re.search(f"public_{index}_[0-9]+", text)
            self.assertEqual(found.span(), (0, len(text)))
        del pattern
        re.purge()
        gc.collect()
        self.assertIs(reference(), match.re)
        self.assertEqual(match.group(1), "42")
        del match
        gc.collect()
        self.assertIsNone(reference())

    def test_eight_threads_keep_native_results_and_allow_public_reentry(self):
        barrier = threading.Barrier(8)
        errors = []
        wrapped_search = _re_rs.search
        local = threading.local()

        def search(pattern, subject, flags):
            if pattern.startswith("outer_") and not getattr(local, "inside", False):
                local.inside = True
                try:
                    self.assertEqual(re.search("inner_[0-9]+", "inner_42").span(), (0, 8))
                finally:
                    local.inside = False
            return wrapped_search(pattern, subject, flags)

        _re_rs.search = search

        def worker(number):
            try:
                barrier.wait()
                for index in range(80):
                    text = f"outer_{number}_{index}_42"
                    pattern = f"outer_{number}_{index}_[0-9]+"
                    self.assertEqual(re.search(pattern, text).span(), (0, len(text)))
            except BaseException as error:
                errors.append(error)

        workers = [threading.Thread(target=worker, args=(number,)) for number in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        if errors:
            raise errors[0]
        outer_calls = [call for call in self.calls if call[0] == "search" and call[1].startswith("outer_")]
        self.assertEqual(len(outer_calls), 640)
        self.assertTrue(all(call[3][0] == 2 for call in outer_calls))

    def test_native_calls_and_native_fallback_keep_captures_flags_and_errors(self):
        cases = [
            (r"word=([A-Za-z]+)", "word=hello", 0),
            (r"value=(\d+)$", "value=123", 0),
            (r"(?=a)a", "a", 0),
            (r"abc", "ABC", re.IGNORECASE),
            ("é", "é", 0),
            (b"abc", b"abc", 0),
        ]
        for pattern, subject, flags in cases:
            with self.subTest(pattern=pattern, flags=flags):
                expected = re._compiler.compile(pattern, flags).search(subject)
                actual = re.search(pattern, subject, flags)
                self.assertEqual(actual.span(), expected.span())
                self.assertEqual(actual.groups(), expected.groups())
        self.assertIn(("search", r"word=([A-Za-z]+)", 32, (2, 0, 10)), self.calls)
        self.assertIn(("search", r"value=(\d+)$", 32, (0, 0, 0)), self.calls)
        self.assertEqual(self.native_search("abc", "ABC", int(re.IGNORECASE)), (0, 0, 0))
        original = re._rust_re
        try:
            re._rust_re = None
            self.assertEqual(re.search(r"word=([A-Za-z]+)", "word=hello").groups(), ("hello",))
        finally:
            re._rust_re = original
        with self.assertRaises(re.PatternError):
            re.search("[", "text")
        with self.assertRaises(TypeError):
            re.search("abc", 42)


if __name__ == "__main__":
    unittest.main()
