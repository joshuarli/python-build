"""Exercise native public bindings, Rust reachability and module ownership."""

import _socket
import _socket_rs
import builtins
import gc
import inspect
import socket
import sys
import types
import weakref

assert type(socket.inet_pton) is types.BuiltinFunctionType
assert type(socket.inet_ntop) is types.BuiltinFunctionType
for name in ("inet_pton", "inet_ntop"):
    function = getattr(socket, name)
    assert function.__name__ == name and function.__module__ == "socket"
    assert function.__self__ is socket
    assert function.__doc__ == getattr(_socket, name).__doc__
assert str(inspect.signature(socket.inet_pton)) == "(address_family, ip_string, /)"
assert str(inspect.signature(socket.inet_ntop)) == "(address_family, packed_ip, /)"
assert not hasattr(socket, "_native_inet_pton")
assert not hasattr(socket, "_native_inet_ntop")

original_parse = _socket_rs.parse_address
original_format = _socket_rs.format_address
calls = []
def parse(*args):
    calls.append(("parse", args))
    return original_parse(*args)
def format_address(*args):
    calls.append(("format", args))
    return original_format(*args)
_socket_rs.parse_address = parse
_socket_rs.format_address = format_address
try:
    for family, text in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "2001:db8::1")):
        for actual_family in (family, int(family)):
            packed = socket.inet_pton(actual_family, text)
            assert packed == _socket.inet_pton(family, text)
            assert socket.inet_ntop(actual_family, packed) == text
    assert [kind for kind, args in calls] == ["parse", "format"] * 4
    class IndexFamily:
        def __index__(self):
            return int(socket.AF_INET)
    class Text(str):
        pass
    class Packed(bytes):
        pass
    before = len(calls)
    assert socket.inet_pton(IndexFamily(), "127.0.0.1") == b"\x7f\0\0\1"
    assert socket.inet_pton(socket.AF_INET, Text("127.0.0.1")) == b"\x7f\0\0\1"
    for packed in (bytearray(b"\x7f\0\0\1"), memoryview(b"\x7f\0\0\1"), Packed(b"\x7f\0\0\1")):
        assert socket.inet_ntop(socket.AF_INET, packed) == "127.0.0.1"
    compatible = _socket.inet_pton(socket.AF_INET6, "::192.0.2.1")
    assert socket.inet_ntop(socket.AF_INET6, compatible) == _socket.inet_ntop(socket.AF_INET6, compatible)
    assert len(calls) == before
    for arguments, error in (((socket.AF_INET, "invalid"), OSError), ((socket.AF_INET, "1\0.2.3.4"), ValueError)):
        try:
            socket.inet_pton(*arguments)
        except error:
            pass
        else:
            raise AssertionError("invalid text accepted")
    for packed in (b"", b"123", b"12345"):
        try:
            socket.inet_ntop(socket.AF_INET, packed)
        except ValueError:
            pass
        else:
            raise AssertionError("wrong packed length accepted")
    # A cached callable owns the original public module even if its name
    # is replaced in the module registry.
    cached = socket.inet_pton
    sys.modules["socket"] = types.ModuleType("socket")
    try:
        assert cached(socket.AF_INET, "127.0.0.1") == b"\x7f\0\0\1"
    finally:
        sys.modules["socket"] = socket
finally:
    _socket_rs.parse_address = original_parse
    _socket_rs.format_address = original_format

# The private binder retains its module for exactly the callable lifetime.
module = types.ModuleType("bound_socket")
module.AF_INET = socket.AF_INET
module.AF_INET6 = socket.AF_INET6
module._socket_rs = None
pton, ntop = _socket._bind_address_converters(module)
reference = weakref.ref(module)
del module
gc.collect()
assert reference() is not None
assert pton(socket.AF_INET, "127.0.0.1") == b"\x7f\0\0\1"
assert ntop(socket.AF_INET, b"\x7f\0\0\1") == "127.0.0.1"
del pton, ntop
gc.collect()
assert reference() is None

# Keep the original Python call contract as an independent reference for
# positional-only keyword and missing/excess-argument diagnostics.
def inet_pton(address_family, ip_string, /):
    pass

def inet_ntop(address_family, packed_ip, /):
    pass


def error(callable, args, kwargs):
    try:
        callable(*args, **kwargs)
    except TypeError as exc:
        return str(exc)
    raise AssertionError("invalid invocation accepted")


for actual, reference, second in (
    (socket.inet_pton, inet_pton, "ip_string"),
    (socket.inet_ntop, inet_ntop, "packed_ip"),
):
    cases = [
        ((), {}), ((0,), {}), ((0, 0, 0), {}),
        ((), {"address_family": 0}), ((), {second: 0}),
        ((), {second: 0, "address_family": 0}),
        ((), {"unknown": 0}),
        ((), {"unknown": 0, "address_family": 0}),
        ((0, 0), {"address_family": 0}),
    ]
    for args, kwargs in cases:
        assert error(actual, args, kwargs) == error(reference, args, kwargs)

# Rebound constants use operator equality, including truth conversion, even
# for identical operands. Guard evaluation must precede address-type checks.
module = types.ModuleType("comparison_socket")
module.AF_INET6 = socket.AF_INET6
module._socket_rs = _socket_rs
pton, ntop = _socket._bind_address_converters(module)
trace = []
class EqualityError(Exception):
    pass

class Family:
    def __index__(self):
        return int(socket.AF_INET)

    def __eq__(self, other):
        trace.append(other is self)
        if other is self:
            raise EqualityError("operator equality called")
        return False

