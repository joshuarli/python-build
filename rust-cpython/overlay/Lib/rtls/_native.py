from __future__ import annotations

import ctypes
import os
import struct
import weakref

from ._immutable import ImmutableType


class _Reply(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_uint64), ("status", ctypes.c_int32), ("length", ctypes.c_size_t)]


def _load_engine():
    """Locate the lane-built Rust TLS engine.

    The fork links ``_ssl_rs`` statically when Setup.local declares it
    ``*static*`` (no ``__file__``) and installs a shared object otherwise.
    ``CDLL(None)`` resolves already-loaded process symbols for the static
    case; the shared object path is used when the build installs one.
    """
    import importlib

    module = importlib.import_module("_ssl_rs")
    path = getattr(module, "__file__", None)
    if path is not None:
        return ctypes.CDLL(path)
    return ctypes.CDLL(None)


_library = _load_engine()
_library.rtls_native_invoke.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(_Reply)]
_library.rtls_native_invoke.restype = None
_library.rtls_native_copy_reply.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
_library.rtls_native_copy_reply.restype = ctypes.c_int
_library.rtls_native_claim.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
_library.rtls_native_claim.restype = ctypes.c_int
_library.rtls_native_free.argtypes = [ctypes.c_uint64]
_library.rtls_native_free.restype = ctypes.c_int
_library.rtls_native_handle_count.argtypes = []
_library.rtls_native_handle_count.restype = ctypes.c_size_t


def _encode(value):
    if value is None:
        return b"\0"
    if value is False:
        return b"\1"
    if value is True:
        return b"\2"
    if isinstance(value, _Handle):
        value = value._handle
        if not value:
            raise RuntimeError("native TLS handle has been closed")
    if isinstance(value, int):
        return b"\3" + struct.pack("<q", value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value)
        return b"\4" + struct.pack("<I", len(value)) + value
    if isinstance(value, str):
        value = value.encode("utf-8")
        return b"\5" + struct.pack("<I", len(value)) + value
    if isinstance(value, (tuple, list)):
        return bytes([7 if isinstance(value, tuple) else 6]) + struct.pack("<I", len(value)) + b"".join(map(_encode, value))
    if isinstance(value, dict):
        return b"\10" + struct.pack("<I", len(value)) + b"".join(_encode(key) + _encode(item) for key, item in value.items())
    raise TypeError(f"unsupported native TLS argument: {type(value).__name__}")


class _ReturnedHandle:
    __slots__ = ("kind", "handle")

    def __init__(self, kind, handle):
        self.kind = kind
        self.handle = handle


def _decode(data):
    offset = 0

    def take(length):
        nonlocal offset
        end = offset + length
        if end > len(data):
            raise RuntimeError("truncated native TLS reply")
        value = data[offset:end]
        offset = end
        return value

    def value(depth=0):
        if depth > 32:
            raise RuntimeError("native TLS reply nesting exceeds limit")
        tag = take(1)[0]
        if tag == 0:
            return None
        if tag in (1, 2):
            return tag == 2
        if tag == 3:
            return struct.unpack("<q", take(8))[0]
        if tag == 9:
            return _ReturnedHandle(take(1)[0], struct.unpack("<Q", take(8))[0])
        length = struct.unpack("<I", take(4))[0]
        if tag == 4:
            return take(length)
        if tag == 5:
            return take(length).decode("utf-8")
        if tag in (6, 7):
            items = [value(depth + 1) for _ in range(length)]
            return tuple(items) if tag == 7 else items
        if tag == 8:
            return {value(depth + 1): value(depth + 1) for _ in range(length)}
        raise RuntimeError("unknown native TLS reply tag")

    result = value()
    if offset != len(data):
        raise RuntimeError("trailing native TLS reply bytes")
    return result


def _raise(status, result):
    from . import _exceptions

    if status == 2:
        code, message, verify_message = result
        raise _exceptions.SSLCertVerificationError(message, verify_code=code, verify_message=verify_message)
    if status == 3:
        raise _exceptions.SSLZeroReturnError(6, result)
    if status == 4:
        raise _exceptions.SSLEOFError(8, result)
    if status == 5:
        raise ValueError(result)
    if status == 6:
        raise NotImplementedError(result)
    if status == 9:
        code, message, filename = result
        raise OSError(code, os.strerror(code), filename)
    if status == 12:
        message, library, reason = result
        raise _exceptions.SSLError(1, message, library=library, reason=reason)
    if status == 11:
        raise MemoryError(result)
    if status in (7, 10):
        raise RuntimeError(result)
    raise _exceptions.SSLError(1, result)


