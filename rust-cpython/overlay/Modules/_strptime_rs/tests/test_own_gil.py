from pathlib import Path
import _interpreters

# Every Rust call borrows only objects owned by that call's interpreter.
# An independent GIL must load the Rust module and perform public conversions.
config = _interpreters.new_config("isolated", gil="own")
interpreter = _interpreters.create(config)
try:
    assert _interpreters.get_config(interpreter).gil == "own"
    fixtures = str(Path(__file__).with_name("test_borrowed_arguments.py"))
    code = (
        "import _strptime_rs, _strptime; "
        "assert _strptime._strptime_rs is _strptime_rs; "
        "from datetime import datetime; import time; "
        "assert datetime.strptime('2024-03-04', '%Y-%m-%d').isoformat() == '2024-03-04T00:00:00'; "
        "assert time.strptime('2024-03-04', '%Y-%m-%d')[:3] == (2024, 3, 4); "
        f"exec(open({fixtures!r}, encoding='utf-8').read())"
    )
    result = _interpreters.run_string(interpreter, code)
    assert result is None, result
finally:
    _interpreters.destroy(interpreter)
print("direct Rust conversion and borrowed owners under an independent GIL passed")