family = Family()
module.AF_INET = family
for function, value in ((pton, "127.0.0.1"), (ntop, b"\x7f\0\0\1")):
    trace.clear()
    try:
        function(family, value)
    except EqualityError:
        pass
    else:
        raise AssertionError("identity bypassed operator equality")
    assert trace == [True]

del module.AF_INET
for function, value in ((pton, Text("127.0.0.1")), (ntop, Packed(b"\x7f\0\0\1"))):
    try:
        function(int(socket.AF_INET), value)
    except NameError as exc:
        assert str(exc) == "name 'AF_INET' is not defined"
        assert exc.name == "AF_INET"
    else:
        raise AssertionError("address type skipped family guard")

class Truth:
    def __init__(self, value):
        self.value = value

    def __bool__(self):
        trace.append("truth")
        return self.value

class FalseFamily(Family):
    def __eq__(self, other):
        trace.append(other is self)
        return Truth(False)

family = FalseFamily()
module.AF_INET = family
trace.clear()
assert pton(family, "127.0.0.1") == b"\x7f\0\0\1"
assert trace == [True, "truth", False, "truth"]

class LateFamily(Family):
    def __eq__(self, other):
        trace.append(other is self)
        if other is self:
            return True
        raise EqualityError("second-family comparison called")

family = LateFamily()
module.AF_INET = family
trace.clear()
try:
    ntop(family, b"wrong length")
except EqualityError:
    pass
else:
    raise AssertionError("wrong length skipped second-family comparison")
assert trace == [True, False]

class Helper:
    def parse_address(self, version, text):
        assert version == 4 and text == "127.0.0.1"
        return b"rebound helper"

class RebindingFamily(Family):
    def __eq__(self, other):
        module._socket_rs = Helper()
        return other is self

family = RebindingFamily()
module.AF_INET = family
assert pton(family, "127.0.0.1") == b"rebound helper"

# The family guard itself compares type objects using tuple-membership
# semantics, so a custom metaclass may fail before value equality occurs.
class GuardMeta(type):
    def __eq__(cls, other):
        trace.append(("type", other))
        if other is int:
            raise EqualityError("metaclass comparison called")
        return super().__eq__(other)

class GuardFamily(metaclass=GuardMeta):
    def __eq__(self, other):
        raise AssertionError("value equality ran before the type guard")

family = GuardFamily()
module.AF_INET = family
module._socket_rs = _socket_rs
for function, value in ((pton, "127.0.0.1"), (ntop, b"\x7f\0\0\1")):
    trace.clear()
    try:
        function(family, value)
    except EqualityError:
        pass
    else:
        raise AssertionError("metaclass equality bypassed")
    assert trace == [("type", int)]

# A guard type result must stay owned across callbacks that replace the
# instance's class and collect its previous class before the next comparison.
class CleanupTruth:
    def __bool__(self):
        return False

    def __del__(self):
        trace.append("cleanup")
        gc.collect()

class ReplacementFamily:
    def __index__(self):
        return int(socket.AF_INET)

class ChangingMeta(type):
    def __eq__(cls, other):
        if cls.__name__ == "OriginalFamily" and other is int:
            trace.append("first")
            changing_family.__class__ = ReplacementFamily
            return CleanupTruth()
        if cls.__name__ == "ReferenceFamily":
            trace.append("second")
            assert original_type() is not None and other is original_type()
            return False
        return super().__eq__(other)

class ReferenceFamily(metaclass=ChangingMeta):
    pass

def make_changing_family():
    class OriginalFamily(metaclass=ChangingMeta):
        def __index__(self):
            return int(socket.AF_INET)
    return OriginalFamily()

module.AF_INET = ReferenceFamily()
module._socket_rs = _socket_rs
for function, value, expected in (
    (pton, "127.0.0.1", b"\x7f\0\0\1"),
    (ntop, b"\x7f\0\0\1", "127.0.0.1"),
):
    changing_family = make_changing_family()
    original_type = weakref.ref(type(changing_family))
    trace.clear()
    assert function(changing_family, value) == expected
    assert trace == ["first", "cleanup", "second"]
    assert type(changing_family) is ReplacementFamily
    gc.collect()
    assert original_type() is None

del module._socket_rs
for function, value in ((pton, "127.0.0.1"), (ntop, b"\x7f\0\0\1")):
    try:
        function(int(socket.AF_INET), value)
    except NameError as exc:
        assert str(exc) == "name '_socket_rs' is not defined"
        assert exc.name == "_socket_rs"
    else:
        raise AssertionError("missing helper global accepted")

# Native bindings resolve their explicit owning-module namespace. Artificial
# builtin globals used only by the former Python wrappers do not supply a
# missing family constant or helper.
sentinel = object()
module.AF_INET = socket.AF_INET
for name, value in (("AF_INET", socket.AF_INET), ("_socket_rs", _socket_rs)):
    saved = vars(builtins).get(name, sentinel)
    setattr(builtins, name, value)
    module.AF_INET = socket.AF_INET
    module._socket_rs = _socket_rs
    delattr(module, name)
    try:
        for function, address in ((pton, "127.0.0.1"), (ntop, b"\x7f\0\0\1")):
            try:
                function(int(socket.AF_INET), address)
            except NameError as exc:
                assert exc.name == name
            else:
                raise AssertionError("native binding used artificial builtin global")
    finally:
        if saved is sentinel:
            delattr(builtins, name)
        else:
            setattr(builtins, name, saved)
