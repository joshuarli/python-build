"""Check compact private codec globals, loader lifetime, and held behavior."""

import copy
import gc
import importlib
import importlib.util
from pathlib import Path
import sys
import weakref
import zlib
import _zlib_rs
from unittest import mock


def check_namespace(module):
    namespace = module.compress.__globals__
    assert namespace is not module.__dict__
    assert set(namespace) == {"__name__", "sys"}, set(namespace)
    assert namespace["__name__"] == "zlib"
    assert namespace["sys"] is sys
    for name in ("compress", "decompress", "compressobj", "decompressobj"):
        assert getattr(module, name).__globals__ is namespace, name
    for cls in (type(module.compressobj()), type(module.decompressobj())):
        for name, member in vars(cls).items():
            if isinstance(member, property):
                member = member.fget
            elif isinstance(member, staticmethod):
                member = member.__func__
            if hasattr(member, "__globals__"):
                assert member.__globals__ is namespace, (cls, name)


check_namespace(zlib)
payload = b"prefix: payload record\n" * 400
held_compress = zlib.compress
held_decompress = zlib.decompress
held_error = zlib.error
held_globals = held_compress.__globals__
compressor = zlib.compressobj()
prefix = compressor.compress(payload[:100])
clones = (copy.copy(compressor), copy.deepcopy(compressor))
encoded = held_compress(payload)
decompressor = zlib.decompressobj()
decoded_prefix = decompressor.decompress(encoded[:9])
decoder_clones = (copy.copy(decompressor), copy.deepcopy(decompressor))

# A fresh source execution must release its loader module while publishing
# private globals. Held functions and streams keep their own codec owners.
source = Path(__file__).resolve().parents[3] / "Lib/zlib.py"
events = []
def observe(event, args):
    if event == "function.__new__" and args[0].co_name == "_install_rust_codecs":
        events.append(args[0].co_name)
sys.addaudithook(observe)
spec = importlib.util.spec_from_file_location("zlib", source)
loader_module = importlib.util.module_from_spec(spec)
loader_reference = weakref.ref(loader_module)
class NamespaceMarker:
    pass
marker = NamespaceMarker()
namespace_reference = weakref.ref(marker)
loader_module.__dict__["_namespace_marker"] = marker
del marker
previous = sys.modules["zlib"]
try:
    sys.modules["zlib"] = loader_module
    spec.loader.exec_module(loader_module)
    fresh = sys.modules["zlib"]
    assert fresh is not loader_module
    check_namespace(fresh)
    del loader_module
    gc.collect()
    assert loader_reference() is None
    assert namespace_reference() is None
    assert events == ["_install_rust_codecs"], events
    assert held_compress.__globals__ is held_globals
    assert fresh.compress.__globals__ is not held_globals
    missing = object()
    shadowed = {
        name: vars(fresh).get(name, missing)
        for name in ("object", "isinstance", "int", "str", "ValueError", "TypeError", "sys")
    }
    for name in shadowed:
        setattr(fresh, name, object())
    try:
        type(fresh.compressobj())()
    except TypeError:
        pass
    else:
        raise AssertionError("public TypeError shadow must not change stream construction errors")
    for level in (0, 1, 6, 9):
        for wbits in (-15, 15):
            assert fresh.compress(payload, level, wbits) == held_compress(payload, level, wbits)
            assert fresh.decompress(held_compress(payload, level, wbits), wbits) == payload
    for stream in (compressor, *clones):
        packed = prefix + stream.compress(payload[100:]) + stream.flush()
        assert held_decompress(packed) == payload
    try:
        held_decompress(b"invalid")
    except held_error:
        pass
    else:
        raise AssertionError("held codec must retain its original error class")
    class FacadeError(Exception):
        pass
    original_error = fresh.error
    try:
        fresh.error = FacadeError
        try:
            fresh.decompress(b"invalid")
        except FacadeError:
            pass
        else:
            raise AssertionError("Rust errors must retain dynamic public error lookup")
    finally:
        fresh.error = original_error
    dictionary = b"prefix: payload record"
    fallback = fresh.compressobj(zdict=dictionary)
    packed = fallback.compress(payload) + fallback.flush()
    decoder = fresh.decompressobj(zdict=dictionary)
    assert decoder.decompress(packed) + decoder.flush() == payload
    assert fresh.adler32(b"abc") == 0x024D0127
    assert fresh.crc32(b"abc") == 0x352441C2
    assert fresh.adler32.__self__ is fresh
    # Reload executes the facade loader in the existing public dictionary.
    # Restore the shadows after checking already-installed codec isolation.
    for name, original in shadowed.items():
        if original is missing:
            delattr(fresh, name)
        else:
            setattr(fresh, name, original)
    held_fresh = fresh.compress
    fresh_globals = held_fresh.__globals__
    reloaded = importlib.reload(fresh)
    assert events == ["_install_rust_codecs", "_install_rust_codecs"], events
    check_namespace(reloaded)
    assert held_fresh.__globals__ is fresh_globals
    assert set(fresh_globals) == {"__name__", "sys"}
    assert held_fresh(payload) == reloaded.compress(payload)
    for stream in (decompressor, *decoder_clones):
        assert decoded_prefix + stream.decompress(encoded[9:]) + stream.flush() == payload
        assert stream.eof
        assert stream.unused_data == stream.unconsumed_tail == b""
    class SmallerSystem:
        maxsize = 0
    packed = held_compress(payload)
    original_system = held_globals["sys"]
    try:
        held_globals["sys"] = SmallerSystem()
        with mock.patch.object(_zlib_rs, "decompress_once", wraps=_zlib_rs.decompress_once) as rust_call:
            assert held_decompress(packed, bufsize=1) == payload
            assert rust_call.call_count == 0
            assert reloaded.decompress(packed, bufsize=1) == payload
            assert rust_call.call_count == 1
    finally:
        held_globals["sys"] = original_system
finally:
    sys.modules["zlib"] = previous

print("private globals, collected namespace, reload, constructor audit, held clones/errors and native fallback passed")
