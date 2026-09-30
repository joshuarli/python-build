"""Check comparator callbacks and direct Rust imports in an isolated interpreter."""

import _interpreters


CHECK = """
import functools
import _functools_rs

left, right, answer = object(), object(), object()

class Comparison:
    def __lt__(self, other):
        assert other == 0
        return answer
    __le__ = __eq__ = __ne__ = __gt__ = __ge__ = __lt__

def compare(a, b):
    assert a is left and b is right
    return Comparison()

for name in ('less_than', 'less_equal', 'equal', 'not_equal',
             'greater_than', 'greater_equal'):
    assert getattr(_functools_rs, name)(compare, left, right) is answer

error = ValueError('callback failure')
def fail(a, b):
    raise error

try:
    _functools_rs.less_than(fail, left, right)
except ValueError as caught:
    assert caught is error
else:
    raise AssertionError('callback exception was lost')

key = functools.cmp_to_key(lambda a, b: (a > b) - (a < b))
assert sorted([3, 1, 2], key=key) == [1, 2, 3]
assert key(None).obj is None
assert key(left).obj is left
try:
    key.obj
except AttributeError as caught:
    assert caught.args == ('object',)
else:
    raise AssertionError('unwrapped key has an object')

for a, b in ((key, key(1)), (key(1), key)):
    try:
        a < b
    except AttributeError as caught:
        assert caught.args == ('object',)
    else:
        raise AssertionError('unwrapped key was compared')

broken = functools.cmp_to_key(fail)
try:
    broken(left) < broken(right)
except ValueError as caught:
    assert caught is error
else:
    raise AssertionError('public comparator exception was lost')
"""


if __name__ == '__main__':
    config = _interpreters.new_config('isolated')
    assert config.gil == 'own'
    interpreter = _interpreters.create(config)
    try:
        result = _interpreters.run_string(interpreter, CHECK)
        assert result is None, result
    finally:
        _interpreters.destroy(interpreter)
    print('PASS: direct Rust callbacks and public cmp_to_key with own GIL')
