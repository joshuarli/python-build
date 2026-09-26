"""Compression and decompression using zlib-compatible DEFLATE streams."""

import importlib.machinery
import importlib.util
import os
import sys


def _load_native_zlib():
    for directory in sys.path:
        if not isinstance(directory, str):
            continue
        if not directory:
            directory = os.getcwd()
        for suffix in importlib.machinery.EXTENSION_SUFFIXES:
            path = os.path.join(directory, "zlib" + suffix)
            if not os.path.isfile(path):
                continue
            loader = importlib.machinery.ExtensionFileLoader(__name__, path)
            spec = importlib.util.spec_from_file_location(
                __name__, path, loader=loader
            )
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            return module
    raise ImportError("cannot locate the native zlib extension")


def _install_rust_codecs():
    native = _load_native_zlib()
    import _zlib_rs as rust

    native_compress = native.compress
    native_decompress = native.decompress
    native_compressobj = native.compressobj
    native_decompressobj = native.decompressobj
    omitted = object()

    def rust_call(function, *args):
        try:
            return function(*args)
        except ValueError as error:
            raise native.error(str(error)) from None

    class RustCompressor:
        __slots__ = ("_level", "_wbits", "_state", "_history", "_finished")

        def __new__(cls, *args, **kwargs):
            raise TypeError(
                f"cannot create '{cls.__module__}.{cls.__name__}' instances"
            )

        def compress(self, data, /):
            result = rust_call(rust.compress, self._state, data)
            self._history.append((False, bytes(data)))
            return result

        def flush(self, mode=native.Z_FINISH, /):
            result = rust_call(rust.flush, self._state, mode)
            self._history.append((True, mode))
            if mode == native.Z_FINISH:
                self._finished = True
            return result

        def copy(self):
            if getattr(self, "_finished", False):
                raise ValueError("cannot copy a finished compression object")
            duplicate = new_compressor(self._level, self._wbits)
            for is_flush, value in self._history:
                if is_flush:
                    rust_call(rust.flush, duplicate._state, value)
                    duplicate._history.append((True, value))
                else:
                    rust_call(rust.compress, duplicate._state, value)
                    duplicate._history.append((False, value))
            return duplicate

        def __copy__(self):
            return self.copy()

        def __deepcopy__(self, memo):
            return self.copy()

    class RustDecompressor:
        __slots__ = ("_wbits", "_state", "_history", "_flushed")

        def __new__(cls, *args, **kwargs):
            raise TypeError(
                f"cannot create '{cls.__module__}.{cls.__name__}' instances"
            )

        @property
        def eof(self):
            return rust.eof(self._state)

        @property
        def unused_data(self):
            return rust.unused_data(self._state)

        @property
        def unconsumed_tail(self):
            return rust.unconsumed_tail(self._state)

        def decompress(self, data, /, max_length=0):
            if self._flushed:
                raise native.error("Error -2 while decompressing data: inconsistent stream state")
            import operator

            max_length = operator.index(max_length)
            if max_length > sys.maxsize or max_length < -sys.maxsize - 1:
                raise OverflowError("Python int too large to convert to C ssize_t")
            if max_length < 0:
                raise ValueError("max_length must be non-negative")
            tail = rust.unconsumed_tail(self._state)
            if tail:
                input_data = memoryview(data).tobytes()
                if input_data.startswith(tail):
                    input_data = input_data[len(tail):]
            else:
                input_data = data
            result = rust_call(rust.decompress, self._state, input_data,
                               max_length)
            self._history.append((memoryview(data).tobytes(), max_length))
            return result

        def flush(self, length=native.DEF_BUF_SIZE, /):
            import operator

            length = operator.index(length)
            if length > sys.maxsize or length < -sys.maxsize - 1:
                raise OverflowError("Python int too large to convert to C ssize_t")
            if length < 1:
                raise ValueError("length must be greater than zero")
            if self._flushed:
                raise native.error("Error -2 while flushing: inconsistent stream state")
            result = rust_call(rust.decompressor_flush, self._state, length)
            self._history.append((None, length))
            self._flushed = rust.eof(self._state)
            return result

        def copy(self):
            if self._flushed:
                raise ValueError("cannot copy a flushed decompression object")
            duplicate = new_decompressor(self._wbits)
            for data, max_length in self._history:
                if data is None:
                    duplicate.flush(max_length)
                else:
                    duplicate.decompress(data, max_length)
            return duplicate

        def __copy__(self):
            return self.copy()

        def __deepcopy__(self, memo):
            return self.copy()

    RustCompressor.__name__ = "Compress"
    RustCompressor.__qualname__ = "Compress"
    RustCompressor.__module__ = __name__
    RustDecompressor.__name__ = "Decompress"
    RustDecompressor.__qualname__ = "Decompress"
    RustDecompressor.__module__ = __name__

    def new_compressor(level, wbits):
        compressor = object.__new__(RustCompressor)
        compressor._level = level
        compressor._wbits = wbits
        compressor._state = rust_call(rust.compressor, level, wbits)
        compressor._history = []
        return compressor

    def new_decompressor(wbits):
        decompressor = object.__new__(RustDecompressor)
        decompressor._wbits = wbits
        decompressor._state = rust_call(rust.decompressor, wbits)
        decompressor._history = []
        decompressor._flushed = False
        return decompressor

    def compress(data, /, level=-1, wbits=native.MAX_WBITS):
        if (isinstance(level, int) and -1 <= level <= 9
                and isinstance(wbits, int)
                and wbits in (native.MAX_WBITS, -native.MAX_WBITS)):
            return rust_call(rust.compress_once, data, level, wbits)
        return native_compress(data, level, wbits)

    def decompress(data, /, wbits=native.MAX_WBITS,
                   bufsize=native.DEF_BUF_SIZE):
        if (isinstance(wbits, int)
                and wbits in (native.MAX_WBITS, -native.MAX_WBITS)
                and isinstance(bufsize, int)
                and -sys.maxsize - 1 <= bufsize <= sys.maxsize):
            try:
                return rust.decompress_once(data, wbits)
            except ValueError as error:
                message = str(error)
                if message == "incomplete or invalid DEFLATE stream":
                    message = "Error -5 while decompressing data: incomplete or truncated stream"
                raise native.error(message) from None
        return native_decompress(data, wbits, bufsize)

    def compressobj(level=-1, method=native.DEFLATED,
                    wbits=native.MAX_WBITS, memLevel=native.DEF_MEM_LEVEL,
                    strategy=native.Z_DEFAULT_STRATEGY, zdict=omitted):
        if (isinstance(level, int) and -1 <= level <= 9
                and isinstance(method, int)
                and method == native.DEFLATED
                and isinstance(wbits, int)
                and wbits in (native.MAX_WBITS, -native.MAX_WBITS)
                and isinstance(memLevel, int)
                and memLevel == native.DEF_MEM_LEVEL
                and isinstance(strategy, int)
                and strategy == native.Z_DEFAULT_STRATEGY
                and zdict is omitted):
            return new_compressor(level, wbits)
        if zdict is omitted:
            return native_compressobj(level, method, wbits, memLevel, strategy)
        return native_compressobj(level, method, wbits, memLevel, strategy,
                                  zdict)

    def decompressobj(wbits=native.MAX_WBITS, zdict=omitted):
        if (isinstance(wbits, int)
                and wbits in (native.MAX_WBITS, -native.MAX_WBITS)
                and zdict is omitted):
            return new_decompressor(wbits)
        if zdict is omitted:
            return native_decompressobj(wbits)
        return native_decompressobj(wbits, zdict)

    compress.__doc__ = native_compress.__doc__
    decompress.__doc__ = native_decompress.__doc__
    compressobj.__doc__ = native_compressobj.__doc__
    decompressobj.__doc__ = native_decompressobj.__doc__
    native.compress = compress
    native.decompress = decompress
    native.compressobj = compressobj
    native.decompressobj = decompressobj
    sys.modules[__name__] = native


_install_rust_codecs()
del _install_rust_codecs
del _load_native_zlib
