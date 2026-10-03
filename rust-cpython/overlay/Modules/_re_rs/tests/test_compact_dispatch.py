"""Check regex dispatch spans, admission, cache lifetime and Unicode fallback."""

import unittest


class CompactDispatchTests(unittest.TestCase):
    def test_captured_engine_dispatch_preserves_whole_match_spans(self):
        import re
        import _re_rs
        patterns = (
            r"^(a+)(b*)", r"\A([a-z]+):(\d+)\z", r"(a|ab)(b?)",
            r"((ab)+)(c*)", r"(a*)(b*)", r"(a+?)(a*)", r"(ab)?c",
            r"(?:ab|a)(b+)", r"\b([a-z]+)\b", r"([\s\d]+)([A-Z]*)",
        )
        subjects = ("", "a", "ab", "aaaabbb", "ababccc", "abc", "x abc y",
                    "name:123", " 12AB", "\t34", "\nab", "zzabc")
        for pattern in patterns:
            assert _re_rs.prepare(pattern, 32), pattern
            oracle = re._compiler.compile(pattern, 0)
            for subject in subjects:
                expected = oracle.search(subject)
                result = _re_rs.search(pattern, subject, 32)
                assert result == ((1, 0, 0) if expected is None else
                                  (2, *expected.span())), (pattern, subject, result, expected)
                actual = re.search(pattern, subject)
                assert (actual is None) == (expected is None)
                if expected is not None:
                    assert (actual.span(), actual.groups()) == (expected.span(), expected.groups())

    def test_original_engine_admission_and_cache_eviction(self):
        import re
        import _re_rs
        # This class syntax is accepted by the original parser but not smaller engines.
        assert _re_rs.prepare('[a-z--m]', 32)
        assert _re_rs.search('[a-z--m]', 'z', 32)[0] != 0
        assert not _re_rs.prepare('(' * 251 + 'a' + ')' * 251, 32)
        assert _re_rs.search('(ab){100000000}', 'ab', 32) == (0, 0, 0)
        assert _re_rs.search('(?=a)', 'a', 32) == (0, 0, 0)
        assert _re_rs.search('(a)', 'a', 2) == (0, 0, 0)
        assert _re_rs.search('(a)', '\N{SNOWMAN}a', 32) == (0, 0, 0)
        for index in range(520):
            pattern = rf'\A({index}:)(a+)'
            subject = f'{index}:aaa'
            expected = re._compiler.compile(pattern, 0).search(subject)
            assert _re_rs.search(pattern, subject, 32) == (2, *expected.span())
        assert _re_rs.search(r'\A(0:)(a+)', '0:aaa', 32) == (2, 0, 5)

    def test_unicode_whitespace_and_escape_fallback_preserves_native_behavior(self):
        import re
        import _re_rs
        cases = (
            (r'(\s+)(word)', '\N{NO-BREAK SPACE}word', 0),
            (r'(\S+)', '\N{NO-BREAK SPACE}word', 0),
            (r'(\s+)', '\N{NO-BREAK SPACE}', re.ASCII),
            (r'(\x1c+)', 'x\x1c\x1c', 0),
            (r'(\u00a0+)', '\N{NO-BREAK SPACE}', 0),
        )
        for pattern, subject, flags in cases:
            compiled = re._compiler.compile(pattern, flags)
            assert _re_rs.search(pattern, subject, compiled.flags) == (0, 0, 0)
            expected = compiled.search(subject)
            actual = re.search(pattern, subject, flags)
            assert (actual is None) == (expected is None)
            if expected is not None:
                assert (actual.span(), actual.groups()) == (expected.span(), expected.groups())


if __name__ == "__main__":
    unittest.main()
