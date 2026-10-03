"""Legacy facade snapshot used only to check held functions during source upgrades."""

def _rust_pickle_protocol(protocol):
    return (protocol is None or
            (type(protocol) is int and protocol in (-1, 3, 4, 5)))


def _rust_pickle_load_options(fix_imports, encoding, errors, buffers):
    return (type(fix_imports) is bool and type(encoding) is str and
            encoding == "ASCII" and type(errors) is str and
            errors == "strict" and buffers is None)


def dump(obj, file, protocol=None, *, fix_imports=True, buffer_callback=None):
    if (_pickle_rs is not None and type(file) is io.BytesIO and
            buffer_callback is None and
            (fix_imports is True or fix_imports is False) and
            _rust_pickle_protocol(protocol)):
        encoded = _pickle_rs.dumps(obj, protocol)
        if encoded is not None:
            file.write(encoded)
            return None
    return _cpython_dump(
        obj, file, protocol, fix_imports=fix_imports,
        buffer_callback=buffer_callback)


def dumps(obj, protocol=None, *, fix_imports=True, buffer_callback=None):
    if (_pickle_rs is not None and buffer_callback is None and
            (fix_imports is True or fix_imports is False) and
            _rust_pickle_protocol(protocol)):
        encoded = _pickle_rs.dumps(obj, protocol)
        if encoded is not None:
            return encoded
    return _cpython_dumps(
        obj, protocol, fix_imports=fix_imports,
        buffer_callback=buffer_callback)


def _rust_loads(data):
    if _pickle_rs is None or type(data) is not bytes:
        return False, None, 0
    return _pickle_rs.loads(data)


def load(file, *, fix_imports=True, encoding="ASCII", errors="strict",
         buffers=None):
    if (_pickle_rs is not None and type(file) is io.BytesIO and
            _rust_pickle_load_options(fix_imports, encoding, errors, buffers)):
        position = file.tell()
        data = file.getvalue()
        if position <= len(data):
            supported, value, consumed = _rust_loads(data[position:])
            if supported:
                file.seek(position + consumed)
                return value
    return _cpython_load(
        file, fix_imports=fix_imports, encoding=encoding, errors=errors,
        buffers=buffers)


def loads(s, /, *, fix_imports=True, encoding="ASCII", errors="strict",
          buffers=None):
    if _rust_pickle_load_options(fix_imports, encoding, errors, buffers):
        supported, value, _consumed = _rust_loads(s)
        if supported:
            return value
    return _cpython_loads(
        s, fix_imports=fix_imports, encoding=encoding, errors=errors,
        buffers=buffers)


for _rust_wrapper, _cpython_function in (
        (dump, _cpython_dump), (dumps, _cpython_dumps),
        (load, _cpython_load), (loads, _cpython_loads)):
    _rust_wrapper.__doc__ = _cpython_function.__doc__
    _rust_wrapper.__module__ = _cpython_function.__module__
del _rust_wrapper, _cpython_function

