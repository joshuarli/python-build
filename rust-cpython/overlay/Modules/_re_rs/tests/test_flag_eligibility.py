"""Exercise regex route eligibility in fresh interpreter processes."""

import subprocess
import sys
import unittest


class FlagEligibilityTests(unittest.TestCase):
    def check_process(self, source):
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", source],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_flags_do_not_load_rust(self):
        for call in ("compile('abc', flag)", "search('abc', 'ABC', flag)"):
            for flag in (2, 8, 16, 64, 98, 112, 256):
                with self.subTest(call=call, flag=flag):
                    self.check_process(f"""
import sys
import re
assert '_re_rs' not in sys.modules
re.{call.replace('flag', str(flag))}
assert '_re_rs' not in sys.modules
""")

    def test_global_inline_flags_do_not_load_rust(self):
        self.check_process("""
import sys
import re
pattern = re.compile('(?i)abc')
assert type(pattern.flags) is int and pattern.flags == 34
assert re.search(pattern, 'ABC').span() == (0, 3)
assert '_re_rs' not in sys.modules
""")

    def test_supported_compile_and_search_execute_rust(self):
        self.check_process("""
import re
import _re_rs
assert _re_rs.prepare('ab[cd]+', 0) is True
assert _re_rs.search('ab[cd]+', 'abcd', 0) == (2, 0, 4)
calls = []
prepare = _re_rs.prepare
search = _re_rs.search
def traced_prepare(pattern, flags):
    result = prepare(pattern, flags)
    calls.append(('prepare', flags, result))
    return result
def traced_search(pattern, string, flags):
    result = search(pattern, string, flags)
    calls.append(('search', flags, result))
    return result
_re_rs.prepare = traced_prepare
_re_rs.search = traced_search
pattern = re.compile('ab[cd]+')
assert type(pattern.flags) is int and pattern.flags == 32
assert re.search(pattern, 'abcd').span() == (0, 4)
assert ('prepare', 32, True) in calls
assert ('search', 32, (2, 0, 4)) in calls
assert re.search(pattern, 'xyz') is None
assert ('search', 32, (1, 0, 0)) in calls
""")

    def test_scoped_inline_flags_keep_supported_flag_route(self):
        self.check_process("""
import sys
import re
pattern = re.compile('(?i:abc)')
assert pattern.flags == 32
assert '_re_rs' in sys.modules
assert re.search(pattern, 'ABC').span() == (0, 3)
""")

    def test_native_validation_precedes_rust_loading(self):
        self.check_process("""
import sys
import re
try:
    re.compile('abc', re.LOCALE)
except ValueError as error:
    assert str(error) == 'cannot use LOCALE flag with a str pattern'
else:
    raise AssertionError('native flag validation was bypassed')
class Text(str):
    pass
assert re.search(Text('abc'), 'abc').span() == (0, 3)
assert re.search(b'abc', b'abc').span() == (0, 3)
assert '_re_rs' not in sys.modules
""")


if __name__ == "__main__":
    unittest.main()
