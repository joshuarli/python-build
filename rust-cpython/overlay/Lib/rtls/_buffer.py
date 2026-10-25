from __future__ import annotations

import operator
import struct
import sys


_C_INT_MAX = (1 << (struct.calcsize("@i") * 8 - 1)) - 1
_SSIZE_MIN = -sys.maxsize - 1


def _ssize_t_index(value: object) -> int:
    length = operator.index(value)
    if length < _SSIZE_MIN or length > sys.maxsize:
        raise OverflowError("Python int too large to convert to C ssize_t")
    return length


def _clamp_read_length(length: int, buffer_nbytes: int | None) -> int:
    if buffer_nbytes is None:
        if length < 0:
            raise ValueError("size should not be negative")
        return length
    if length <= 0 or length > buffer_nbytes:
        length = buffer_nbytes
        if length > _C_INT_MAX:
            raise OverflowError("maximum length can't fit in a C 'int'")
    return length
