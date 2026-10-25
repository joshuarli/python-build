from __future__ import annotations

from ._immutable import ImmutableType

import operator
import threading

_MAX_BIO_SIZE = (1 << 31) - 1


class MemoryBIO(metaclass=ImmutableType):
    """In-memory BIO that buffers bytes, compatible with ssl.MemoryBIO.

    Used by TLSObject (via wrap_bio) to replace network I/O with
    memory-based byte shuffling, exactly like asyncio's SSLProtocol does
    with ssl.MemoryBIO.
    """

    __slots__ = ("_buf", "_eof", "_lock")

    def __init__(self) -> None:
        self._buf = bytearray()
        self._eof = False
        self._lock = threading.Lock()

    def read(self, size: int = -1, /) -> bytes:
        """Read up to *size* bytes from the BIO.

        If *size* is -1 or omitted, read all available data.
        Returns b"" if no data is available (non-blocking).
        """
        size = operator.index(size)
        if not -_MAX_BIO_SIZE - 1 <= size <= _MAX_BIO_SIZE:
            raise OverflowError("Python int too large to convert to C int")
        with self._lock:
            if size < 0 or size >= len(self._buf):
                data = bytes(self._buf)
                self._buf.clear()
                return data
            data = bytes(self._buf[:size])
            del self._buf[:size]
            return data

    def write(self, data: bytes, /) -> int:
        with memoryview(data) as view:
            if not view.c_contiguous:
                raise BufferError("memoryview: underlying buffer is not C-contiguous")
            if view.nbytes > _MAX_BIO_SIZE:
                raise OverflowError(f"string longer than {_MAX_BIO_SIZE} bytes")
            with self._lock:
                if self._eof:
                    from ._exceptions import SSLError

                    raise SSLError("cannot write() after write_eof()")
                self._buf.extend(view.cast("B"))
                return view.nbytes

    def write_eof(self) -> None:
        """Signal that no more data will be written.

        After this, further write() calls will raise SSLError.
        """
        with self._lock:
            self._eof = True

    @property
    def pending(self) -> int:
        """Number of bytes currently in the buffer waiting to be read."""
        with self._lock:
            return len(self._buf)

    @property
    def eof(self) -> bool:
        """True if write_eof() was called AND all buffered data has been read."""
        with self._lock:
            return self._eof and not self._buf

    def __repr__(self) -> str:
        return f"<MemoryBIO pending={self.pending} eof_written={self._eof}>"