def _invoke(handle, method, *arguments):
    name = method.encode("ascii")
    data = _encode(arguments)
    reply = _Reply()
    try:
        _library.rtls_native_invoke(handle, name, len(name), data, len(data), ctypes.byref(reply))
        if not reply.handle:
            raise RuntimeError("Rust TLS engine could not allocate a native reply")
        output = ctypes.create_string_buffer(reply.length)
        if _library.rtls_native_copy_reply(reply.handle, output, reply.length):
            raise RuntimeError("could not copy native TLS reply")
        result = _decode(output.raw)
        if isinstance(result, _ReturnedHandle):
            wrapper = _HANDLE_TYPES[result.kind]._from_handle(result.handle)
            if _library.rtls_native_claim(reply.handle, result.handle):
                wrapper.close()
                raise RuntimeError("could not transfer native TLS handle ownership")
            result = wrapper
    finally:
        if reply.handle:
            _library.rtls_native_free(reply.handle)
    if reply.status:
        _raise(reply.status, result)
    return result


class _Handle:
    __slots__ = ("_handle", "_finalizer", "__weakref__")

    @classmethod
    def _from_handle(cls, handle):
        try:
            self = object.__new__(cls)
            self._handle = handle
            self._finalizer = weakref.finalize(self, _library.rtls_native_free, handle)
            return self
        except BaseException:
            _library.rtls_native_free(handle)
            raise

    def close(self):
        self._finalizer()
        self._handle = 0

    def _call(self, method, *arguments):
        if not self._handle:
            raise RuntimeError("native TLS handle has been closed")
        return _invoke(self._handle, method, *arguments)


class RustlsConfigBuilder(_Handle):
    def __new__(cls):
        return _invoke(0, "new_builder")

    def clone_builder(self):
        return self._call("clone_builder")

    def snapshot_server_builder(self):
        return self._call("snapshot_server_builder")

    def build_client_connection(self, server_name, session=None, capture_message_callback=False):
        return self._call("build_client_connection", server_name, session, capture_message_callback)

    def build_server_connection(self, capture_message_callback=False):
        return self._call("build_server_connection", capture_message_callback)

    def accept_server_connection(self, acceptor, selected_context, capture_message_callback=False):
        return self._call("accept_server_connection", acceptor, selected_context, capture_message_callback)

    def set_keylog_filename(self, filename):
        try:
            return self._call("set_keylog_filename", None if filename is None else os.fsencode(filename))
        except OSError as error:
            error.filename = filename
            raise

    def set_num_tickets(self, value, server_side):
        import operator

        value = operator.index(value)
        if not -(1 << 63) <= value < (1 << 63):
            raise OverflowError("Python int too large to convert to C long")
        return self._call("set_num_tickets", value, server_side)

    def set_client_cert_chain_pem(self, cert_pem, key_pem, password=None):
        return self._call("set_client_cert_chain_pem", cert_pem, key_pem, password)

    def set_server_cert_chain_pem(self, cert_pem, key_pem, password=None):
        return self._call("set_server_cert_chain_pem", cert_pem, key_pem, password)

    def get_groups(self, include_aliases=False):
        return self._call("get_groups", include_aliases)

    @staticmethod
    def supported_sigalgs():
        return _invoke(0, "supported_sigalgs")


class RustlsServerAcceptor(_Handle):
    def __new__(cls, capture_message_callback=False):
        return _invoke(0, "new_acceptor", capture_message_callback)


