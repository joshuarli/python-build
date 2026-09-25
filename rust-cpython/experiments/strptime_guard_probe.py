"""Record routing observations for the optional numeric strptime source."""

import datetime
import json
import locale
import re

import _rust_strptime_numeric
import _strptime


FORMAT = "%Y/%m/%d %H:%M:%S"
STAMP = "2024/03/17 11:22:33"
calls = 0
original_scan = _rust_strptime_numeric.scan


def counted_scan(value):
    global calls
    calls += 1
    return original_scan(value)


_rust_strptime_numeric.scan = counted_scan
observations = []


def observe(name, value=STAMP, format=FORMAT, cls=datetime.datetime):
    before = calls
    try:
        result = _strptime._strptime_datetime_datetime(cls, value, format)
        outcome = {"value": str(result), "type": type(result).__name__}
    except Exception as error:
        outcome = {"exception": type(error).__name__, "message": str(error)}
    observations.append({"case": name, "scanner_calls": calls - before, **outcome})


observe("cold-cache")
observe("warm-cache")
observe("invalid-second", "2024/03/17 11:22:60")
observe("non-ascii-digit", "2024/03/１７ 11:22:33")
observe("other-format", "2024-03-17 11:22:33", "%Y-%m-%d %H:%M:%S")


class Child(datetime.datetime):
    pass


observe("subclass", cls=Child)

original = _strptime._strptime
try:
    def replacement(*args):
        raise RuntimeError("parser replacement ran")
    _strptime._strptime = replacement
    observe("replaced-parser")
finally:
    _strptime._strptime = original

original = _strptime._getlang
try:
    _strptime._getlang = lambda: _strptime._TimeRE_cache.locale_time.lang
    observe("replaced-locale-function")
finally:
    _strptime._getlang = original

original = locale.getlocale
cached_regex = _strptime._regex_cache[FORMAT]
try:
    def replace_regex_during_locale_check(category):
        _strptime._regex_cache[FORMAT] = re.compile("anything")
        return original(category)
    locale.getlocale = replace_regex_during_locale_check
    observe("locale-hook-replaces-regex")
finally:
    locale.getlocale = original
    _strptime._regex_cache[FORMAT] = cached_regex

original = _strptime.datetime_date
try:
    _strptime.datetime_date = lambda *args: 1 / 0
    observe("replaced-date-constructor")
finally:
    _strptime.datetime_date = original

original = _strptime._TimeRE_cache.locale_time.LC_alt_digits
try:
    _strptime._TimeRE_cache.locale_time.LC_alt_digits = ["not-a-digit"]
    observe("replaced-alternative-digits")
finally:
    _strptime._TimeRE_cache.locale_time.LC_alt_digits = original

original = _strptime._regex_cache[FORMAT]
try:
    _strptime._regex_cache[FORMAT] = re.compile("anything")
    observe("replaced-cached-regex")
finally:
    _strptime._regex_cache[FORMAT] = original

for index in range(6):
    _strptime._regex_cache[str(index)] = re.compile("x")
observe("oversized-cache")
observations.append({"case": "cache-after-eviction", "size": len(_strptime._regex_cache)})

print(json.dumps({"source": _strptime.__file__, "observations": observations}, indent=2))
