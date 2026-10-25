from __future__ import annotations

from ._immutable import ImmutableType

import operator
import os
import socket
import sys
import threading
import warnings
from typing import Any, Callable

from ._bio import MemoryBIO
from ._ciphers import (
    get_cipher_descriptions,
    parse_cipher_string,
    parse_tls13_cipher_suites,
)
from ._constants import (
    _ASN1ObjectBase,
    _HAS_ECH,
    CERT_NONE,
    CERT_OPTIONAL,
    CERT_REQUIRED,
    DEFAULT_OPTIONS,
    OP_CIPHER_SERVER_PREFERENCE,
    OP_NO_SSLv3,
    OP_NO_TLSv1,
    OP_NO_TLSv1_1,
    OP_NO_TLSv1_2,
    OP_NO_TLSv1_3,
    PROTOCOL_TLS,
    PROTOCOL_TLS_CLIENT,
    PROTOCOL_TLS_SERVER,
    PROTOCOL_TLSv1,
    PROTOCOL_TLSv1_1,
    PROTOCOL_TLSv1_2,
    Options,
    Purpose,
    TLSVersion,
    VERIFY_X509_TRUSTED_FIRST,
    VerifyMode,
)
from ._exceptions import SSLError
from ._stdlib import ssl as _stdlib_ssl

def _encode_server_hostname(server_hostname: str | bytes | None) -> str | None:
    if server_hostname is None:
        return None
    if isinstance(server_hostname, str):
        encoded = server_hostname.encode("idna").decode("ascii")
    else:
        encoded = server_hostname.decode("ascii")
    if "\0" in encoded:
        raise TypeError(
            "argument must be encoded string without null bytes, not str"
        )
    return encoded


_VERSION_OPTION_CHANGES = (
    OP_NO_SSLv3 | OP_NO_TLSv1 | OP_NO_TLSv1_1 | OP_NO_TLSv1_2 | OP_NO_TLSv1_3
)
_PROTOCOL_OPTION_VERSIONS = (
    (TLSVersion.TLSv1_2, OP_NO_TLSv1_2),
    (TLSVersion.TLSv1_3, OP_NO_TLSv1_3),
)

_ECDH_CURVE_GROUPS = {
    "prime256v1": "secp256r1",
    "secp384r1": "secp384r1",
    "X25519": "x25519",
}

_SUPPORTED_OPTION_CHANGES = int(
    OP_CIPHER_SERVER_PREFERENCE | _VERSION_OPTION_CHANGES
)
_PROTOCOL_NAMES = {
    int(PROTOCOL_TLS): "PROTOCOL_TLS",
    int(PROTOCOL_TLS_CLIENT): "PROTOCOL_TLS_CLIENT",
    int(PROTOCOL_TLS_SERVER): "PROTOCOL_TLS_SERVER",
    int(PROTOCOL_TLSv1): "PROTOCOL_TLSv1",
    int(PROTOCOL_TLSv1_1): "PROTOCOL_TLSv1_1",
    int(PROTOCOL_TLSv1_2): "PROTOCOL_TLSv1_2",
}
_MAX_OPTION_VALUE = (1 << 64) - 1
_HOSTFLAG_NO_PARTIAL_WILDCARDS = 0x04
_HOSTFLAG_NEVER_CHECK_SUBJECT = 0x20