class RustlsClientConnection(_Handle):
    def session(self):
        return self._call("session")

    def read_tls(self, data):
        return self._call("read_tls", memoryview(data)[:65536])

    def write_plaintext(self, data):
        return self._call("write_plaintext", memoryview(data)[:65536])

    def decrypt_incoming(self, ciphertext, max_plaintext):
        plaintext = bytearray()
        offset = 0
        while offset < len(ciphertext):
            previous_offset = offset
            previous_plaintext = len(plaintext)
            offset += self.read_tls(ciphertext[offset:])
            self.process_new_packets()
            plaintext += self.read_plaintext(max_plaintext - len(plaintext))
            if len(plaintext) >= max_plaintext:
                break
            if offset == previous_offset and len(plaintext) == previous_plaintext:
                break
        return bytes(plaintext), ciphertext[offset:]


class RustlsServerConnection(RustlsClientConnection):
    pass


class RustlsSession(_Handle, metaclass=ImmutableType):
    def __new__(cls):
        raise TypeError("SSLSession cannot be constructed directly")

    def __eq__(self, other):
        if not isinstance(other, RustlsSession):
            return NotImplemented
        return self._call("equals", other)

    __hash__ = None


_HANDLE_TYPES = {
    1: RustlsConfigBuilder, 2: RustlsClientConnection, 3: RustlsServerConnection,
    4: RustlsServerAcceptor, 5: RustlsSession,
}


for _name in ("id", "time", "timeout", "has_ticket", "ticket_lifetime_hint"):
    type.__setattr__(RustlsSession, _name, property(lambda self, name=_name: self._call(name)))


def _method(name):
    def call(self, *arguments):
        return self._call(name, *arguments)
    call.__name__ = name
    return call


for _name in (
    "add_root_certs_from_pem", "add_root_certs_from_cadata", "add_capath_directory",
    "add_root_cert_from_der", "set_alpn", "set_min_version", "set_max_version",
    "set_cipher_suites", "set_tls13_cipher_suites", "get_num_tickets", "enabled_cipher_suites", "set_groups", "set_client_sigalgs",
    "cert_chain_key_is_encrypted", "set_server_sigalgs", "set_verify_mode", "set_check_hostname", "set_sni_enabled",
    "set_ech_configs", "has_ech", "root_cert_count", "root_ca_count", "crl_count",
    "get_root_certs_der", "get_ca_certs_der", "set_verify_flags", "session_stats",
    "set_cipher_server_preference", "set_hostname_checks_common_name", "validate_server_hello",
):
    setattr(RustlsConfigBuilder, _name, _method(_name))
for _name in ("feed", "server_name", "cipher_suites", "take_alert", "set_message_callback_enabled", "take_message_events", "reject"):
    setattr(RustlsServerAcceptor, _name, _method(_name))
for _name in (
    "process_new_packets", "read_plaintext", "pending",
    "set_message_callback_enabled", "take_message_events",
    "write_tls", "send_close_notify", "is_handshaking", "set_session",
    "session_reused", "wants_read", "wants_write", "peer_certificates", "verified_certificates",
    "alpn_protocol", "protocol_version", "negotiated_cipher_suite", "negotiated_cipher_suite_bits",
    "ech_status", "tls_unique", "group", "client_sigalg", "server_sigalg",
):
    setattr(RustlsClientConnection, _name, _method(_name))


def rustls_version():
    return _invoke(0, "rustls_version")


def graviola_version():
    return _invoke(0, "graviola_version")


def crypto_provider():
    return _invoke(0, "crypto_provider")


def crypto_provider_version():
    return _invoke(0, "crypto_provider_version")


def rand_bytes(length):
    if length < 0:
        raise ValueError("num must be positive")
    chunks = []
    while length:
        count = min(length, 65536)
        chunks.append(_invoke(0, "rand_bytes", count))
        length -= count
    return b"".join(chunks)


def certificate_subject_name_der(certificate):
    return _invoke(0, "certificate_subject_name_der", certificate)


def parse_certificate_dict(certificate):
    return _invoke(0, "parse_certificate_dict", certificate)


def _load_engine_python():
    import _ssl_rs

    path = getattr(_ssl_rs, "__file__", None)
    if path is not None:
        return ctypes.PyDLL(path)
    return ctypes.PyDLL(None)


_python_library = _load_engine_python()
_python_library.rtls_native_report_unraisable.argtypes = [ctypes.py_object, ctypes.py_object]
_python_library.rtls_native_report_unraisable.restype = None


def report_callback_error(error, callback):
    _python_library.rtls_native_report_unraisable(error, callback)
