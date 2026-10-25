from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Any

from ._buffer import _clamp_read_length, _ssize_t_index
from ._bio import MemoryBIO
from ._certificate import TLSCertificate
from ._constants import (
    ENCODING_DER,
    _HAS_ECH,
    CERT_NONE,
    SSL_ERROR_WANT_READ,
)
from ._exceptions import (
    SSLEOFError,
    SSLError,
    SSLWantReadError,
    SSLZeroReturnError,
)

if TYPE_CHECKING:
    from ._context import TLSContext


# Map protocol version u16 → TLSVersion string for cipher() tuple
_VERSION_MAP = {
    0x0303: "TLSv1.2",
    0x0304: "TLSv1.3",
}

# Map IANA suite debug names to OpenSSL-style names for cipher() tuple
_SUITE_TO_OPENSSL = {
    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256": "ECDHE-RSA-AES128-GCM-SHA256",
    "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384": "ECDHE-RSA-AES256-GCM-SHA384",
    "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256": "ECDHE-RSA-CHACHA20-POLY1305",
    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256": "ECDHE-ECDSA-AES128-GCM-SHA256",
    "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384": "ECDHE-ECDSA-AES256-GCM-SHA384",
    "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256": "ECDHE-ECDSA-CHACHA20-POLY1305",
    "TLS13_AES_128_GCM_SHA256": "TLS_AES_128_GCM_SHA256",
    "TLS13_AES_256_GCM_SHA384": "TLS_AES_256_GCM_SHA384",
    "TLS13_CHACHA20_POLY1305_SHA256": "TLS_CHACHA20_POLY1305_SHA256",
}


def _validate_session_type(session: Any) -> None:
    from . import _rustls

    if not isinstance(session, _rustls.RustlsSession):
        raise TypeError("Value is not a SSLSession.")


def _validate_constructor_session(session: Any, server_side: bool) -> None:
    if session is None:
        return
    if server_side:
        raise ValueError("session can only be specified in client mode")
    _validate_session_type(session)


def _validate_server_hostname(
    server_side: bool, server_hostname: str | bytes | None
) -> None:
    if server_side and server_hostname:
        raise ValueError("server_hostname can only be specified in client mode")


def _validate_channel_binding_type(cb_type: Any) -> None:
    if not isinstance(cb_type, str):
        raise TypeError(
            "get_channel_binding() argument 'cb_type' must be str, "
            f"not {type(cb_type).__name__}"
        )
    if cb_type != "tls-unique":
        raise ValueError(f"'{cb_type}' channel binding type not implemented")


class _TLSPrivateObject:
    def __init__(self, connection: _TLSConnection) -> None:
        self._connection = connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def get_verified_chain(self) -> list[TLSCertificate] | None:
        return self._connection._get_verified_chain()

    def get_unverified_chain(self) -> list[TLSCertificate] | None:
        return self._connection._get_unverified_chain()

    def uses_ktls_for_send(self) -> bool:
        return False

    @property
    def session(self) -> Any:
        return self._connection.session

    @session.setter
    def session(self, value: Any) -> None:
        self._connection.session = value


