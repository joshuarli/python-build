"""Exercise native INI ownership and calls under the main and independent GILs."""

import sys

assert 're' not in sys.modules
import configparser
import gc
import io
import _configparser_rs
import _interpreters

assert 're' in dir(configparser)
assert 're' not in sys.modules
native_read = _configparser_rs.read_ini
native_write = _configparser_rs.write_ini
reads = []
writes = []

def traced_read(*args):
    result = native_read(*args)
    reads.append(result is None)
    return result

def traced_write(*args):
    result = native_write(*args)
    writes.append(result)
    return result

_configparser_rs.read_ini = traced_read
_configparser_rs.write_ini = traced_write
try:
    parser = configparser.ConfigParser()
    parser.read_string('[s]\nkey = 日本語\n')
    output = io.StringIO()
    parser.write(output)
    assert output.getvalue() == '[s]\nkey = 日本語\n\n'
    assert reads == [True] and writes == [True]
    assert 're' not in sys.modules

    for serial in range(24):
        source_name = f'long section {serial} ' + '日本語' * 11000
        source_value = f'long value {serial} ' + 'x' * 131072
        parser = configparser.ConfigParser()
        parser.read_string(f'[{source_name}]\nkey = {source_value}\n')
        name = next(iter(parser._sections))
        value = parser._sections[name]['key']
        assert name == source_name and value == source_value
        assert not sys._is_immortal(name) and not sys._is_immortal(value)
        output = io.StringIO()
        parser.write(output)
        assert output.getvalue() == f'[{source_name}]\nkey = {source_value}\n\n'
        del parser
        gc.collect()
        assert sys.getrefcount(name) == 2 and sys.getrefcount(value) == 2
    assert reads == [True] * 25 and writes == [True] * 25
finally:
    _configparser_rs.read_ini = native_read
    _configparser_rs.write_ini = native_write

text = '[shared section with spaces]\nkey = shared value with spaces\n'
first = configparser.ConfigParser()
second = configparser.ConfigParser()
first.read_string(text)
second.read_string(text)
first_name = first.sections()[0]
second_name = second.sections()[0]
assert first_name is second_name
assert first._sections[first_name]['key'] is second._sections[second_name]['key']
first['shared section with spaces']['key'] = 'changed'
assert second['shared section with spaces']['key'] == 'shared value with spaces'

parser = configparser.ConfigParser()
parser.read_string('[s]\ninteger=42\nreal=2.5\nflag=yes\n')
proxy = parser['s']
assert proxy.getint('integer') == 42
assert proxy.getfloat('real') == 2.5
assert proxy.getboolean('flag') is True
assert proxy.getint('missing', fallback=7) == 7
parser.getint = lambda *args, **kwargs: 999
assert proxy.getint('integer') == 42
proxy.get = lambda *args, **kwargs: 888
assert proxy.getint('integer') == 42

class CustomProxy(configparser.SectionProxy):
    accesses = 0

    @property
    def get(self):
        self.accesses += 1
        return super().get

custom = CustomProxy(parser, 's')
assert custom.accesses == len(parser.converters)
assert custom.getint('integer') == 999

original_get = configparser.SectionProxy.get
def custom_get(self, *args, **kwargs):
    return original_get(self, *args, **kwargs)
configparser.SectionProxy.get = custom_get
try:
    customized = configparser.SectionProxy(parser, 's')
    assert customized.getint('integer') == 999
    assert customized.getint.func is not customized.getfloat.func
finally:
    configparser.SectionProxy.get = original_get

original_proxy = configparser.SectionProxy
original_getattribute = original_proxy.__getattribute__
def observed_getattribute(self, name):
    if name == 'get':
        attributes = original_getattribute(self, '__dict__')
        attributes['get_accesses'] = attributes.get('get_accesses', 0) + 1
    return original_getattribute(self, name)

class ObservedProxy(original_proxy):
    __getattribute__ = observed_getattribute

access_counts = []
configparser.SectionProxy = ObservedProxy
try:
    parser = configparser.ConfigParser()
    access_counts.append(parser['DEFAULT'].get_accesses)
finally:
    configparser.SectionProxy = original_proxy
original_proxy.__getattribute__ = observed_getattribute
try:
    parser = configparser.ConfigParser()
    access_counts.append(parser['DEFAULT'].get_accesses)
finally:
    original_proxy.__getattribute__ = original_getattribute
assert access_counts == [3, 3], access_counts

interp = _interpreters.create()
try:
    result = _interpreters.run_string(interp, '''
import configparser, gc, io, sys, _configparser_rs
reads = []
writes = []
native_read = _configparser_rs.read_ini
native_write = _configparser_rs.write_ini
def traced_read(*args):
    result = native_read(*args)
    reads.append(result is None)
    return result
_configparser_rs.read_ini = traced_read
def traced_write(*args):
    result = native_write(*args)
    writes.append(result)
    return result
_configparser_rs.write_ini = traced_write
for serial in range(24):
    parser = configparser.ConfigParser()
    parser.read_string('[owned section %d]\\nkey = owned value %d with spaces\\n' % (serial, serial))
    name = next(iter(parser._sections))
    value = parser._sections[name]['key']
    assert not sys._is_immortal(name) and not sys._is_immortal(value)
    output = io.StringIO()
    parser.write(output)
    assert output.getvalue() == '[owned section %d]\\nkey = owned value %d with spaces\\n\\n' % (serial, serial)
    del parser
    gc.collect()
    assert sys.getrefcount(name) == 2 and sys.getrefcount(value) == 2
assert reads == [True] * 24
assert writes == [True] * 24
''')
    assert result is None, result
finally:
    _interpreters.destroy(interp)
print('Native routes under independent GILs, mortal ownership, lazy binding, and proxy overrides passed')
