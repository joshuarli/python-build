"""Observe warning filter protocols, formatting callbacks and native dispatch."""
import types
import warnings
import _warnings_rs as native


item = ("ignore", None, UserWarning, None, 0)
other = ("always", None, RuntimeWarning, None, 0)
filters = [other, item]
assert native.add_filter(filters, item, False) is None
assert filters == [item, other]
assert native.add_filter(filters, item, True) is None
assert filters == [item, other]
assert native.add_filter(filters, other, False) is None
assert filters == [other, item]

failure = RuntimeError("filter callback")
class BrokenFilters:
    def remove(self, value):
        raise failure
try:
    native.add_filter(BrokenFilters(), item, False)
except RuntimeError as error:
    assert error is failure
else:
    raise AssertionError("filter callback error lost")

class ReentrantFilters(list):
    def insert(self, index, value):
        assert native.add_filter([], other, True) is None
        super().insert(index, value)
filters = ReentrantFilters()
assert native.add_filter(filters, item, False) is None
assert filters == [item]

seen = []
class Field:
    def __init__(self, value):
        self.value = value
    def __format__(self, spec):
        assert spec == ""
        seen.append(self.value)
        return self.value
message = types.SimpleNamespace(filename=Field("sample.py"), lineno=Field("7"),
                                message=Field("notice"))
assert native.format_message(message, Field("UserWarning")) == "sample.py:7: UserWarning: notice\n"
assert seen == ["sample.py", "7", "UserWarning", "notice"]
class BrokenField:
    def __format__(self, spec):
        raise failure
message.filename = BrokenField()
try:
    native.format_message(message, "UserWarning")
except RuntimeError as error:
    assert error is failure
else:
    raise AssertionError("format callback error lost")

original_add, original_format = native.add_filter, native.format_message
calls = []
def traced_add(*args):
    calls.append("filter")
    return original_add(*args)
def traced_format(*args):
    calls.append("format")
    return original_format(*args)
native.add_filter, native.format_message = traced_add, traced_format
try:
    with warnings.catch_warnings():
        warnings.simplefilter("always", UserWarning)
        assert "filter" in calls
        assert warnings.formatwarning("notice", UserWarning, "sample.py", 7, line="") == "sample.py:7: UserWarning: notice\n"
        assert "format" in calls
        original_override = warnings.formatwarning
        warnings.formatwarning = lambda *args, **kwargs: "overridden"
        try:
            record = warnings.WarningMessage(UserWarning("notice"), UserWarning,
                                             "sample.py", 7, line="")
            assert warnings._formatwarnmsg(record) == "overridden"
        finally:
            warnings.formatwarning = original_override
finally:
    native.add_filter, native.format_message = original_add, original_format
print("OK warnings core filter protocols, callback errors/reentry, formatting and override precedence")
