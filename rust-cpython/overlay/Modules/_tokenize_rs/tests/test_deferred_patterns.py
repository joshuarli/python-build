import io
import importlib
import sys
import tokenize

# Unicode token generation needs neither encoding cookies nor legacy regex grammar.
assert '_tokenize_patterns' not in sys.modules
assert 'endpats' not in vars(tokenize) and 'endpats' in dir(tokenize)
try:
    del tokenize.endpats
except AttributeError:
    pass
else:
    raise AssertionError('unresolved grammar names are absent in raw module globals')
original_scan = tokenize._tokenize_rs.scan_line
successful_scans = []
def recording_scan(line):
    result = original_scan(line)
    if result is not None:
        successful_scans.append(line)
    return result
try:
    tokenize._tokenize_rs.scan_line = recording_scan
    simple = list(tokenize.generate_tokens(io.StringIO('x = 1 + 2\n' * 64).readline))
finally:
    tokenize._tokenize_rs.scan_line = original_scan
assert len(successful_scans) == 64
assert len(simple) == 385 and simple[-3].string == '2'
source = 'def sample(x):\n    return "café" # comment\n'
actual = list(tokenize.generate_tokens(io.StringIO(source).readline))
expected = list(tokenize._c_tokenizer_tokens(
    io.StringIO(source).readline, None, True, (), 0))
assert actual == expected
assert '_tokenize_patterns' not in sys.modules

class Provider:
    name = 'source.py'

    def __init__(self, lines):
        self.lines = iter(lines)
        self.calls = 0

    def readline(self):
        self.calls += 1
        return next(self.lines, b'')

# A first-line cookie must retain its bytes and avoid reading the next line.
cookie = b'# coding: latin-1\n'
provider = Provider((cookie, b'value = "\xe9"\n'))
encoding, consumed = tokenize.detect_encoding(provider.readline)
assert encoding == 'iso-8859-1' and consumed == [cookie]
assert consumed[0] is cookie and provider.calls == 1
assert '_tokenize_patterns' not in sys.modules
assert tokenize.cookie_re.pattern == br'^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)'
assert tokenize.blank_re.pattern == br'^[ \t\f]*(?:[#\r\n]|$)'

# Existing module bindings remain replaceable providers after materialization.
class RecordingPattern:
    def __init__(self, pattern):
        self.pattern = pattern
        self.lines = []

    def match(self, line):
        self.lines.append(line)
        return self.pattern.match(line)

original_cookie = tokenize.cookie_re
original_lookup = tokenize.lookup
recording_cookie = RecordingPattern(original_cookie)
lookups = []
def recording_lookup(name):
    lookups.append(name)
    return original_lookup(name)
try:
    tokenize.cookie_re = recording_cookie
    tokenize.lookup = recording_lookup
    assert tokenize.detect_encoding(Provider((cookie,)).readline)[0] == 'iso-8859-1'
    assert recording_cookie.lines == [cookie] and lookups == ['iso-8859-1']
finally:
    tokenize.cookie_re = original_cookie
    tokenize.lookup = original_lookup

for first, message in ((b'# coding: no-such-encoding\n', 'unknown encoding'),
                       (b'x = 1\x00\n', 'null bytes')):
    provider = Provider((first,))
    try:
        tokenize.detect_encoding(provider.readline)
    except SyntaxError as error:
        assert message in str(error), str(error)
        if message == 'unknown encoding':
            assert 'source.py' in str(error), str(error)
    else:
        raise AssertionError('encoding error must survive pattern deferral')

byte_source = b'\xef\xbb\xbfx = 1\n'
assert list(tokenize.tokenize(io.BytesIO(byte_source).readline))[0].string == 'utf-8'
assert '_tokenize_patterns' not in sys.modules

# Attribute access materializes the compatibility objects with their original values.
# First access must use import-time grammar inputs despite later builder changes.
original_group = tokenize.group
original_prefixes = tokenize._all_string_prefixes
expected_special = original_group(*map(tokenize.re.escape,
                                     sorted(tokenize.EXACT_TOKEN_TYPES, reverse=True)))
def replaced_builder(*args):
    raise AssertionError('deferred construction consulted a replaced tokenizer builder')
try:
    tokenize.group = replaced_builder
    tokenize._all_string_prefixes = replaced_builder
    tokenize.EXACT_TOKEN_TYPES['__extra_operator__'] = -1
    tokenize.PseudoToken = 'overridden before materialization'
    assert tokenize.StringPrefix.startswith('(')
    assert tokenize.Special == expected_special
    assert tokenize.PseudoToken == 'overridden before materialization'
finally:
    tokenize.group = original_group
    tokenize._all_string_prefixes = original_prefixes
    tokenize.EXACT_TOKEN_TYPES.pop('__extra_operator__', None)

assert set(tokenize.StringPrefix[1:-1].split('|')) == tokenize._all_string_prefixes()
assert '_tokenize_patterns' in sys.modules
prefixes = tokenize._all_string_prefixes()
assert tokenize.single_quoted == {prefix + quote for prefix in prefixes for quote in ('"', "'")}
assert tokenize.triple_quoted == {prefix + quote for prefix in prefixes for quote in ('"""', "'''")}
assert set(tokenize.endpats) == {
    prefix + quote for prefix in prefixes for quote in ('"', "'", '"""', "'''")}
for text in ('1', '0xff', '1_000', '.25', '3e2', '2j'):
    assert tokenize._compile(tokenize.Number).fullmatch(text), text
assert tokenize._compile(tokenize.Number) is tokenize._compile(tokenize.Number)
assert tokenize.group.__module__ == tokenize._compile.__module__ == 'tokenize'
assert {'cookie_re', 'blank_re', 'PseudoToken', 'endpats'} <= set(dir(tokenize))
# Reload owns new mutable grammar containers instead of reusing a helper cache.
old_endpats = tokenize.endpats
old_single = tokenize.single_quoted
old_triple = tokenize.triple_quoted
old_endpats['__extra__'] = 'changed'
old_single.add('__extra__')
old_triple.add('__extra__')
importlib.reload(tokenize)
assert 'endpats' not in vars(tokenize)
assert tokenize.endpats is not old_endpats and '__extra__' not in tokenize.endpats
assert tokenize.single_quoted is not old_single and '__extra__' not in tokenize.single_quoted
assert tokenize.triple_quoted is not old_triple and '__extra__' not in tokenize.triple_quoted
assert tokenize.PseudoToken != 'overridden before materialization'
assert tokenize._all_string_prefixes() is not tokenize._all_string_prefixes()
del tokenize.Token
assert 'Token' not in dir(tokenize)
try:
    tokenize.Token
except AttributeError:
    pass
else:
    raise AssertionError('deleted materialized grammar must not be recreated')
print('deferred grammar ownership, successful Rust dispatch, provider/encoding errors, builders, and reload passed')
