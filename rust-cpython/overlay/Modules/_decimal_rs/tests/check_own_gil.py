"""Exercise private owned buffers and the public Decimal route with an own GIL."""
import _interpreters

config = _interpreters.new_config("isolated", gil="own")
interpreter = _interpreters.create(config)
try:
    assert _interpreters.get_config(interpreter).gil == "own"
    result = _interpreters.run_string(interpreter, '''
import _decimal_rs
import decimal
large = "9" * 1001
assert _decimal_rs.multiply_exact_integers(large, "+1_") == large
assert _decimal_rs.add_exact_integers(large, "1") == "1" + "0" * 1001
try:
    _decimal_rs.add_exact_integers(large, "_1")
except ValueError:
    pass
else:
    raise AssertionError("invalid coefficient accepted")
with decimal.localcontext() as context:
    context.prec = 260
    number = decimal.Decimal("9" * 128)
    assert number + decimal.Decimal(1) == decimal.Decimal(10**128)
    assert number * number == decimal.Decimal((10**128 - 1)**2)
    assert not any(context.flags.values())
''')
    assert result is None, result
finally:
    _interpreters.destroy(interpreter)
print("OK decimal owned coefficients and native context under an independent GIL")
