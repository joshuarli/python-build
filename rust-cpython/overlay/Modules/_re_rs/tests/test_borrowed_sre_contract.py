"""Compare borrowed SRE execution with native compiled Pattern.search."""

import itertools
import gc
import re
import subprocess
import sys
import unittest
import weakref
from unittest import mock


KERNEL_PATTERNS = (
    r'\b(\w+)@(\w+)\.com\b',
    r'^record=(\d+);name=([a-z-]+\d*)',
    r'[A-Z][a-z]+ \d{4}',
    r'(?:GET|POST) (/\S*) HTTP/1\.[01]',
    r'value=(\d+)$',
    r'\d+\.\d+\.\d+\.\d+',
)
PORTABLE_PATTERNS = (
    '', 'a', '.', 'ab', '^a', r'\A', r'\z',
    'a|ab', 'ab|a', '(a|ab)b', '(?:ab|a)*',
    'a*', 'a+', 'a?', 'a*?', 'a+?', 'a??', 'a{0,2}', 'a{1,3}?',
    '(?:a?)*', '(?:a*)*', '(?:a?)*?', '(?:a*?)*', '(?:(?:a?)*)*',
    'a(?:b?)*b', '[ab]', '[^ab]', '[a-c]+', '[a-cx-z]+',
    r'\d+', r'\D+', r'\s+', r'\S+', r'\w+', r'\W+', r'\b',
    '(a)(b)?', '((?:a|b)+)',
) + KERNEL_PATTERNS
KERNEL_SUBJECTS = (
    'first@example.com', ' first@example.com ',
    'record=42;name=some-name7', 'xrecord=42;name=a',
    'Alice 2026', 'x Alice 2026 y', 'GET /a HTTP/1.1',
    'POST /a?b=c HTTP/1.0', 'value=23', 'xvalue=23\n',
    '127.0.0.1', 'x127.0.0.1y', 'no match', '\x1c\x1d\x1e\x1f',
)


def match_details(match):
    if match is None:
        return None
    return (match.span(), match.groups(), match.groupdict(), match.regs,
            match.lastindex, match.lastgroup)