class _TLSConnection:
    """Sans-I/O TLS object — equivalent of ``ssl.SSLObject``.

    Created by ``TLSContext.wrap_bio(incoming, outgoing, ...)``.
    Asyncio's ``SSLProtocol`` drives this by:
      1. Writing ciphertext into ``incoming`` BIO
      2. Calling ``do_handshake()`` / ``read()`` / ``write()``
      3. Reading ciphertext from ``outgoing`` BIO to send on the wire
    """

    def __init__(
        self,
        context: TLSContext,
        incoming: MemoryBIO,
        outgoing: MemoryBIO,
        server_side: bool = False,
        server_hostname: str | None = None,
        session: Any = None,
    ) -> None:
        _validate_constructor_session(session, server_side)
        self._context = context
        self._connection_verify_mode = int(context.verify_mode)
        self._sni_owner = None
        self._acceptor = None
        self._sni_failure = None
        self._initial_server_builder = None
        self._offered_cipher_suites: frozenset[int] | None = None
        self._shared_cipher_candidates: tuple[tuple[int, str, str, int], ...] | None = None
        self._incoming = incoming
        self._outgoing = outgoing
        self._server_side = server_side
        self._server_hostname = server_hostname
        self._explicit_session = session
        self._conn: Any = None  # RustlsClientConnection or RustlsServerConnection
        self._handshake_started = False
        self._handshake_done = False
        self._shutdown = False
        self._shutdown_sent = False
        # Set only once the peer's close_notify and all plaintext are consumed.
        self._peer_closed = False

        self._pending_ct: bytes = b""
        self._pending_plaintext = b""
        self._maybe_buffered = False
        # Build the Rust connection via the context's config builder
        self._init_connection(session)

    def _init_connection(self, session: Any = None) -> None:
        """Create the Rust TLS connection state machine."""
        builder = self._context._get_builder()

        if self._server_side:
            from ._rustls import RustlsServerAcceptor

            self._initial_server_builder = builder.snapshot_server_builder()
            self._acceptor = RustlsServerAcceptor(
                self._context._msg_callback is not None,
            )
        else:
            hostname = self._server_hostname or "0.0.0.0"
            self._conn = builder.build_client_connection(
                hostname,
                session=session,
                capture_message_callback=self._context._msg_callback is not None,
            )

        # After building client connection, the state machine immediately
        # has a ClientHello to send — flush it to the outgoing BIO
        self._flush_outgoing()

    def _flush_outgoing(self) -> None:
        """Move any ciphertext from the Rust state machine to the outgoing BIO."""
        if self._conn is None:
            return
        while self._conn.wants_write():
            data = self._conn.write_tls()
            if data:
                self._outgoing.write(data)
            else:
                break

    def _dispatch_message_events(self) -> None:
        if self._conn is not None:
            events = self._conn.take_message_events()
        elif self._acceptor is not None:
            events = self._acceptor.take_message_events()
        else:
            return
        owner = self._sni_owner() if self._sni_owner is not None else self
        for direction, version, content_type, message_type, data in events:
            callback = self._context._msg_callback
            if callback is not None:
                callback(owner, direction, version, content_type, message_type, data)

    def _pump_incoming(self) -> None:
        """Move ciphertext from the incoming BIO into the Rust state machine.

        If rustls's internal buffer is full (``read_tls`` raises "message
        buffer full"), we stop feeding and put the unconsumed ciphertext
        back into the BIO so it will be picked up on the next call after
        the caller drains plaintext via ``process_new_packets`` +
        ``read_plaintext``.
        """
        data = self._incoming.read()
        if data:
            # read_tls may not consume all data at once (it reads one TLS
            # record at a time), so we must loop until everything is fed.
            view = memoryview(data)
            total = len(view)
            offset = 0
            while offset < total:
                try:
                    consumed = self._conn.read_tls(bytes(view[offset:]))
                except SSLError as e:  # Defensive:
                    # Rustls buffer full — stop feeding, stash the rest
                    if "buffer full" in str(e):
                        self._incoming.write(bytes(view[offset:]))
                        return
                    raise
                if consumed == 0:
                    break
                offset += consumed

    def _accept_client_hello(self) -> None:
        from ._rustls import report_callback_error

        if self._sni_failure is not None:
            raise self._sni_failure
        acceptor = self._acceptor
        try:
            if not acceptor.feed(self._incoming.read()):
                raise SSLWantReadError(
                    SSL_ERROR_WANT_READ, "The operation did not complete (read)"
                )
            self._dispatch_message_events()
            self._initial_server_builder.validate_server_hello(acceptor)
            self._offered_cipher_suites = frozenset(acceptor.cipher_suites())
            initial_context = self._context
            callback = initial_context.sni_callback
            if callback is not None:
                owner = self._sni_owner() if self._sni_owner is not None else self
                alert = 40 if owner is None else None
                if alert is None:
                    try:
                        result = callback(owner, acceptor.server_name(), initial_context)
                    except BaseException as error:
                        report_callback_error(error, callback)
                        alert = 40
                    else:
                        if result is not None:
                            try:
                                import operator

                                alert = operator.index(result)
                                if not -2147483648 <= alert <= 2147483647:
                                    raise OverflowError("Python int too large to convert to C long")
                                alert &= 255
                            except BaseException as error:
                                report_callback_error(error, callback)
                                alert = 80
                if alert is not None:
                    self._outgoing.write(acceptor.reject(alert))
                    self._sni_failure = SSLError(1, "[CALLBACK_FAILED] callback failed")
                    raise self._sni_failure
            self._shared_cipher_candidates = tuple(
                (
                    int(cipher["id"]) & 0xFFFF,
                    str(cipher["name"]),
                    str(cipher["protocol"]),
                    int(cipher["strength_bits"]),
                )
                for cipher in self._context.get_ciphers()
            )
            self._conn = self._initial_server_builder.accept_server_connection(
                acceptor,
                self._context._get_builder(),
                capture_message_callback=self._context._msg_callback is not None,
            )
            self._initial_server_builder = None
            self._acceptor = None
        except SSLError:
            self._outgoing.write(acceptor.take_alert())
            raise

    def do_handshake(self) -> None:
        """Perform the TLS handshake.

        Raises SSLWantReadError if more data is needed from the network.
        asyncio catches this and waits for more data.
        """
        if self._handshake_done:
            return
        if self._incoming.eof:
            raise SSLEOFError("EOF occurred in violation of protocol")
        self._handshake_started = True
        self._dispatch_message_events()

        if self._acceptor is not None:
            self._accept_client_hello()

        self._pump_incoming()

        # Process the TLS records
        try:
            self._conn.process_new_packets()
        except SSLError:
            # Flush any alert that rustls wants to send
            self._dispatch_message_events()
            self._flush_outgoing()
            raise
        self._dispatch_message_events()

        # Flush outgoing ciphertext (handshake messages)
        self._flush_outgoing()

        if self._conn.is_handshaking():
            raise SSLWantReadError(
                SSL_ERROR_WANT_READ, "The operation did not complete (read)"
            )

        self._handshake_done = True
        # process_new_packets() may have decrypted early application data
        self._maybe_buffered = True

    def read(self, n: int = 1024, buffer: Any | None = None) -> bytes | int:
        """Read decrypted data from the TLS connection.

        Returns bytes, or if *buffer* is given, reads into it and returns count.
        Raises SSLWantReadError if no data is available yet.

        Uses the fused ``decrypt_incoming`` Rust method that performs
        read_tls → process_new_packets → read_plaintext in a single
        Python→Rust call, handling buffer-full looping internally.
        """
        requested = _ssize_t_index(n)
        byte_view = None
        if buffer is not None:
            byte_view = memoryview(buffer)
            if byte_view.readonly:
                raise TypeError("read() argument 2 must be read-write bytes-like object")
            byte_view = byte_view.cast("B")
        read_length = _clamp_read_length(
            requested, None if byte_view is None else byte_view.nbytes
        )
        if read_length == 0:
            return b"" if byte_view is None else 0
        if byte_view is not None:
            buffer = byte_view
        if self._shutdown or self._peer_closed:
            return self._closed_read_result(buffer)
        if not self._handshake_done:
            self.do_handshake()

        max_len = read_length
        if self._pending_plaintext:
            data = self._pending_plaintext[:max_len]
            self._pending_plaintext = self._pending_plaintext[len(data) :]
            return self._read_result(data, buffer)

        # Read all available ciphertext from the BIO
        ciphertext = self._incoming.read()

        if ciphertext:
            # Fast path: one Rust call does everything
            try:
                plaintext, unconsumed = self._conn.decrypt_incoming(ciphertext, max_len)
            except SSLZeroReturnError:
                self._dispatch_message_events()
                self._peer_closed = True
                return self._closed_read_result(buffer)
            except SSLError:
                # Flush the fatal alert rustls queued for the peer.
                self._dispatch_message_events()
                self._flush_outgoing()
                raise

            # Stash any unconsumed ciphertext back in the BIO
            if unconsumed:
                self._incoming.write(unconsumed)

            self._dispatch_message_events()
            # Flush any outgoing data (post-handshake messages, key updates)
            self._flush_outgoing()

            if plaintext:
                return self._read_result(plaintext, buffer)

        # No ciphertext available (or it produced no plaintext).
        # Try draining any plaintext already buffered in rustls from
        # a previous decrypt_incoming call that hit max_len.
        try:
            data = self._conn.read_plaintext(max_len)
        except SSLZeroReturnError:
            self._peer_closed = True
            return self._closed_read_result(buffer)
        if data:
            return self._read_result(data, buffer)

        # Truly no data available
        if self._incoming.eof:
            raise SSLEOFError("EOF occurred in violation of protocol")
        raise SSLWantReadError(
            SSL_ERROR_WANT_READ, "The operation did not complete (read)"
        )

    def _closed_read_result(self, buffer: Any | None) -> bytes | int:
        if self._shutdown_sent:
            raise SSLZeroReturnError("TLS/SSL connection has been closed")
        if buffer is not None:
            return 0
        return b""

    def _read_result(self, data: bytes, buffer: Any | None) -> bytes | int:
        if buffer is None:
            return data
        nbytes = min(len(data), buffer.nbytes)
        buffer[:nbytes] = data[:nbytes]
        if nbytes < len(data):
            self._pending_plaintext = data[nbytes:] + self._pending_plaintext
        return nbytes

    def has_pending(self) -> bool:
        """True if plaintext or clean EOF may be available without network I/O."""
        return (
            self._peer_closed
            or bool(self._pending_ct)
            or bool(self._pending_plaintext)
            or self._maybe_buffered
        )

    def feed_decrypt(self, ciphertext: bytes, max_len: int) -> bytes:
        """Synchronous fast-path read used by :class:`TLSSocket`."""
        if self._shutdown or self._peer_closed:
            raise SSLZeroReturnError("TLS/SSL connection has been closed")
        if self._pending_plaintext:
            data = self._pending_plaintext[:max_len]
            self._pending_plaintext = self._pending_plaintext[len(data) :]
            self._pending_ct += ciphertext
            return data

        # Absorb any ciphertext left in the incoming BIO
        if self._incoming.pending:
            self._pending_ct = bytes(self._incoming.read()) + self._pending_ct

        pending = self._pending_ct
        if pending:
            ciphertext = pending + ciphertext if ciphertext else pending
            self._pending_ct = b""

        if ciphertext:
            try:
                plaintext, unconsumed = self._conn.decrypt_incoming(ciphertext, max_len)
            except SSLZeroReturnError:
                self._dispatch_message_events()
                self._peer_closed = True
                raise
            except SSLError:
                # Flush the fatal alert rustls queued for the peer.
                self._dispatch_message_events()
                self._flush_outgoing()
                raise
            self._pending_ct = unconsumed
            self._dispatch_message_events()
            # Flush any control messages rustls produced (key updates, etc).
            self._flush_outgoing()
            # Even a short read can leave a received close_notify to report.
            self._maybe_buffered = bool(unconsumed) or bool(plaintext)
            if self._incoming.eof and not plaintext:
                raise SSLEOFError("EOF occurred in violation of protocol")
            return plaintext

        # drain already decrypted.
        try:
            plaintext = self._conn.read_plaintext(max_len)
        except SSLZeroReturnError:
            self._peer_closed = True
            raise
        self._maybe_buffered = bool(plaintext)
        if self._incoming.eof and not plaintext:
            raise SSLEOFError("EOF occurred in violation of protocol")
        return plaintext

    def write(self, data: bytes | bytearray | memoryview) -> int:
        """Write plaintext data to be encrypted and sent.

        Returns number of bytes written. The encrypted ciphertext is
        placed in the outgoing BIO for the transport to send.
        """
        if self._shutdown or self._shutdown_sent:
            raise SSLZeroReturnError("TLS/SSL connection has been closed")

        if not self._handshake_done:
            self.do_handshake()

        # Ensure data is bytes for the Rust side
        if isinstance(data, (bytearray, memoryview)):
            data = bytes(data)

        n = self._conn.write_plaintext(data)
        self._dispatch_message_events()

        # Flush the resulting ciphertext to the outgoing BIO
        self._flush_outgoing()

        return n

    def unwrap(self) -> None:
        if self._shutdown:
            return
        if self._conn is None:
            self._shutdown = True
            return
        if not self._shutdown_sent:
            self._conn.send_close_notify()
            self._dispatch_message_events()
            self._flush_outgoing()
            self._shutdown_sent = True

        if self._incoming.pending:
            self._pump_incoming()
            try:
                self._conn.process_new_packets()
            except SSLError:
                self._dispatch_message_events()
                self._flush_outgoing()
                raise
            self._dispatch_message_events()
            self._flush_outgoing()

        if self._peer_closed:
            self._shutdown = True
            return
        if self._pending_plaintext or self._conn.pending():
            raise SSLWantReadError(
                SSL_ERROR_WANT_READ, "The operation did not complete (read)"
            )

        try:
            data = self._conn.read_plaintext(1)
        except SSLZeroReturnError:
            self._peer_closed = True
            self._shutdown = True
            return
        if data:
            self._pending_plaintext = data + self._pending_plaintext
        if self._incoming.eof:
            raise SSLEOFError("EOF occurred in violation of protocol")
        raise SSLWantReadError(
            SSL_ERROR_WANT_READ, "The operation did not complete (read)"
        )

    def getpeercert(self, binary_form: bool = False) -> dict | bytes | None:
        """Return the peer's certificate.

        If ``binary_form`` is True, return the DER-encoded bytes.
        Otherwise, return a dict matching CPython's getpeercert() format.
        Returns None if no certificate was presented.

        CPython behavior: when verify_mode is CERT_NONE and binary_form
        is False, returns {} (empty dict) after handshake — the cert is
        not validated so its contents are not exposed.
        """
        if not self._handshake_done:
            raise ValueError("handshake not done yet")

        certs = self._conn.peer_certificates()
        if not certs:
            return None

        if not binary_form:
            if self._context.verify_mode == CERT_NONE:
                return {}

        der_bytes = bytes(certs[0])

        if binary_form:
            return der_bytes

        from . import _rustls

        return _rustls.parse_certificate_dict(der_bytes)

    def cipher(self) -> tuple[str, str, int] | None:
        """Return a 3-tuple (cipher_name, tls_version, secret_bits) or None."""
        suite_name = self._conn.negotiated_cipher_suite()
        if suite_name is None:
            return None

        version_num = self._conn.protocol_version()
        version_str = (
            _VERSION_MAP.get(version_num, "unknown") if version_num else "unknown"
        )

        # Map IANA name to OpenSSL name
        openssl_name = _SUITE_TO_OPENSSL.get(suite_name, suite_name)

        bits = self._conn.negotiated_cipher_suite_bits() or 0

        return (openssl_name, version_str, bits)

    def shared_ciphers(self) -> list[tuple[str, str, int]] | None:
        """Return the peer-shared cipher list when available."""
        if not self._server_side or not self._handshake_done:
            return None
        if (
            self._offered_cipher_suites is None
            or self._shared_cipher_candidates is None
        ):
            return None
        version = self.version()
        if version is None:
            return None
        shared = [
            (name, protocol, bits)
            for suite_id, name, protocol, bits in self._shared_cipher_candidates
            if suite_id in self._offered_cipher_suites and protocol == version
        ]
        return shared or None

    def version(self) -> str | None:
        """Return the negotiated TLS version string, e.g. 'TLSv1.3'."""
        v = self._conn.protocol_version()
        if v is None:
            return None
        return _VERSION_MAP.get(v, None)

    def group(self) -> str | None:
        """Return the negotiated key exchange group name."""
        if self._conn is None:
            return None
        return self._conn.group()

    def client_sigalg(self) -> str | None:
        if self._conn is None:
            return None
        return self._conn.client_sigalg()

    def server_sigalg(self) -> str | None:
        if self._conn is None:
            return None
        return self._conn.server_sigalg()

    def selected_alpn_protocol(self) -> str | None:
        """Return the selected ALPN protocol as a string, or None."""
        proto = self._conn.alpn_protocol()
        if proto is None:
            return None
        return proto.decode("ascii", errors="replace")

    def selected_npn_protocol(self) -> None:
        """NPN is not supported by rustls. Always returns None."""
        return None

    def compression(self) -> None:
        """rustls does not support TLS compression. Always returns None."""
        return None

    def pending(self) -> int:
        """Return the number of already decrypted bytes available for read."""
        return self._conn.pending()

    def get_channel_binding(self, cb_type: str = "tls-unique") -> bytes | None:
        """Return channel binding data."""
        _validate_channel_binding_type(cb_type)
        if self._conn is None:
            return None
        return self._conn.tls_unique()

    def getpeername(self) -> tuple | None:
        """SSLObject doesn't have a socket, so no peername."""
        return None

    @property
    def context(self) -> TLSContext:
        """The TLSContext that created this object."""
        return self._context

    @context.setter
    def context(self, ctx: TLSContext) -> None:
        from ._context import TLSContext

        if not isinstance(ctx, TLSContext):
            raise TypeError("The value must be a SSLContext")
        self._dispatch_message_events()
        capture_message_callback = ctx._msg_callback is not None
        if self._conn is not None:
            self._conn.set_message_callback_enabled(capture_message_callback)
        elif self._acceptor is not None:
            self._acceptor.set_message_callback_enabled(capture_message_callback)
        self._context = ctx

    @property
    def server_side(self) -> bool:
        return self._server_side

    @property
    def server_hostname(self) -> str | None:
        return self._server_hostname

    @property
    def _sslobj(self) -> _TLSPrivateObject:
        return _TLSPrivateObject(self)

    def _get_verified_chain(self) -> list[TLSCertificate] | None:
        if self._conn is None:
            return None
        if self._connection_verify_mode == CERT_NONE:
            certs = self._conn.peer_certificates()
        else:
            certs = self._conn.verified_certificates()
        if certs is None:
            return None
        return [TLSCertificate._from_der(bytes(der)) for der in certs]

    def _get_unverified_chain(self) -> list[TLSCertificate] | None:
        if self._conn is None:
            return None
        certs = self._conn.peer_certificates()
        if certs is None:
            return None
        return [TLSCertificate._from_der(bytes(der)) for der in certs]

    def get_verified_chain(self) -> list[bytes]:
        certs = self._get_verified_chain()
        if certs is None:
            return []
        return [cert.public_bytes(ENCODING_DER) for cert in certs]

    def get_unverified_chain(self) -> list[bytes]:
        certs = self._get_unverified_chain()
        if certs is None:
            return []
        return [cert.public_bytes(ENCODING_DER) for cert in certs]

    @property
    def owner(self) -> Any:
        return self._sni_owner() if self._sni_owner is not None else None

    @property
    def session(self) -> Any:
        if not self._handshake_done and self._explicit_session is None:
            return None
        return self._conn.session()

    @session.setter
    def session(self, value: Any) -> None:
        _validate_session_type(value)
        if self._server_side:
            raise ValueError("Cannot set session for server-side SSLSocket.")
        if self._handshake_started:
            raise ValueError("Cannot set session after handshake.")
        if self._conn.set_session(value):
            self._outgoing.read()
            self._flush_outgoing()
        self._explicit_session = value

    @property
    def session_reused(self) -> bool:
        return self._conn.session_reused()

    if _HAS_ECH:

        @property
        def ech_status(self) -> str:
            """Return the ECH (Encrypted Client Hello) status string.

            Possible values:
              - "not_offered": ECH was not configured
              - "grease": GREASE ECH was sent (anti-ossification)
              - "offered": ECH was offered but handshake not complete
              - "accepted": ECH was accepted by the server
              - "rejected": ECH was rejected by the server
            """
            if self._conn is None:
                return "not_offered"
            try:
                return self._conn.ech_status()
            except AttributeError:
                # Server connections don't have ech_status
                return "not_offered"


