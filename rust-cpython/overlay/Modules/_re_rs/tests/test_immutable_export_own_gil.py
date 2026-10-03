"""Own-GIL rejection and public fallback require separate native admission."""
import unittest

import _interpreters
import _re_rs as native


class ImmutableRegexOwnGilTests(unittest.TestCase):
    def test_isolated_import_stays_rejected_and_outer_methods_survive(self):
        held = native.search
        interpreter = _interpreters.create("isolated")
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, "own")
            result = _interpreters.run_string(interpreter, r"""
try:
    import _re_rs
except ImportError:
    pass
else:
    raise AssertionError('regex helper unexpectedly supports own-GIL imports')
import re
assert re._get_rust_re() is None
assert re.compile(r'(ab|cd)+').search('abcd!').group(1) == 'cd'
assert re.search(r'a+', 'zaaa').span() == (1, 4)
assert re.search(r'\s', '\u2003').span() == (0, 1)
assert re.escape('a+b') == r'a\+b'
""")
            self.assertIsNone(result)
        except BaseException as primary:
            try:
                _interpreters.destroy(interpreter)
            except BaseException as cleanup:
                primary.add_note(f"interpreter destruction also failed: {cleanup!r}")
            raise
        else:
            _interpreters.destroy(interpreter)
        self.assertIs(native.search, held)
        self.assertIs(held.__self__, native)
        self.assertEqual(held("a+", "zaaa", 0), (2, 1, 4))


if __name__ == "__main__":
    unittest.main()