class TLSContext(_stdlib_ssl.SSLContext, metaclass=ImmutableType):
    """TLS context backed by rustls, subclassing ssl.SSLContext for asyncio.

    Usage::

        ctx = TLSContext(PROTOCOL_TLS_CLIENT)
        ctx.load_default_certs()
        ssock = ctx.wrap_socket(sock, server_hostname="example.com")
    """

    # We need __new__ because ssl.SSLContext.__new__ takes a protocol argument
    # and does C-level initialization we want to coexist with.
    def __new__(
        cls, protocol: int = PROTOCOL_TLS, *args: Any, **kwargs: Any
    ) -> TLSContext:
        stdlib_protocol = _stdlib_ssl.PROTOCOL_TLS_CLIENT
        return super().__new__(cls, stdlib_protocol)

    def __init__(self, protocol: int = PROTOCOL_TLS, *args: Any, **kwargs: Any) -> None:
        protocol = operator.index(protocol)
        if protocol not in _PROTOCOL_NAMES:
            raise ValueError(f"invalid protocol version {protocol}")
        protocol = type(PROTOCOL_TLS)(protocol)
        if protocol in (
            PROTOCOL_TLS,
            PROTOCOL_TLSv1,
            PROTOCOL_TLSv1_1,
            PROTOCOL_TLSv1_2,
        ):
            warnings.warn(
                f"ssl.{_PROTOCOL_NAMES[protocol]} is deprecated",
                DeprecationWarning,
                stacklevel=2,
            )
        if protocol in (PROTOCOL_TLSv1, PROTOCOL_TLSv1_1):
            raise NotImplementedError("TLS 1.0 and TLS 1.1 are unavailable in RTLS")

        self._protocol = protocol

        from . import _rustls

        self._builder = _rustls.RustlsConfigBuilder()
        self._builder_lock = threading.RLock()

        self._verify_mode = CERT_NONE
        self._check_hostname = False
        self._options = DEFAULT_OPTIONS
        self._minimum_version = TLSVersion.MINIMUM_SUPPORTED
        self._maximum_version = TLSVersion.MAXIMUM_SUPPORTED
        self._alpn_protocols: list[bytes] = []
        self._ciphers_string: str | None = None
        self._sni_callback: Callable | None = None
        self._message_callback: Callable | None = None
        self._keylog_filename: Any = None
        self._verify_flags = int(VERIFY_X509_TRUSTED_FIRST)
        self._builder.set_verify_flags(self._verify_flags)
        self._builder.set_cipher_server_preference(True)
        self._hostname_checks_common_name = True
        self._builder.set_hostname_checks_common_name(True)

        self._cert_chain_loaded = False
        self._ca_certs_loaded = False

        if protocol == PROTOCOL_TLS_CLIENT:
            self._verify_mode = CERT_REQUIRED
            self._check_hostname = True
            self._builder.set_verify_mode(CERT_REQUIRED)
            self._builder.set_check_hostname(True)
        elif protocol == PROTOCOL_TLS_SERVER:
            self._verify_mode = CERT_NONE
            self._check_hostname = False

        if protocol == PROTOCOL_TLSv1_2:
            self._minimum_version = TLSVersion.TLSv1_2
            self._maximum_version = TLSVersion.TLSv1_2
            self._builder.set_min_version(int(TLSVersion.TLSv1_2))
            self._builder.set_max_version(int(TLSVersion.TLSv1_2))

    def _get_builder(self) -> Any:
        """Return the RustlsConfigBuilder (used by TLSObject/TLSSocket)."""
        return self._builder

    def wrap_socket(  # type: ignore[override]
        self,
        sock: socket.socket,
        server_side: bool = False,
        do_handshake_on_connect: bool = True,
        suppress_ragged_eofs: bool = True,
        server_hostname: str | None = None,
        session: Any = None,
    ) -> Any:
        """Wrap a socket with TLS, returning an TLSSocket."""
        from ._socket import TLSStreamSocket
        from ._object import _validate_server_hostname

        if (
            isinstance(sock, socket.socket)
            and sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            != socket.SOCK_STREAM
        ):
            raise NotImplementedError("only stream sockets are supported")
        _validate_server_hostname(server_side, server_hostname)

        if not server_side and self._check_hostname and not server_hostname:
            raise ValueError("check_hostname requires server_hostname")

        socket_type = (
            TLSStreamSocket
            if sys.platform == "wasi" or not isinstance(sock, socket.socket)
            else self.sslsocket_class
        )
        return socket_type(
            sock=sock,
            context=self,
            server_side=server_side,
            server_hostname=server_hostname,
            do_handshake_on_connect=do_handshake_on_connect,
            suppress_ragged_eofs=suppress_ragged_eofs,
            session=session,
        )

    def wrap_bio(  # type: ignore[override]
        self,
        incoming: MemoryBIO,
        outgoing: MemoryBIO,
        server_side: bool = False,
        server_hostname: str | None = None,
        session: Any = None,
    ) -> Any:
        """Wrap a pair of MemoryBIOs with TLS, returning an TLSObject.

        This is the method asyncio's SSLProtocol calls to create a sans-I/O
        TLS state machine.
        """
        from ._object import TLSObject, _validate_server_hostname

        _validate_server_hostname(server_side, server_hostname)
        if not server_side and self._check_hostname and not server_hostname:
            raise ValueError("check_hostname requires server_hostname")

        return self.sslobject_class(
            context=self,
            incoming=incoming,
            outgoing=outgoing,
            server_side=server_side,
            server_hostname=_encode_server_hostname(server_hostname),
            session=session,
        )

    def load_cert_chain(  # type: ignore[override]
        self,
        certfile: str | bytes | os.PathLike,
        keyfile: str | bytes | os.PathLike | None = None,
        password: str | bytes | Callable | None = None,
    ) -> None:
        """Load PEM certificate and private key files for client/server authentication."""
        cert_pem = self._read_pem_file(certfile)
        key_pem = self._read_pem_file(keyfile) if keyfile is not None else cert_pem

        password_callback = password if callable(password) else None
        pw_bytes: bytes | None = None
        if password is not None and password_callback is None:
            if isinstance(password, str):
                pw_bytes = password.encode("utf-8")
            elif isinstance(password, (bytes, bytearray)):
                pw_bytes = bytes(password)
            else:
                raise TypeError("password should be a string or callable")

        encrypted_key = False
        if password_callback is not None or pw_bytes is not None:
            encrypted_key = self._builder.cert_chain_key_is_encrypted(
                cert_pem, key_pem
            )
        if encrypted_key and password_callback is not None:
            password_value = password_callback()
            if isinstance(password_value, str):
                pw_bytes = password_value.encode("utf-8")
            elif isinstance(password_value, (bytes, bytearray)):
                pw_bytes = bytes(password_value)
            else:
                raise TypeError("password callback must return a string")
        if encrypted_key and pw_bytes is not None and len(pw_bytes) > 1024:
            raise ValueError("password cannot be longer than 1024 bytes")

        with self._builder_lock:
            staged = self._builder.clone_builder()
            staged.set_server_cert_chain_pem(cert_pem, key_pem, pw_bytes)
            staged.set_client_cert_chain_pem(cert_pem, key_pem, pw_bytes)
            self._builder = staged

        self._cert_chain_loaded = True

    def load_dh_params(self, dhfile: Any) -> None:
        raise NotImplementedError("Finite-field DH is outside the modern TLS policy")

    def load_verify_locations(  # type: ignore[override]
        self,
        cafile: str | None = None,
        capath: str | bytes | None = None,
        cadata: str | bytes | None = None,
    ) -> None:
        """Load CA certificates for verification."""
        if cafile is None and capath is None and cadata is None:
            raise TypeError("cafile, capath and cadata cannot all be None")

        with self._builder_lock:
            staged = self._builder.clone_builder()

            if cafile is not None:
                with open(cafile, "rb") as f:
                    staged.add_root_certs_from_pem(f.read())

            if capath is not None:
                directories = os.fsdecode(capath)
                if not directories:
                    raise SSLError(
                        113,
                        "[X509: INVALID_DIRECTORY] invalid directory",
                        library="X509",
                        reason="INVALID_DIRECTORY",
                    )
                for directory in directories.split(os.pathsep):
                    if not directory:
                        continue
                    if "\0" in directory:
                        raise ValueError("embedded null byte")
                    staged.add_capath_directory(os.fsencode(directory))

            if cadata is not None:
                if isinstance(cadata, str):
                    pem_data = cadata.encode("ascii")
                    try:
                        staged.add_root_certs_from_cadata(pem_data)
                    except SSLError:
                        if b"-----BEGIN CERTIFICATE-----" not in pem_data:
                            raise SSLError(
                                0,
                                "no start line: cadata does not contain a certificate",
                            ) from None
                        raise
                elif b"-----BEGIN" in cadata:
                    staged.add_root_certs_from_cadata(cadata)
                else:
                    staged.add_root_cert_from_der(cadata)

            self._builder = staged
            self._ca_certs_loaded = True

    def set_default_verify_paths(self) -> None:
        from ._utils import get_default_verify_paths

        paths = get_default_verify_paths()
        capath = paths.capath
        if "SSL_CERT_DIR" in os.environ:
            capath = os.environ["SSL_CERT_DIR"] or None
        if paths.cafile is not None or capath is not None:
            self.load_verify_locations(cafile=paths.cafile, capath=capath)

    def load_default_certs(self, purpose: Any = Purpose.SERVER_AUTH) -> None:
        """Load the configured default certificate paths."""
        if not isinstance(purpose, _ASN1ObjectBase):
            raise TypeError(purpose)
        self.set_default_verify_paths()

    def set_ciphers(self, ciphers: str) -> None:
        iana_names = parse_cipher_string(ciphers)
        self._builder.set_cipher_suites(iana_names)
        self._ciphers_string = ciphers

    def set_ciphersuites(self, ciphersuites: str, /) -> None:
        """Set the TLS 1.3 cipher suite preference list."""
        if not isinstance(ciphersuites, str):
            argument_type = (
                "None" if ciphersuites is None else type(ciphersuites).__name__
            )
            raise TypeError(
                "set_ciphersuites() argument must be str, not "
                f"{argument_type}"
            )
        if "\0" in ciphersuites:
            raise ValueError("embedded null character")
        suites = parse_tls13_cipher_suites(ciphersuites)
        self._builder.set_tls13_cipher_suites(suites)

    def set_groups(self, groups: str) -> None:
        self._builder.set_groups(groups)

    def get_groups(self, *, include_aliases: bool = False) -> list[str]:
        return self._builder.get_groups(include_aliases)

    def set_ecdh_curve(self, name: Any, /) -> None:
        curve_name = os.fsdecode(name)
        try:
            group = _ECDH_CURVE_GROUPS[curve_name]
        except KeyError:
            raise ValueError(f"unknown elliptic curve name {name!r}") from None
        self._builder.set_groups(group)

    def set_client_sigalgs(self, sigalgs: str) -> None:
        self._builder.set_client_sigalgs(sigalgs)

    def set_server_sigalgs(self, sigalgs: str) -> None:
        self._builder.set_server_sigalgs(sigalgs)

    def get_ciphers(self) -> list[dict[str, object]]:  # type: ignore[override]
        """Return the list of enabled ciphers."""
        return get_cipher_descriptions(self._builder.enabled_cipher_suites())

    def set_alpn_protocols(self, protocols: list[str]) -> None:  # type: ignore[override]
        """Set ALPN protocols for negotiation."""
        self._alpn_protocols = [p.encode("ascii") for p in protocols]
        self._builder.set_alpn(self._alpn_protocols)

    def get_alpn_protocols(self) -> list[str]:
        """Return the configured ALPN protocols."""
        return [p.decode("ascii") for p in self._alpn_protocols]

    @property
    def protocol(self) -> int:  # type: ignore[override]
        return self._protocol

    @property  # type: ignore[override]
    def verify_mode(self) -> VerifyMode:
        return VerifyMode(self._verify_mode)

    @verify_mode.setter
    def verify_mode(self, value: int) -> None:
        verify_mode = operator.index(value)
        if verify_mode not in (CERT_NONE, CERT_OPTIONAL, CERT_REQUIRED):
            raise ValueError("invalid value for verify_mode")
        if verify_mode == CERT_NONE and self._check_hostname:
            raise ValueError(
                "Cannot set verify_mode to CERT_NONE when check_hostname is enabled."
            )
        self._builder.set_verify_mode(verify_mode)
        self._verify_mode = verify_mode

    @property
    def check_hostname(self) -> bool:
        return self._check_hostname

    @check_hostname.setter
    def check_hostname(self, value: bool) -> None:
        check_hostname = bool(value)
        verify_mode = self._verify_mode
        with self._builder_lock:
            staged = self._builder.clone_builder()
            if check_hostname and verify_mode == CERT_NONE:
                verify_mode = CERT_REQUIRED
                staged.set_verify_mode(verify_mode)
            staged.set_check_hostname(check_hostname)
            self._builder = staged
            self._verify_mode = verify_mode
            self._check_hostname = check_hostname

    @property  # type: ignore[override]
    def options(self) -> Options:
        return Options(self._options)

    @options.setter
    def options(self, value: int) -> None:
        option_value = operator.index(value)
        if option_value < 0:
            raise ValueError("Cannot convert negative int")
        if option_value > _MAX_OPTION_VALUE:
            raise OverflowError("Python int too large for C unsigned long long")

        changed = int(self._options) ^ option_value
        unsupported = changed & ~_SUPPORTED_OPTION_CHANGES
        if unsupported:
            raise NotImplementedError(
                f"RTLS cannot apply SSL option changes 0x{unsupported:x}"
            )
        if changed & int(_VERSION_OPTION_CHANGES):
            warnings.warn(
                "ssl.OP_NO_SSL*/ssl.OP_NO_TLS* options are deprecated",
                DeprecationWarning,
                stacklevel=2,
            )
        self._set_protocol_policy(
            self._minimum_version,
            self._maximum_version,
            Options(option_value),
        )

    @property  # type: ignore[override]
    def minimum_version(self) -> TLSVersion:
        return self._minimum_version

    @minimum_version.setter
    def minimum_version(self, value: TLSVersion | int) -> None:
        version = self._coerce_tls_version(value)
        if version == TLSVersion.MAXIMUM_SUPPORTED:
            version = TLSVersion.TLSv1_3
        self._set_protocol_policy(version, self._maximum_version, self._options)

    @property  # type: ignore[override]
    def maximum_version(self) -> TLSVersion:
        return self._maximum_version

    @maximum_version.setter
    def maximum_version(self, value: TLSVersion | int) -> None:
        version = self._coerce_tls_version(value)
        if version == TLSVersion.MINIMUM_SUPPORTED:
            version = TLSVersion.TLSv1
        self._set_protocol_policy(self._minimum_version, version, self._options)

    @staticmethod
    def _coerce_tls_version(value: TLSVersion | int) -> TLSVersion:
        version = operator.index(value)
        try:
            return TLSVersion(version)
        except ValueError:
            raise ValueError(f"Unsupported TLS/SSL version 0x{version:x}") from None

    @staticmethod
    def _effective_protocol_bounds(
        minimum: TLSVersion, maximum: TLSVersion, options: Options
    ) -> tuple[int, int]:
        minimum_value = (
            int(TLSVersion.TLSv1_2)
            if minimum == TLSVersion.MINIMUM_SUPPORTED
            else int(minimum)
        )
        maximum_value = (
            int(TLSVersion.TLSv1_3)
            if maximum == TLSVersion.MAXIMUM_SUPPORTED
            else int(maximum)
        )
        allowed_versions = tuple(
            int(version)
            for version, option in _PROTOCOL_OPTION_VERSIONS
            if minimum_value <= int(version) <= maximum_value
            and not options & option
        )
        if not allowed_versions:
            return int(TLSVersion.TLSv1_3), int(TLSVersion.TLSv1_2)
        return allowed_versions[0], allowed_versions[-1]

    def _set_protocol_policy(
        self, minimum: TLSVersion, maximum: TLSVersion, options: Options
    ) -> None:
        minimum_value, maximum_value = self._effective_protocol_bounds(
            minimum, maximum, options
        )
        if (
            minimum == self._minimum_version
            and maximum == self._maximum_version
            and options == self._options
        ):
            return
        with self._builder_lock:
            staged = self._builder.clone_builder()
            staged.set_min_version(minimum_value)
            staged.set_max_version(maximum_value)
            staged.set_cipher_server_preference(
                bool(options & OP_CIPHER_SERVER_PREFERENCE)
            )
            self._builder = staged
            self._minimum_version = minimum
            self._maximum_version = maximum
            self._options = options

    @property
    def post_handshake_auth(self) -> None:
        return None

    @post_handshake_auth.setter
    def post_handshake_auth(self, value: bool) -> None:
        raise NotImplementedError("RTLS does not support post-handshake authentication")

    @property
    def keylog_filename(self) -> Any:
        return self._keylog_filename

    @keylog_filename.setter
    def keylog_filename(self, value: Any) -> None:
        with self._builder_lock:
            self._builder.set_keylog_filename(value)
            self._keylog_filename = value

    @keylog_filename.deleter
    def keylog_filename(self) -> None:
        raise AttributeError(
            f"attribute 'keylog_filename' of '{type(self).__name__}' "
            "objects cannot be deleted"
        )

    @property
    def _host_flags(self) -> int:
        flags = _HOSTFLAG_NO_PARTIAL_WILDCARDS
        if not self._hostname_checks_common_name:
            flags |= _HOSTFLAG_NEVER_CHECK_SUBJECT
        return flags

    @_host_flags.setter
    def _host_flags(self, value: int) -> None:
        flags = operator.index(value)
        if not 0 <= flags <= 0xFFFFFFFF:
            raise OverflowError("unsigned int is greater than maximum")
        unsupported = flags & ~(
            _HOSTFLAG_NO_PARTIAL_WILDCARDS | _HOSTFLAG_NEVER_CHECK_SUBJECT
        )
        if unsupported or not flags & _HOSTFLAG_NO_PARTIAL_WILDCARDS:
            raise NotImplementedError(
                "RTLS requires no-partial-wildcard hostname checking"
            )
        self.hostname_checks_common_name = not bool(
            flags & _HOSTFLAG_NEVER_CHECK_SUBJECT
        )

    @property
    def hostname_checks_common_name(self) -> bool:
        return self._hostname_checks_common_name

    @hostname_checks_common_name.setter
    def hostname_checks_common_name(self, value: bool) -> None:
        hostname_checks_common_name = bool(value)
        self._builder.set_hostname_checks_common_name(hostname_checks_common_name)
        self._hostname_checks_common_name = hostname_checks_common_name

    @property  # type: ignore[override]
    def verify_flags(self) -> int:
        return self._verify_flags

    @verify_flags.setter
    def verify_flags(self, value: int) -> None:
        verify_flags = int(value)
        self._builder.set_verify_flags(verify_flags)
        self._verify_flags = verify_flags

    @property
    def security_level(self) -> int:  # type: ignore[override]
        """Return a high security level (rustls defaults are strong)."""
        return 2

    @property
    def sni_callback(self) -> Callable | None:
        return self._sni_callback

    @sni_callback.setter
    def sni_callback(self, callback: Callable | None) -> None:
        if callback is not None:
            if not callable(callback):
                raise TypeError("not a callable object")
        self._sni_callback = callback

    @property
    def _msg_callback(self) -> Callable | None:
        return self._message_callback

    @_msg_callback.setter
    def _msg_callback(self, callback: Callable | None) -> None:
        if callback is not None and not callable(callback):
            raise TypeError("not a callable object")
        self._message_callback = callback

    @_msg_callback.deleter
    def _msg_callback(self) -> None:
        raise AttributeError(
            f"attribute '_msg_callback' of '{type(self).__name__}' objects cannot be deleted"
        )

    def set_servername_callback(self, callback: Callable | None) -> None:
        if callback is None:
            self.sni_callback = None
            return
        if not callable(callback):
            raise TypeError("not a callable object")

        self.sni_callback = callback

    def cert_store_stats(self) -> dict[str, int]:
        """Return cert store statistics."""
        return {
            "x509": self._builder.root_cert_count(),
            "x509_ca": self._builder.root_ca_count(),
            "crl": self._builder.crl_count(),
        }

    def get_ca_certs(self, binary_form: bool = False) -> list[dict] | list[bytes]:  # type: ignore[override]
        """Return loaded CA certs."""
        if binary_form:
            return self._builder.get_ca_certs_der()

        from . import _rustls

        return [
            _rustls.parse_certificate_dict(der)
            for der in self._builder.get_ca_certs_der()
        ]

    def session_stats(self) -> dict[str, int]:
        return self._builder.session_stats()

    @property
    def num_tickets(self) -> int:
        return self._builder.get_num_tickets()

    @num_tickets.setter
    def num_tickets(self, value: int) -> None:
        self._builder.set_num_tickets(
            value, self.protocol == PROTOCOL_TLS_SERVER
        )

    def set_npn_protocols(self, protocols: list[str]) -> None:  # type: ignore[override]
        """No-op — NPN is not supported by rustls."""
        pass

    if _HAS_ECH:

        def set_ech_configs(self, ech_config_list: bytes) -> TLSContext:
            """Create a **new** TLSContext clone with ECH enabled."""
            if not isinstance(ech_config_list, (bytes, bytearray, memoryview)):
                raise TypeError(
                    f"expected bytes-like object, got {type(ech_config_list).__name__}"
                )

            clone = TLSContext.__new__(TLSContext, self._protocol)
            clone.__init__(self._protocol)  # type: ignore[misc]

            clone._builder = self._builder.clone_builder()

            clone._verify_mode = self._verify_mode
            clone._check_hostname = self._check_hostname
            clone._options = self._options
            clone._minimum_version = self._minimum_version
            clone._maximum_version = self._maximum_version
            clone._alpn_protocols = list(self._alpn_protocols)
            clone._ciphers_string = self._ciphers_string
            clone._sni_callback = self._sni_callback
            clone._message_callback = self._message_callback
            clone._keylog_filename = self._keylog_filename
            clone._cert_chain_loaded = self._cert_chain_loaded
            clone._ca_certs_loaded = self._ca_certs_loaded
            clone._verify_flags = self._verify_flags
            clone._hostname_checks_common_name = self._hostname_checks_common_name
            clone._protocol = self._protocol

            clone._builder.set_ech_configs(bytes(ech_config_list))

            from ._constants import TLSVersion

            clone._minimum_version = TLSVersion.TLSv1_3
            clone._builder.set_min_version(int(TLSVersion.TLSv1_3))

            return clone

        @property
        def ech_enabled(self) -> bool:
            """Return True if ECH configs have been set."""
            return self._builder.has_ech()

    @staticmethod
    def _read_pem_file(source: str | bytes | os.PathLike) -> bytes:
        with open(os.fspath(source), "rb") as stream:
            return stream.read()

    def __repr__(self) -> str:
        return (
            f"<TLSContext"
            f" protocol={self._protocol}"
            f" verify_mode={self._verify_mode}"
            f" check_hostname={self._check_hostname}>"
        )