class TLSObject:
    def __init__(
        self,
        context: TLSContext | None = None,
        incoming: MemoryBIO | None = None,
        outgoing: MemoryBIO | None = None,
        server_side: bool = False,
        server_hostname: str | None = None,
        session: Any = None,
    ) -> None:
        if context is None or incoming is None or outgoing is None:
            raise TypeError(
                f"{self.__class__.__name__} does not have a public constructor. "
                "Instances are returned by SSLContext.wrap_bio()."
            )
        _validate_server_hostname(server_side, server_hostname)
        connection = _TLSConnection(
            context=context,
            incoming=incoming,
            outgoing=outgoing,
            server_side=server_side,
            server_hostname=server_hostname,
            session=session,
        )
        connection._sni_owner = weakref.ref(self)
        object.__setattr__(self, "_connection", connection)

    def cipher(self) -> tuple[str, str, int] | None:
        return self._connection.cipher()

    def client_sigalg(self) -> str | None:
        return self._connection.client_sigalg()

    def compression(self) -> None:
        return self._connection.compression()

    def do_handshake(self) -> None:
        return self._connection.do_handshake()

    def get_channel_binding(self, cb_type: str = "tls-unique") -> bytes | None:
        return self._connection.get_channel_binding(cb_type)

    def get_unverified_chain(self) -> list[bytes]:
        return self._connection.get_unverified_chain()

    def get_verified_chain(self) -> list[bytes]:
        return self._connection.get_verified_chain()

    def getpeercert(self, binary_form: bool = False) -> dict | bytes | None:
        return self._connection.getpeercert(binary_form)

    def group(self) -> str | None:
        return self._connection.group()

    def pending(self) -> int:
        return self._connection.pending()

    def read(self, len: int = 1024, buffer: Any | None = None) -> bytes | int:
        return self._connection.read(len, buffer)

    def selected_alpn_protocol(self) -> str | None:
        return self._connection.selected_alpn_protocol()

    def selected_npn_protocol(self) -> None:
        return self._connection.selected_npn_protocol()

    def server_sigalg(self) -> str | None:
        return self._connection.server_sigalg()

    def shared_ciphers(self) -> list[tuple[str, str, int]] | None:
        return self._connection.shared_ciphers()

    def unwrap(self) -> None:
        return self._connection.unwrap()

    def verify_client_post_handshake(self) -> None:
        raise NotImplementedError(
            "RTLS does not support post-handshake authentication"
        )

    def version(self) -> str | None:
        return self._connection.version()

    def write(self, data: bytes | bytearray | memoryview) -> int:
        return self._connection.write(data)

    @property
    def context(self) -> TLSContext:
        return self._connection.context

    @context.setter
    def context(self, value: TLSContext) -> None:
        self._connection.context = value

    @property
    def server_hostname(self) -> str | None:
        return self._connection.server_hostname

    @property
    def server_side(self) -> bool:
        return self._connection.server_side

    @property
    def session(self) -> Any:
        return self._connection.session

    @session.setter
    def session(self, value: Any) -> None:
        self._connection.session = value

    @property
    def session_reused(self) -> bool:
        return self._connection.session_reused

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_connection":
            object.__setattr__(self, name, value)
        elif name in {"context", "session"}:
            setattr(self._connection, name, value)
        else:
            object.__setattr__(self, name, value)
