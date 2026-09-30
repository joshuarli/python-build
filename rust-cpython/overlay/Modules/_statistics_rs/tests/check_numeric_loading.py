"""Check lazy numeric imports and exact integer summary result contracts."""

import subprocess
import sys


IMPORT_CHECK = """
import sys
import statistics

assert sys._is_gil_enabled()
assert 'Decimal' in dir(statistics) and 'Fraction' in dir(statistics)
assert 'decimal' not in sys.modules and 'fractions' not in sys.modules
for call, data, expected in (
    (statistics.mean, [1, 2, 3], 2),
    (statistics.mean, [-2, -1], -1.5),
    (statistics.median, [3, 1, 2], 2),
    (statistics.variance, [1, 2, 3], 1),
    (statistics.pvariance, [1, 2, 3], 2 / 3),
):
    result = call(data)
    assert type(result) is type(expected) and result == expected
assert '_statistics_rs' in sys.modules
assert 'decimal' not in sys.modules and 'fractions' not in sys.modules
assert '_fractions_rs' not in sys.modules and '_re_rs' not in sys.modules

annotations = statistics._decimal_sqrt_of_frac.__annotations__
from statistics import Decimal, Fraction
import decimal
import fractions
assert annotations['return'] is decimal.Decimal
assert Decimal is decimal.Decimal and Fraction is fractions.Fraction
assert statistics.mean([Decimal('1'), Decimal('2')]) == Decimal('1.5')
assert statistics.variance([Fraction(1), Fraction(2)]) == Fraction(1, 2)
assert '_fractions_rs' in sys.modules
"""

RATIO_CHECK = """
import itertools
import random
import statistics
from fractions import Fraction

def reference(n, d):
    return statistics._convert(Fraction(n, d), int)

def outcome(convert, n, d):
    try:
        value = convert(n, d)
        return type(value), value.hex() if type(value) is float else value
    except OverflowError:
        return OverflowError

random = random.Random(12345)
for _ in range(10000):
    n = random.getrandbits(random.randrange(1, 8193)) * random.choice((-1, 1))
    d = max(1, random.getrandbits(random.randrange(1, 8193))) * random.choice((-1, 1))
    assert outcome(reference, n, d) == outcome(statistics._convert_integer_ratio, n, d)

for length in range(1, 6):
    for data in itertools.product(range(-2, 3), repeat=length):
        n, total, squares = len(data), sum(data), sum(x*x for x in data)
        cases = [(statistics.mean, total, n),
                 (statistics.pvariance, n*squares-total*total, n*n)]
        if n > 1:
            cases.append((statistics.variance, n*squares-total*total, n*(n-1)))
        for call, numerator, denominator in cases:
            actual, expected = call(data), reference(numerator, denominator)
            assert type(actual) is type(expected) and actual == expected
"""

OWN_GIL_CHECK = """
import _interpreters

config = _interpreters.new_config('isolated')
assert config.gil == 'own'
interpreter = _interpreters.create(config)
try:
    result = _interpreters.run_string(interpreter, '''
import statistics
assert statistics.mean([1, 2, 3]) == 2
assert statistics.variance([1, 2, 3]) == 1
from statistics import Decimal, Fraction
assert statistics.mean([Decimal('1'), Decimal('2')]) == Decimal('1.5')
assert statistics.variance([Fraction(1), Fraction(2)]) == Fraction(1, 2)
''')
    assert result is None, result
finally:
    _interpreters.destroy(interpreter)
"""


if __name__ == '__main__':
    for check in (IMPORT_CHECK, RATIO_CHECK, OWN_GIL_CHECK):
        subprocess.run([sys.executable, '-s', '-P', '-c', check], check=True)
    print('PASS: numeric loading, exact ratios, public summaries, own GIL')
