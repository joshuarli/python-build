import gc
import _strptime
import _strptime_rs

fixtures = (
    ("2004-02-29 23:04:05.123456+05:30", "%Y-%m-%d %H:%M:%S.%f%z"),
    ("Mon Jan 01 12:00:00 AM 2024", "%a %b %d %I:%M:%S %p %Y"),
    ("2024 01 1", "%G %V %u"),
    ("2024 001", "%Y %j"),
    ("2024 05 0", "%Y %U %w"),
    ("2024 05 1", "%Y %W %w"),
    ("2024-01-01 UTC", "%Y-%m-%d %Z"),
)
for text, format in fixtures:
    rust = _strptime._strptime(text, format)
    module = _strptime._strptime_rs
    try:
        _strptime._strptime_rs = None
        assert rust == _strptime._strptime(text, format), (text, format, rust)
    finally:
        _strptime._strptime_rs = module

missing = -(1 << 63)
def fresh_locale():
    def fresh(text):
        return (text + "!")[:-1]
    weekdays = tuple(fresh(text) for text in ("måndag", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))
    months = tuple(fresh("märz" if index == 3 else "month" + str(index)) for index in range(13))
    return (weekdays, weekdays, months, months, (fresh("am"), fresh("pm")), ((fresh("gmt"), fresh("utc")), ()), (fresh("zone0"), fresh("zone1")), 0)
# Each locale owns fresh Unicode objects. Results must own their integers,
# and a later call must never read a buffer retained from an earlier call.
for _ in range(100):
    locale = fresh_locale()
    result = _strptime_rs.parse_groups((("Y", "2024"), ("B", "MÄRZ"), ("d", "4"), ("A", "MÅNDAG")), *locale)
    assert len(result) == 16 and result[1:4] == (2024, 3, 4) and result[14:] == (0, 64), result
    del locale
    gc.collect()
    assert result[1:4] == (2024, 3, 4)
locale = fresh_locale()
assert _strptime_rs.parse_groups((), *locale) == (missing, missing, 1, 1, 0, 0, 0, 0, -1, missing, 0, missing, missing, missing, missing, missing)
assert _strptime_rs.parse_groups((("unsupported", "1"),), *locale) == ()
assert _strptime_rs.parse_groups((("Y",),), *locale) == ()
assert _strptime_rs.parse_groups((("Y", "2024"),), locale[0], locale[1], locale[2][:-1], *locale[3:]) == ()
assert _strptime_rs.parse_groups((("Z", "UTC"),), *locale)[8] == 0
try:
    _strptime_rs.parse_groups((("Y", "\ud800"),), *locale)
except UnicodeEncodeError:
    pass
else:
    raise AssertionError("surrogate input must retain UnicodeEncodeError")
print("borrowed owners, Unicode locale, missing groups, malformed lengths, and public fallback parity passed")
