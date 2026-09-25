"""Interpret strings as packed binary data.
"""

__all__ = [
    'calcsize', 'pack', 'pack_into', 'unpack', 'unpack_from',
    'iter_unpack', 'Struct', 'error'
]

import _struct as _c_struct
from _struct import *
from _struct import _clearcache  # noqa: F401
from _struct import __doc__  # noqa: F401

_RUST_STRUCT_NOT_LOADED = object()
_rust_struct = _RUST_STRUCT_NOT_LOADED


def _get_rust_struct():
    global _rust_struct
    if _rust_struct is _RUST_STRUCT_NOT_LOADED:
        try:
            import _struct_rs
        except ImportError:
            _rust_struct = None
        else:
            _rust_struct = _struct_rs
    return _rust_struct


def pack(*args, **kwargs):
    rust_struct = _get_rust_struct()
    if rust_struct is not None and not kwargs and len(args) >= 1:
        packed = rust_struct.pack(args[0], args[1:])
        if packed is not False:
            return packed
    return _c_struct.pack(*args, **kwargs)


def unpack(*args, **kwargs):
    rust_struct = _get_rust_struct()
    if rust_struct is not None and not kwargs and len(args) == 2:
        unpacked = rust_struct.unpack(args[0], args[1])
        if unpacked is not False:
            return unpacked
    return _c_struct.unpack(*args, **kwargs)


def pack_into(*args, **kwargs):
    rust_struct = _get_rust_struct()
    if rust_struct is not None and not kwargs and len(args) >= 3:
        format, buffer, offset = args[:3]
        if type(buffer) is bytearray and type(offset) is int:
            packed = rust_struct.pack(format, args[3:])
            if packed is not False and 0 <= offset <= len(buffer) - len(packed):
                buffer[offset:offset + len(packed)] = packed
                return None
    return _c_struct.pack_into(*args, **kwargs)


def unpack_from(*args, **kwargs):
    rust_struct = _get_rust_struct()
    if rust_struct is not None and not kwargs and len(args) in (2, 3):
        format, buffer = args[:2]
        offset = args[2] if len(args) == 3 else 0
        if type(buffer) in (bytes, bytearray) and type(offset) is int:
            unpacked = rust_struct.unpack_from(format, buffer, offset)
            if unpacked is not False:
                return unpacked
    return _c_struct.unpack_from(*args, **kwargs)


pack.__doc__ = _c_struct.pack.__doc__
pack.__module__ = _c_struct.pack.__module__
unpack.__doc__ = _c_struct.unpack.__doc__
unpack.__module__ = _c_struct.unpack.__module__
pack_into.__doc__ = _c_struct.pack_into.__doc__
pack_into.__module__ = _c_struct.pack_into.__module__
unpack_from.__doc__ = _c_struct.unpack_from.__doc__
unpack_from.__module__ = _c_struct.unpack_from.__module__