class BorrowedSREContractTests(unittest.TestCase):
    def test_pattern_view_ignores_python_identity_spoofs_and_none_source(self):
        import _re_rs
        import _sre
        from re import _constants

        class FakePattern:
            @property
            def __class__(self):
                raise AssertionError('Python class lookup is not native identity')

            @property
            def pattern(self):
                raise AssertionError('foreign pattern attributes must not be read')

            @property
            def flags(self):
                raise AssertionError('foreign flags must not be read')

        fake = FakePattern()
        self.assertFalse(_re_rs.prepare_compiled(fake))
        self.assertEqual(_re_rs.search_compiled(fake, 'a'), (0, 0, 0))
        pattern = re.compile('a')
        with mock.patch.dict(sys.modules, {'_sre': fake}):
            self.assertTrue(_re_rs.prepare_compiled(pattern))
            self.assertEqual(_re_rs.search_compiled(pattern, 'ba'), (2, 1, 2))
        anonymous = _sre.compile(None, 0, [int(_constants.SUCCESS)], 0, {}, ())
        self.assertFalse(_re_rs.prepare_compiled(anonymous))
        self.assertEqual(_re_rs.search_compiled(anonymous, 'a'), (0, 0, 0))
        self.assertTrue(_re_rs.prepare_compiled(pattern))
        self.assertEqual(_re_rs.search_compiled(pattern, 'a'), (2, 0, 1))

    def assert_public_matches_native(self, pattern, subject):
        expected = pattern.search(subject)
        actual = re.search(pattern, subject)
        self.assertEqual(match_details(actual), match_details(expected))
        if actual is not None:
            self.assertIs(actual.re, pattern)

    def test_unicode_whitespace_control_keeps_native_public_match(self):
        pattern = re.compile(r'\s')
        self.assertEqual(pattern.search('\x1c').span(), (0, 1))
        actual = re.search(pattern, '\x1c')
        self.assertIsNotNone(actual)
        self.assertEqual(actual.span(), (0, 1))

    def test_portable_ascii_compiled_spans_match_native_corpus(self):
        import _re_rs
        subjects = [''.join(chars) for length in range(4)
                    for chars in itertools.product('ab\n\x1c', repeat=length)]
        subjects += list(KERNEL_SUBJECTS)
        for flags in (0, re.UNICODE):
            for source in PORTABLE_PATTERNS:
                pattern = re.compile(source, flags)
                admitted = source != r'value=(\d+)$'
                self.assertEqual(_re_rs.prepare_compiled(pattern), admitted, source)
                for subject in subjects:
                    with self.subTest(source=source, flags=flags, subject=subject):
                        expected = pattern.search(subject)
                        span = ((1, 0, 0) if expected is None
                                else (2, *expected.span()))
                        self.assertEqual(_re_rs.search_compiled(pattern, subject),
                                         span if admitted else (0, 0, 0))
                        self.assert_public_matches_native(pattern, subject)

    def test_unicode_category_controls_match_native_program(self):
        import _re_rs
        for source in (r'\s', r'\s+', r'[\s]', r'\S', r'[^\s]'):
            pattern = re.compile(source)
            self.assertTrue(_re_rs.prepare_compiled(pattern))
            for subject in ('\x1c', '\x1d', '\x1e', '\x1f'):
                with self.subTest(source=source, subject=repr(subject)):
                    expected = pattern.search(subject)
                    span = (1, 0, 0) if expected is None else (2, *expected.span())
                    self.assertEqual(_re_rs.search_compiled(pattern, subject), span)
                    self.assert_public_matches_native(pattern, subject)

    def test_empty_complement_classes_keep_definitive_rust_no_match(self):
        import _re_rs
        original = _re_rs.search_compiled
        calls = []
        def traced(pattern, subject):
            result = original(pattern, subject)
            calls.append((pattern, subject, result))
            return result
        sources = (r'[^\s\S]', r'[^\d\D]', r'[^\w\W]', r'[^\S\s]',
                   r'a[^\s\S]', r'[^\d\D]a', r'[^\w\W]|a')
        with mock.patch.object(_re_rs, 'search_compiled', traced):
            for source in sources:
                pattern = re.compile(source)
                self.assertTrue(_re_rs.prepare_compiled(pattern), source)
                for subject in ('', 'a', 'b', '\x1c', 'aa'):
                    with self.subTest(source=source, subject=subject):
                        expected = pattern.search(subject)
                        span = (1, 0, 0) if expected is None else (2, *expected.span())
                        self.assertEqual(original(pattern, subject), span)
                        self.assert_public_matches_native(pattern, subject)
                        self.assertIs(calls[-1][0], pattern)
                        self.assertEqual(calls[-1][1:], (subject, span))
        self.assertEqual(len(calls), len(sources) * 5)

    def test_public_search_calls_executor_and_preserves_pattern_owner(self):
        import _re_rs
        original = _re_rs.search_compiled
        calls = []
        def traced(pattern, subject):
            calls.append((pattern, subject))
            return original(pattern, subject)
        pattern = re.compile(r'(a)(b)?')
        reference = weakref.ref(pattern)
        self.assertIs(re.compile(pattern), pattern)
        with mock.patch.object(_re_rs, 'search_compiled', traced):
            for subject in ('ab', 'za', 'zzz'):
                self.assert_public_matches_native(pattern, subject)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(owner is pattern for owner, _ in calls))
        re.purge()
        self.assertIs(reference(), pattern)
        self.assert_public_matches_native(pattern, 'ab')
        self.assertEqual(pattern.search('ab').groupdict(), {})
        calls.clear()
        re.purge()
        del pattern
        gc.collect()
        self.assertIsNone(reference())

    def test_legacy_hooks_keep_string_arguments_and_public_reentry(self):
        import _re_rs
        old_prepare, old_search = _re_rs.prepare, _re_rs.search
        calls = []
        def prepare(source, flags):
            calls.append(('prepare', source, flags))
            self.assertEqual(re.compile('sentinel', re.I).search('SENTINEL').span(), (0, 8))
            return old_prepare(source, flags)
        def search(source, subject, flags):
            calls.append(('search', source, subject, flags))
            return old_search(source, subject, flags)
        def forbidden(*args):
            self.fail('compiled executor bypassed replaced legacy hooks')
        with mock.patch.object(_re_rs, 'prepare', prepare), \
             mock.patch.object(_re_rs, 'search', search), \
             mock.patch.object(_re_rs, 'prepare_compiled', forbidden), \
             mock.patch.object(_re_rs, 'search_compiled', forbidden):
            re.purge()
            pattern = re.compile('ab[cd]+')
            for subject in ('abcd', 'xabcd', 'none'):
                self.assert_public_matches_native(pattern, subject)
        self.assertGreaterEqual(sum(row[0] == 'prepare' for row in calls), 1)
        self.assertEqual(sum(row[0] == 'search' for row in calls), 3)
        self.assertTrue(all(type(row[1]) is str for row in calls))

    def test_missing_guard_or_compiled_method_keeps_legacy_dispatch(self):
        import _re_rs
        pattern = re.compile('ab[cd]+')
        for missing in ('_legacy_hooks_intact', 'prepare_compiled', 'search_compiled'):
            original = getattr(_re_rs, missing)
            try:
                delattr(_re_rs, missing)
                self.assert_public_matches_native(pattern, 'abcd')

                self.assert_public_matches_native(pattern, 'none')
            finally:
                setattr(_re_rs, missing, original)
        for guard in (None, lambda: False):
            def forbidden(*args):
                self.fail('compiled executor used without an affirmative native guard')
            with mock.patch.object(_re_rs, '_legacy_hooks_intact', guard), \
                 mock.patch.object(_re_rs, 'prepare_compiled', forbidden), \
                 mock.patch.object(_re_rs, 'search_compiled', forbidden):
                self.assert_public_matches_native(pattern, 'abcd')

        class LegacyOnlyHelper:
            _legacy_hooks_intact = True
            def prepare(self, source, flags):
                calls.append(('prepare', source, flags))
                return False
            def search(self, source, subject, flags):
                calls.append(('search', source, subject, flags))
                return (0, 0, 0)
        calls = []
        with mock.patch.object(re, '_rust_re', LegacyOnlyHelper()):
            self.assert_public_matches_native(pattern, 'abcd')
        self.assertEqual([row[0] for row in calls], ['prepare', 'search'])

    def test_hooks_replaced_before_first_helper_get_are_not_bypassed(self):
        code = r'''
import _re_rs
calls = []
p, s = _re_rs.prepare, _re_rs.search
def prepare(source, flags):
    calls.append(('prepare', source))
    return p(source, flags)
def search(source, text, flags):
    calls.append(('search', source))
    return s(source, text, flags)
def forbidden(*args):
    raise AssertionError('compiled hook bypass')
_re_rs.prepare = prepare
_re_rs.search = search
_re_rs.prepare_compiled = forbidden
_re_rs.search_compiled = forbidden
import re
assert re._rust_re is re._RUST_RE_UNSET
pattern = re.compile('ab[cd]+')
assert re.search(pattern, 'abcd').span() == pattern.search('abcd').span()
assert any(row[0] == 'prepare' for row in calls)
assert any(row[0] == 'search' for row in calls)
'''
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_inputs_keep_native_fallback_and_errors(self):
        import _re_rs
        cases = (
            (b'(a)', b'za', 0), ('é', 'xé', 0), ('a', 'éa', 0),
            ('a', 'A', re.I), ('^a', 'x\na', re.M), ('.', '\n', re.S),
            ('a b', 'ab', re.X), (r'\s', '\x1c', re.ASCII),
            (r'(a)\1', 'aa', 0), (r'(?=a)a', 'a', 0),
            (r'(?P<first>a)', 'a', 0), (r'a$', 'a', 0), (r'\B', 'aa', 0),
        )
        for source, subject, flags in cases:
            pattern = re.compile(source, flags)
            with self.subTest(source=source, subject=subject, flags=flags):
                self.assertEqual(_re_rs.search_compiled(pattern, subject), (0, 0, 0))
                if subject != 'éa':
                    self.assertFalse(_re_rs.prepare_compiled(pattern))
                self.assert_public_matches_native(pattern, subject)
        for source in ('(', '[', '*a'):
            with self.assertRaises(re.PatternError):
                re.compile(source)
        with self.assertRaises(TypeError):
            re.search(re.compile('a'), b'a')
        with self.assertRaises(ValueError):
            re.search(re.compile('a'), 'a', re.I)

    def test_private_boundary_rejects_wrong_types_and_accepts_unicode_subclass(self):
        import _re_rs
        for args in ((), ('a',), (None,), (re.compile('a'), 0)):
            self.assertFalse(_re_rs.prepare_compiled(*args))
        for args in ((), ('a', 'a'), (None, 'a'), (re.compile('a'), b'a')):
            self.assertEqual(_re_rs.search_compiled(*args), (0, 0, 0))
        class Text(str):
            pass
        self.assertEqual(_re_rs.search_compiled(re.compile('a'), Text('za')), (2, 1, 2))
        self.assert_public_matches_native(re.compile('a'), Text('za'))

    def test_own_gil_interpreter_keeps_native_fallback(self):
        code = r'''
import _interpreters
interpreter = _interpreters.create()
try:
    result = _interpreters.run_string(interpreter, """
import re
for source, subject, flags in ((r'\s', '\x1c', 0), ('ab[cd]+', 'xabcd', 0),
                               ('a', 'A', re.I), (b'a', b'za', 0)):
    pattern = re.compile(source, flags)
    expected = pattern.search(subject)
    actual = re.search(pattern, subject)
    assert (None if actual is None else actual.span()) == (None if expected is None else expected.span())
assert re._get_rust_re() is None
""")
    assert result is None, result
finally:
    _interpreters.destroy(interpreter)
'''
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
