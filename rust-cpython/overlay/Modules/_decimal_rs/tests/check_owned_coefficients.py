"""Check inline and Python-owned coefficients, parser errors, and the native route."""
import decimal
import _decimal_rs


def main():
    values = [0, 1, 999_999_999, 1_000_000_000, 10**18 - 1,
              10**127 - 1, 10**128 - 1, 10**270 - 1, 10**600 + 17]
    for left in values:
        for right in values:
            assert _decimal_rs.add_exact_integers(str(left), str(right)) == str(left + right)
            assert _decimal_rs.multiply_exact_integers(str(left), str(right)) == str(left * right)
    for text, value in [("+001_2__3_", 123), ("0_" * 400, 0),
                        ("000" + "9" * 128, 10**128 - 1)]:
        assert _decimal_rs.add_exact_integers(text, "0") == str(value)
        assert _decimal_rs.multiply_exact_integers(text, "+1_") == str(value)
    for method in (_decimal_rs.add_exact_integers, _decimal_rs.multiply_exact_integers):
        for text in ("", "+", "_1", "+_1", "++1", "-1", "1.0", " 1", "١", "1\x00"):
            try:
                method(text, "1")
            except ValueError as error:
                assert str(error) == "invalid decimal integer"
            else:
                raise AssertionError(text)
        for args in ((), ("1",), ("1", "2", "3"), (1, "2")):
            try:
                method(*args)
            except TypeError:
                pass
            else:
                raise AssertionError(args)

    # A large left operand must be discarded when conversion of the right
    # operand fails, while subsequent calls still return exact coefficients.
    large = "9" * 1001
    for method in (_decimal_rs.add_exact_integers, _decimal_rs.multiply_exact_integers):
        for invalid, error_type in (("_1", ValueError), ("1.0", ValueError), (object(), TypeError)):
            try:
                method(large, invalid)
            except error_type:
                pass
            else:
                raise AssertionError(invalid)
        assert method(large, "1") == (str(int(large) + 1) if method is _decimal_rs.add_exact_integers else large)

    calls = []
    original_add = _decimal_rs.add_exact_integers
    original_multiply = _decimal_rs.multiply_exact_integers
    def traced_add(left, right):
        calls.append("add")
        return original_add(left, right)
    def traced_multiply(left, right):
        calls.append("multiply")
        return original_multiply(left, right)
    _decimal_rs.add_exact_integers = traced_add
    _decimal_rs.multiply_exact_integers = traced_multiply
    try:
        with decimal.localcontext() as context:
            context.prec = 260
            context.clear_flags()
            number = decimal.Decimal("9" * 128)
            assert number + decimal.Decimal(1) == decimal.Decimal(10**128)
            assert number * number == decimal.Decimal((10**128 - 1)**2)
            assert calls == ["add", "multiply"]
            assert not any(context.flags.values())
            assert str(decimal.Decimal("-0") * decimal.Decimal(1)) == "-0"
            assert calls == ["add", "multiply"]
            context.prec = 2
            context.clear_flags()
            assert str(decimal.Decimal(999) + decimal.Decimal(1)) == "1.0E+3"
            assert context.flags[decimal.Rounded]
            assert calls == ["add", "multiply"]
    finally:
        _decimal_rs.add_exact_integers = original_add
        _decimal_rs.multiply_exact_integers = original_multiply
    print("OK owned decimal coefficients, parser/error cleanup paths, public Rust route and context flags")


if __name__ == "__main__":
    main()
