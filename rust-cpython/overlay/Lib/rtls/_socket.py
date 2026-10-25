from __future__ import annotations

from ._immutable import ImmutableType

import errno
import operator
import socket
import threading
import time
import weakref
from typing import TYPE_CHECKING, Any, Callable

from ._buffer import _clamp_read_length, _ssize_t_index
from ._bio import MemoryBIO
from ._certificate import TLSCertificate
from ._constants import _HAS_ECH, SSL_ERROR_WANT_READ, SSL_ERROR_WANT_WRITE
from ._exceptions import (
    SSLEOFError,
    SSLError,
    SSLWantReadError,
    SSLWantWriteError,
    SSLZeroReturnError,
)
from ._object import (
    _TLSConnection,
    _validate_channel_binding_type,
    _validate_constructor_session,
    _validate_server_hostname,
    _validate_session_type,
)
from ._stdlib import ssl as _stdlib_ssl

if TYPE_CHECKING:
    from ._context import TLSContext


_DEFAULT_BUFFER_SIZE = 16384

# Size of each ciphertext read from the underlying network socket.
_SOCKET_READ_BUFFER_SIZE = 65536
_SOCKET_WRITE_BUFFER_SIZE = 65536
_TLS_RECORD_HEADER_SIZE = 5
_CONNECT_PENDING_ERRORS = frozenset(
    {
        errno.EINPROGRESS,
        errno.EALREADY,
        errno.EWOULDBLOCK,
        errno.EAGAIN,
        errno.EINTR,
        errno.ETIMEDOUT,
    }
)


class _SocketTLSPrivateObject:
    def __init__(self, owner: TLSSocket, private_object: Any) -> None:
        self._owner_ref = weakref.ref(owner)
        self._private_object = private_object

    @property
    def owner(self) -> TLSSocket:
        owner = self._owner_ref()
        if owner is None:
            raise ReferenceError("TLS socket owner no longer exists")
        return owner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._private_object, name)

    @property
    def session(self) -> Any:
        return self._private_object.session

    @session.setter
    def session(self, value: Any) -> None:
        self._private_object.session = value

    def read(self, n: int = -1, buffer: Any = None) -> bytes | int:
        return self.owner._read_private(n, buffer)

    def write(self, data: Any) -> int:
        return self.owner._write_private(data)


def _read_tls_record(
    recv: Callable[[int], bytes], record: bytearray, record_size: int | None
) -> tuple[bytes, int | None]:
    while True:
        if record_size is not None:
            needed = record_size - len(record)
            if needed == 0:
                body = bytes(record)
                record.clear()
                return body, None
        else:
            needed = _TLS_RECORD_HEADER_SIZE - len(record)
            if needed == 0:
                header = bytes(record)
                record.clear()
                return header, int.from_bytes(header[3:5], "big")

        chunk = recv(needed)
        if not chunk:
            raise SSLEOFError("EOF on underlying transport")
        record.extend(chunk)


class TLSSocket(_stdlib_ssl.SSLSocket, metaclass=ImmutableType):
    """TLS-wrapped socket, equivalent of ``ssl.SSLSocket``.

    Inherits from ``ssl.SSLSocket`` so it passes isinstance checks
    (both ``isinstance(s, socket.socket)`` and ``isinstance(s, ssl.SSLSocket)``).
    Intercepts send/recv to route through the rustls TLS state machine.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> TLSSocket:
        # Use socket.socket.__new__ to allocate, skipping ssl.SSLSocket
        # which doesn't have its own __new__ anyway.
        return socket.socket.__new__(cls)

    def __init__(
        self,
        sock: socket.socket | None = None,
        context: TLSContext | None = None,
        server_side: bool = False,
        server_hostname: str | None = None,
        do_handshake_on_connect: bool = True,
        suppress_ragged_eofs: bool = True,
        session: Any = None,
    ) -> None:
        if sock is None or context is None:
            raise TypeError(
                f"{self.__class__.__name__} does not have a public constructor. "
                "Instances are returned by SSLContext.wrap_socket()."
            )
        _validate_server_hostname(server_side, server_hostname)
        _validate_constructor_session(session, server_side)
        # NOTE: We intentionally do NOT call ssl.SSLSocket.__init__() because
        # it raises TypeError (SSLSocket has no public constructor). All real
        # initialization goes through socket.socket.__init__() instead.
        self._rtls_context = context
        self._server_side = server_side
        self._server_hostname = None
        self._do_handshake_on_connect = do_handshake_on_connect
        self._suppress_ragged_eofs = suppress_ragged_eofs
        self._pending_session = session
        self._connected = False
        self._connection_attempted = False
        self._plain_socket = False
        self._tls_started = False
        self._sslobj_socket_proxy: _SocketTLSPrivateObject | None = None
        self._closed = False

        # Take over the underlying socket's fd.
        # Save socket properties before detaching
        _family = sock.family
        _type = sock.type
        _proto = sock.proto
        _timeout = sock.gettimeout()

        # First, close the fd that socket.__new__ may have created.
        try:
            # If __new__ allocated a real fd, close it
            if self.fileno() >= 0:
                socket.socket.close(self)  # Defensive: should not happen, ever.
        except Exception:  # Defensive: just in case(...)
            pass

        fd = sock.detach()
        # Re-init with the real fd
        socket.socket.__init__(
            self,
            family=_family,
            type=_type,
            proto=_proto,
            fileno=fd,
        )

        # Restore the timeout/blocking mode from the original socket
        if _timeout is None:
            self.setblocking(True)
        else:
            self.settimeout(_timeout)

        # Create the MemoryBIO pair and _TLSConnection
        self._incoming = MemoryBIO()
        self._outgoing = MemoryBIO()
        self._handshake_record = bytearray()
        self._handshake_record_size: int | None = None
        self._ciphertext_condition = threading.Condition()
        self._ciphertext_write_in_progress = False
        self._pending_ciphertext = bytearray()

        self._sslobj_internal: _TLSConnection | None = None
        from ._context import _encode_server_hostname

        try:
            self._server_hostname = _encode_server_hostname(server_hostname)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(
                    "closing TLS socket after hostname encoding failed also failed: "
                    f"{cleanup_error}"
                )
            raise

        try:
            self.getpeername()
            self._connected = True
        except OSError as peer_error:
            if peer_error.errno not in (errno.ENOTCONN, errno.EINVAL):
                raise
            try:
                self.setblocking(False)
                try:
                    pre_handshake_data = socket.socket.recv(self, 1)
                except OSError as recv_error:
                    if recv_error.errno not in (errno.ENOTCONN, errno.EINVAL):
                        raise
                    pre_handshake_data = b""
            finally:
                self.settimeout(_timeout)
            if pre_handshake_data:
                reason = "Closed before TLS handshake with data in recv buffer."
                self.close()
                raise SSLError(
                    peer_error.errno,
                    reason,
                    reason=reason,
                    library=None,
                )
            self._connected = False

        if self._connected:
            self._create_sslobj()
            if self._do_handshake_on_connect:
                try:
                    self.do_handshake()
                except BaseException:
                    self.close()
                    raise

    def accept(self) -> tuple[TLSSocket, Any]:
        accepted, address = socket.socket.accept(self)
        try:
            wrapped = self._rtls_context.wrap_socket(
                accepted,
                server_side=True,
                do_handshake_on_connect=self._do_handshake_on_connect,
                suppress_ragged_eofs=self._suppress_ragged_eofs,
            )
        except BaseException:
            accepted.close()
            raise
        return wrapped, address

    def _create_sslobj(self) -> None:
        """Create the internal _TLSConnection."""
        self._tls_started = True
        self._sslobj_internal = _TLSConnection(
            context=self._rtls_context,
            incoming=self._incoming,
            outgoing=self._outgoing,
            server_side=self._server_side,
            server_hostname=self._server_hostname,
            session=self._pending_session,
        )
        self._pending_session = None
        self._sslobj_internal._sni_owner = weakref.ref(self)
        self._sslobj_socket_proxy = _SocketTLSPrivateObject(
            self, self._sslobj_internal._sslobj
        )

    def _discard_connection_attempt(self, session: Any, retryable: bool) -> None:
        self._sslobj_internal = None
        self._sslobj_socket_proxy = None
        self._pending_session = session
        self._connected = False
        self._connection_attempted = not retryable
        self._incoming = MemoryBIO()
        self._outgoing = MemoryBIO()
        self._handshake_record.clear()
        self._handshake_record_size = None
        self._pending_ciphertext.clear()

    def _handle_connection_error(self, session: Any, error: BaseException) -> None:
        try:
            self.getpeername()
        except OSError:
            pass
        else:
            self._connected = True
            return

        if isinstance(error, (ValueError, TypeError)):
            self._discard_connection_attempt(session, retryable=True)
            return

        error_number = getattr(error, "errno", None)
        if isinstance(error, TimeoutError) or error_number in _CONNECT_PENDING_ERRORS:
            return

        self._discard_connection_attempt(session, retryable=False)

    def connect(self, addr: Any) -> None:
        """Connect and perform TLS handshake."""
        if self._server_side:
            raise ValueError("can't connect in server-side mode")
        if self._connected or self._connection_attempted:
            raise ValueError("attempt to connect already-connected SSLSocket!")
        session = self._pending_session
        self._create_sslobj()
        self._connection_attempted = True
        try:
            socket.socket.connect(self, addr)
        except (OSError, ValueError, TypeError) as error:
            self._handle_connection_error(session, error)
            raise
        self._connected = True
        if self._do_handshake_on_connect:
            self.do_handshake()

    def connect_ex(self, addr: Any) -> int:
        """Connect and perform TLS handshake, returning error code."""
        if self._server_side:
            raise ValueError("can't connect in server-side mode")
        if self._connected or self._connection_attempted:
            raise ValueError("attempt to connect already-connected SSLSocket!")
        session = self._pending_session
        self._create_sslobj()
        self._connection_attempted = True
        try:
            rc = socket.socket.connect_ex(self, addr)
        except (OSError, ValueError, TypeError) as error:
            self._handle_connection_error(session, error)
            raise
        if rc == 0:
            self._connected = True
            if self._do_handshake_on_connect:
                self.do_handshake()
        elif rc not in _CONNECT_PENDING_ERRORS:
            self._discard_connection_attempt(session, retryable=False)
        return rc

    def do_handshake(self) -> None:  # type: ignore[override]
        """Perform the TLS handshake, blocking until complete."""
        if self._incoming.eof:
            raise SSLEOFError("EOF occurred in violation of protocol")
        if self._sslobj_internal is None:
            self._create_sslobj()

        self._flush_outgoing()

        timeout = self.gettimeout()
        self._do_handshake_loop(timeout)

    def _do_handshake_loop(self, timeout: float | None) -> None:
        """Inner handshake loop - drives _TLSConnection.do_handshake()."""
        while True:
            try:
                self._sslobj_internal.do_handshake()
                self._flush_outgoing()
                return
            except SSLWantReadError:
                # Flush any outgoing data (handshake messages)
                self._flush_outgoing()
                # Read more ciphertext from the network
                self._pull_incoming(timeout)
            except SSLWantWriteError:
                self._flush_outgoing()
            except SSLError as handshake_error:
                try:
                    self._flush_outgoing()
                except OSError as alert_error:
                    raise handshake_error from alert_error
                raise

    def _uses_plain_transport(self) -> bool:
        return self._plain_socket or self.fileno() < 0 or (
            self._sslobj_internal is None
            and not self._tls_started
            and not self._connected
        )

    def send(self, data: bytes, flags: int = 0) -> int:  # type: ignore[override]
        """Encrypt and send data."""
        if self._uses_plain_transport():
            return socket.socket.send(self, data, flags)
        if not data:
            return 0
        if self._incoming.eof:
            raise SSLEOFError("EOF occurred in violation of protocol")
        obj = self._sslobj_internal
        if obj is None:
            raise SSLError("SSL handshake not done")
        if not obj._handshake_done:
            self.do_handshake()

        self._flush_outgoing()
        n = obj.write(data)
        try:
            self._flush_outgoing()
        except SSLWantWriteError:
            if n == 0:
                raise
        return n

    def sendall(self, data: bytes, flags: int = 0) -> None:  # type: ignore[override]
        """Send all data, blocking until complete."""
        if self._uses_plain_transport():
            socket.socket.sendall(self, data, flags)
            return
        view = memoryview(data)
        total = len(view)
        sent = 0
        while sent < total:
            n = self.send(bytes(view[sent:]))
            sent += n
        self._flush_outgoing()

    def recv(self, buflen: int = _DEFAULT_BUFFER_SIZE, flags: int = 0) -> bytes:
        """Receive decrypted data."""
        if self._uses_plain_transport():
            return socket.socket.recv(self, buflen, flags)
        return self._recv_tls(
            buflen, suppress_ragged_eofs=self._suppress_ragged_eofs
        )

    def _recv_tls(self, buflen: int, suppress_ragged_eofs: bool) -> bytes:
        if buflen < 0:
            raise ValueError("negative buffersize in recv")
        if buflen == 0:
            return b""
        obj = self._sslobj_internal
        if obj is None:
            raise SSLError("SSL handshake not done")
        if obj._shutdown:
            return b""
        if not obj._handshake_done:
            self.do_handshake()

        while True:
            # 1. Drain plaintext rustls already holds, without touching the
            #    network, including a close_notify after the last data read.
            if obj.has_pending() or obj._incoming.pending:
                try:
                    data = obj.feed_decrypt(b"", buflen)
                except SSLZeroReturnError:
                    return b""
                if data:
                    return data

            # 2. Flush any control messages queued by rustls.
            self._flush_outgoing()

            # 3. Read more ciphertext directly from the network.
            try:
                chunk, self._handshake_record_size = _read_tls_record(
                    lambda size: socket.socket.recv(self, size),
                    self._handshake_record,
                    self._handshake_record_size,
                )
            except (BlockingIOError, InterruptedError):
                raise SSLWantReadError(
                    SSL_ERROR_WANT_READ, "The operation did not complete (read)"
                )
            except SSLEOFError:
                if not self._incoming.eof:
                    self._incoming.write_eof()
                try:
                    data = obj.feed_decrypt(b"", buflen)
                except SSLEOFError:
                    if suppress_ragged_eofs:
                        return b""
                    raise
                except SSLZeroReturnError:
                    return b""
                if data:
                    return data
                if suppress_ragged_eofs:
                    return b""
                raise SSLEOFError("EOF occurred in violation of protocol")
            except (socket.timeout, TimeoutError):
                raise  # Let timeout propagate unchanged.
            except OSError as e:
                if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                    raise SSLWantReadError(
                        SSL_ERROR_WANT_READ, "The operation did not complete (read)"
                    )
                raise

            if not chunk:
                data = obj.feed_decrypt(chunk, buflen)
                if data:
                    return data
                continue

            # 4. Feed + decrypt. If only handshake/control records arrived
            #    this yields no plaintext — loop and read more.
            try:
                data = obj.feed_decrypt(chunk, buflen)
            except SSLZeroReturnError:
                return b""
            if data:
                return data

    def recv_into(
        self, buffer: Any, nbytes: int | None = None, flags: int = 0
    ) -> int:  # type: ignore[override]
        """Receive decrypted data into a buffer."""
        if self._uses_plain_transport():
            if nbytes is None:
                return socket.socket.recv_into(self, buffer, flags=flags)
            return socket.socket.recv_into(self, buffer, nbytes, flags)

        view = None
        if nbytes is None:
            view = memoryview(buffer)
            nbytes = view.nbytes or 1024
        if flags:
            raise ValueError("non-zero flags not allowed on TLS sockets")
        nbytes = _ssize_t_index(nbytes)
        if view is None:
            view = memoryview(buffer)
        if view.readonly:
            raise TypeError("recv_into() argument 1 must be read-write bytes-like object")
        view = view.cast("B")
        nbytes = _clamp_read_length(nbytes, view.nbytes)
        if nbytes == 0:
            return 0
        data = self.recv(nbytes)
        n = len(data)
        view[:n] = data
        return n

    def read(  # type: ignore[override]
        self, n: int = _DEFAULT_BUFFER_SIZE, buffer: bytearray | None = None
    ) -> bytes | int:
        """Read decrypted data. Alias matching ssl.SSLSocket.read()."""
        if self._sslobj_internal is None:
            raise ValueError("Read on closed or unwrapped SSL socket.")
        requested = _ssize_t_index(n)
        if buffer is not None:
            view = memoryview(buffer).cast("B")
            if view.readonly:
                raise TypeError("read() argument 2 must be read-write bytes-like object")
            n = _clamp_read_length(requested, view.nbytes)
            if n == 0:
                return 0
            data = self.recv(n)
            nbytes = len(data)
            view[:nbytes] = data
            return nbytes
        n = _clamp_read_length(requested, None)
        if n == 0:
            return b""
        return self.recv(n)

    def write(self, data: bytes) -> int:  # type: ignore[override]
        """Write data to be encrypted. Alias matching ssl.SSLSocket.write()."""
        if self._sslobj_internal is None:
            raise ValueError("Write on closed or unwrapped SSL socket.")
        return self.send(data)

    def _flush_outgoing(self) -> None:
        """Send any pending ciphertext from the outgoing BIO to the network."""
        timeout = self.gettimeout()
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._ciphertext_condition:
            waited = False
            while self._ciphertext_write_in_progress:
                if timeout == 0:
                    raise SSLWantWriteError(
                        SSL_ERROR_WANT_WRITE, "The operation did not complete (write)"
                    )
                waited = True
                if deadline is None:
                    self._ciphertext_condition.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout("timed out")
                    self._ciphertext_condition.wait(remaining)
            if waited and deadline is not None and time.monotonic() >= deadline:
                raise socket.timeout("timed out")
            self._ciphertext_write_in_progress = True

        try:
            while True:
                with self._ciphertext_condition:
                    if not self._pending_ciphertext:
                        data = self._outgoing.read(_SOCKET_WRITE_BUFFER_SIZE)
                        if not data:
                            return
                        self._pending_ciphertext.extend(data)
                    data = bytes(self._pending_ciphertext)

                try:
                    sent = socket.socket.send(self, data)
                except BlockingIOError as error:
                    raise SSLWantWriteError(
                        SSL_ERROR_WANT_WRITE,
                        "The operation did not complete (write)",
                    ) from error
                if sent == 0:
                    raise SSLError("connection closed during TLS write")

                with self._ciphertext_condition:
                    del self._pending_ciphertext[:sent]
        finally:
            with self._ciphertext_condition:
                self._ciphertext_write_in_progress = False
                self._ciphertext_condition.notify_all()

    def _pull_incoming(self, timeout: float | None = None) -> None:
        """Read ciphertext from the network into the incoming BIO."""
        try:
            data, self._handshake_record_size = _read_tls_record(
                lambda size: socket.socket.recv(self, size),
                self._handshake_record,
                self._handshake_record_size,
            )
        except (BlockingIOError, InterruptedError):
            raise SSLWantReadError(
                SSL_ERROR_WANT_READ, "The operation did not complete (read)"
            )
        except (socket.timeout, TimeoutError):
            raise  # Let timeout propagate — don't convert to SSLWantReadError
        except OSError as e:
            if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                raise SSLWantReadError(
                    SSL_ERROR_WANT_READ, "The operation did not complete (read)"
                )
            raise

        if not data:
            raise SSLEOFError("EOF on underlying transport")

        self._incoming.write(data)

    def _read_private(self, n: int = -1, buffer: Any = None) -> bytes | int:
        requested = _ssize_t_index(n)
        if buffer is None:
            n = _clamp_read_length(requested, None)
            if n == 0:
                return b""
            return self._recv_tls(n, suppress_ragged_eofs=False)
        view = memoryview(buffer)
        if view.readonly:
            raise TypeError("read() argument 2 must be read-write bytes-like object")
        view = view.cast("B")
        n = _clamp_read_length(requested, view.nbytes)
        if n == 0:
            return 0
        data = self._recv_tls(n, suppress_ragged_eofs=False)
        view[: len(data)] = data
        return len(data)

    def _write_private(self, data: Any) -> int:
        if self._incoming.eof:
            raise SSLEOFError("EOF occurred in violation of protocol")
        return self.send(data)

    def getpeercert(self, binary_form: bool = False) -> dict | bytes | None:  # type: ignore[override]
        """Return the peer's certificate."""
        if self._sslobj_internal is None:
            self.getpeername()
            return None
        return self._sslobj_internal.getpeercert(binary_form)

    def sendfile(self, file: Any, offset: int = 0, count: int | None = None) -> int:
        if self._uses_plain_transport():
            return socket.socket.sendfile(self, file, offset, count)
        if self._sslobj_internal is None:
            raise SSLError("SSL handshake not done")
        return socket.socket._sendfile_use_send(self, file, offset, count)

    def cipher(self) -> tuple[str, str, int] | None:
        """Return cipher info tuple."""
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.cipher()

    def shared_ciphers(self) -> list[tuple[str, str, int]] | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.shared_ciphers()

    def version(self) -> str | None:
        """Return the negotiated TLS version string."""
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.version()

    def group(self) -> str | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.group()

    def client_sigalg(self) -> str | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.client_sigalg()

    def server_sigalg(self) -> str | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.server_sigalg()

    def selected_alpn_protocol(self) -> str | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.selected_alpn_protocol()

    def selected_npn_protocol(self) -> None:
        return None

    def compression(self) -> None:
        return None

    def pending(self) -> int:
        if self._sslobj_internal is None:
            return 0
        return self._sslobj_internal.pending()

    def get_channel_binding(self, cb_type: str = "tls-unique") -> bytes | None:
        _validate_channel_binding_type(cb_type)
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.get_channel_binding(cb_type)

    def unwrap(self) -> TLSSocket:
        """Shut down TLS and return this socket in plain-socket mode."""
        if self._sslobj_internal is None:
            raise ValueError("No SSL wrapper around " + str(self))
        while True:
            try:
                self._sslobj_internal.unwrap()
            except SSLWantReadError:
                self._flush_outgoing()
                if (
                    self.gettimeout() == 0
                    or self._sslobj_internal.pending()
                    or self._sslobj_internal._pending_plaintext
                ):
                    raise
                self._pull_incoming()
            else:
                self._flush_outgoing()
                break
        self._sslobj_internal = None
        self._sslobj_socket_proxy = None
        self._plain_socket = True
        return self

    def shutdown(self, how: int) -> None:
        """Shut down one or both halves of the connection."""
        socket.socket.shutdown(self, how)

    def close(self) -> None:
        """Close the TLS connection and underlying socket.

        When ``makefile()`` references are still open (``_io_refs > 0``),
        this only marks the socket as closed — the TLS state and fd stay
        alive so buffered I/O streams (and direct send/recv) keep working.
        The actual cleanup is deferred to ``_real_close()`` which runs once
        all makefile references have been drained.
        """
        self._closed = True
        if self._io_refs <= 0:  # type: ignore[attr-defined]
            self._real_close()

    def _real_close(self) -> None:
        """Tear down TLS state and close the underlying fd.

        Called by the inherited ``socket.socket`` machinery once
        ``_io_refs`` drops to zero (all makefile wrappers are closed).
        """
        if self._sslobj_internal is not None:
            try:
                self._sslobj_internal.unwrap()
                self._flush_outgoing()
            except Exception:  # Defensive:
                pass
            self._sslobj_internal = None
            self._sslobj_socket_proxy = None
        socket.socket._real_close(self)  # type: ignore[attr-defined]

    @property  # type: ignore[override]
    def context(self) -> TLSContext:
        return self._rtls_context

    @context.setter
    def context(self, ctx: TLSContext) -> None:
        if self._sslobj_internal is not None:
            self._sslobj_internal.context = ctx
        self._rtls_context = ctx

    @property
    def server_side(self) -> bool:  # type: ignore[override]
        return self._server_side

    @property
    def server_hostname(self) -> str | None:  # type: ignore[override]
        return self._server_hostname

    @property
    def session(self) -> Any:
        if self._sslobj_internal is None:
            return self._pending_session
        return self._sslobj_internal.session

    @session.setter
    def session(self, value: Any) -> None:
        _validate_session_type(value)
        if self._server_side:
            raise ValueError("Cannot set session for server-side SSLSocket.")
        if self._sslobj_internal is None:
            self._pending_session = value
        else:
            self._sslobj_internal.session = value

    @property
    def session_reused(self) -> bool | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.session_reused

    # urllib3-future compatibility
    @property
    def _sslobj(self) -> Any:
        if self._sslobj_internal is None:
            return None
        if self._sslobj_socket_proxy is None:
            self._sslobj_socket_proxy = _SocketTLSPrivateObject(
                self, self._sslobj_internal._sslobj
            )
        return self._sslobj_socket_proxy

    @_sslobj.setter
    def _sslobj(self, value: Any) -> None:
        """Allow setting _sslobj (ssl.SSLSocket._real_close sets it to None)."""
        self._sslobj_internal = value
        self._sslobj_socket_proxy = None
        if value is not None:
            self._tls_started = True

    @property
    def sslobj(self) -> _TLSConnection | None:
        return self._sslobj_internal

    def get_verified_chain(self) -> list[bytes]:
        if self._sslobj_internal is None:
            return []
        return self._sslobj_internal.get_verified_chain()

    def get_unverified_chain(self) -> list[bytes]:
        if self._sslobj_internal is None:
            return []
        return self._sslobj_internal.get_unverified_chain()

    if _HAS_ECH:

        @property
        def ech_status(self) -> str:
            """Return the ECH status string. See _TLSConnection.ech_status."""
            if self._sslobj_internal is None:
                return "not_offered"
            return self._sslobj_internal.ech_status

    def recvfrom(self, buflen: int = _DEFAULT_BUFFER_SIZE, flags: int = 0) -> Any:
        if self._tls_started and not self._plain_socket:
            raise ValueError(f"recvfrom not allowed on instances of {self.__class__}")
        return socket.socket.recvfrom(self, buflen, flags)

    def recvfrom_into(
        self, buffer: Any, nbytes: int | None = None, flags: int = 0
    ) -> Any:
        if self._tls_started and not self._plain_socket:
            raise ValueError(
                f"recvfrom_into not allowed on instances of {self.__class__}"
            )
        if self._uses_plain_transport():
            if nbytes is None:
                return socket.socket.recvfrom_into(self, buffer, flags=flags)
            return socket.socket.recvfrom_into(self, buffer, nbytes, flags)
        view = memoryview(buffer)
        nbytes = 0 if nbytes is None else operator.index(nbytes)
        if nbytes < 0:
            raise ValueError("negative buffersize in recvfrom_into")
        if nbytes > view.nbytes:
            raise ValueError("nbytes is greater than the length of the buffer")
        return socket.socket.recvfrom_into(self, buffer, nbytes, flags)

    def sendto(self, data: Any, flags_or_addr: Any, addr: Any = None) -> Any:
        if self._tls_started and not self._plain_socket:
            raise ValueError(f"sendto not allowed on instances of {self.__class__}")
        if addr is None:
            return socket.socket.sendto(self, data, flags_or_addr)
        return socket.socket.sendto(self, data, flags_or_addr, addr)

    def dup(self) -> None:
        raise NotImplementedError(
            f"Can't dup() {self.__class__.__name__} instances"
        )

    def recvmsg(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("recvmsg not allowed on TLS sockets")

    def recvmsg_into(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("recvmsg_into not allowed on TLS sockets")

    def sendmsg(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("sendmsg not allowed on TLS sockets")

    def __enter__(self) -> TLSSocket:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        try:
            peer = self.getpeername()
        except Exception:
            peer = None
        return (
            f"<TLSSocket"
            f" server_side={self._server_side}"
            f" server_hostname={self._server_hostname!r}"
            f" peer={peer}>"
        )


class TLSStreamSocket:
    """TLS over a socket-compatible byte stream without file descriptors."""

    def __init__(
        self,
        sock: Any,
        context: TLSContext,
        server_side: bool = False,
        server_hostname: str | None = None,
        do_handshake_on_connect: bool = True,
        suppress_ragged_eofs: bool = True,
        session: Any = None,
    ) -> None:
        if session is not None:
            if server_side:
                raise ValueError("session can only be specified in client mode")
            _validate_session_type(session)
        self._transport = sock
        self._rtls_context = context
        self._server_side = server_side
        self._server_hostname = None
        self._do_handshake_on_connect = do_handshake_on_connect
        self._suppress_ragged_eofs = suppress_ragged_eofs
        self._pending_session = session
        self._incoming = MemoryBIO()
        self._outgoing = MemoryBIO()
        self._handshake_record = bytearray()
        self._handshake_record_size: int | None = None
        self._sslobj_internal: _TLSConnection | None = None
        self._closed = False
        from ._context import _encode_server_hostname

        try:
            self._server_hostname = _encode_server_hostname(server_hostname)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(
                    "closing TLS socket after hostname encoding failed also failed: "
                    f"{cleanup_error}"
                )
            raise

        try:
            sock.getpeername()
        except OSError:
            self._connected = False
        else:
            self._connected = True

        if self._connected:
            self._create_sslobj()
            if self._do_handshake_on_connect:
                try:
                    self.do_handshake()
                except BaseException:
                    self.close()
                    raise

    def _create_sslobj(self) -> None:
        self._sslobj_internal = _TLSConnection(
            context=self._rtls_context,
            incoming=self._incoming,
            outgoing=self._outgoing,
            server_side=self._server_side,
            server_hostname=self._server_hostname,
            session=self._pending_session,
        )
        self._pending_session = None
        self._sslobj_internal._sni_owner = weakref.ref(self)

    def connect(self, addr: Any) -> None:
        if self._server_side:
            raise ValueError("can't connect in server-side mode")
        if self._connected:
            raise ValueError("attempt to connect already-connected SSLSocket!")
        self._transport.connect(addr)
        self._connected = True
        self._create_sslobj()
        if self._do_handshake_on_connect:
            self.do_handshake()

    def connect_ex(self, addr: Any) -> int:
        if self._server_side:
            raise ValueError("can't connect in server-side mode")
        if self._connected:
            raise ValueError("attempt to connect already-connected SSLSocket!")
        result = self._transport.connect_ex(addr)
        if result == 0:
            self._connected = True
            self._create_sslobj()
            if self._do_handshake_on_connect:
                self.do_handshake()
        return result

    def do_handshake(self) -> None:
        if self._sslobj_internal is None:
            self._create_sslobj()
        while True:
            try:
                self._sslobj_internal.do_handshake()
                self._flush_outgoing()
                return
            except SSLWantReadError:
                self._flush_outgoing()
                self._pull_incoming()
            except SSLWantWriteError:
                self._flush_outgoing()
            except SSLError as handshake_error:
                try:
                    self._flush_outgoing()
                except OSError as alert_error:
                    raise handshake_error from alert_error
                raise

    def send(self, data: bytes, flags: int = 0) -> int:
        if flags:
            raise ValueError("non-zero flags not allowed on TLS sockets")
        if not data:
            return 0
        if self._sslobj_internal is None:
            raise SSLError("SSL handshake not done")
        written = self._sslobj_internal.write(data)
        self._flush_outgoing()
        return written

    def sendall(self, data: bytes, flags: int = 0) -> None:
        sent = 0
        while sent < len(data):
            sent += self.send(data[sent:], flags)

    def recv(self, buflen: int = _DEFAULT_BUFFER_SIZE, flags: int = 0) -> bytes:
        if flags:
            raise ValueError("non-zero flags not allowed on TLS sockets")
        if buflen < 0:
            raise ValueError("negative buffersize in recv")
        if buflen == 0:
            return b""
        obj = self._sslobj_internal
        if obj is None:
            raise SSLError("SSL handshake not done")
        if obj._shutdown:
            return b""

        while True:
            if obj.has_pending() or obj._incoming.pending:
                try:
                    data = obj.feed_decrypt(b"", buflen)
                except SSLZeroReturnError:
                    return b""
                if data:
                    return data

            self._flush_outgoing()
            chunk = self._transport.recv(_SOCKET_READ_BUFFER_SIZE)
            if not chunk:
                if not self._incoming.eof:
                    self._incoming.write_eof()
                try:
                    data = obj.feed_decrypt(b"", buflen)
                except SSLEOFError:
                    if self._suppress_ragged_eofs:
                        return b""
                    raise
                except SSLZeroReturnError:
                    return b""
                if data:
                    return data
                if self._suppress_ragged_eofs:
                    return b""
                raise SSLEOFError("EOF occurred in violation of protocol")
            try:
                data = obj.feed_decrypt(chunk, buflen)
            except SSLZeroReturnError:
                return b""
            if data:
                return data

    def recv_into(self, buffer: Any, nbytes: int | None = None, flags: int = 0) -> int:
        view = memoryview(buffer)
        if view.readonly:
            raise TypeError("recv_into() argument 1 must be read-write bytes-like object")
        view = view.cast("B")
        if nbytes is None:
            nbytes = view.nbytes
        if nbytes > view.nbytes:
            raise ValueError("buffer too small for requested bytes")
        if nbytes == 0:
            return 0
        data = self.recv(nbytes, flags)
        view[: len(data)] = data
        return len(data)

    def read(self, n: int = _DEFAULT_BUFFER_SIZE, buffer: Any = None) -> bytes | int:
        if buffer is None:
            if n < 0:
                raise ValueError("size should not be negative")
            return self.recv(n)
        view = memoryview(buffer).cast("B")
        if view.readonly:
            raise TypeError("read() argument 2 must be read-write bytes-like object")
        if n <= 0 or n > view.nbytes:
            n = view.nbytes
        return self.recv_into(view, n)

    def write(self, data: bytes) -> int:
        return self.send(data)

    def _flush_outgoing(self) -> None:
        data = self._outgoing.read()
        if data:
            self._transport.sendall(data)

    def _pull_incoming(self) -> None:
        data, self._handshake_record_size = _read_tls_record(
            self._transport.recv,
            self._handshake_record,
            self._handshake_record_size,
        )
        self._incoming.write(data)

    def getpeercert(self, binary_form: bool = False) -> dict | bytes | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.getpeercert(binary_form)

    def cipher(self) -> tuple[str, str, int] | None:
        return self._sslobj_internal.cipher() if self._sslobj_internal else None

    def version(self) -> str | None:
        return self._sslobj_internal.version() if self._sslobj_internal else None

    def group(self) -> str | None:
        return self._sslobj_internal.group() if self._sslobj_internal else None

    def client_sigalg(self) -> str | None:
        return self._sslobj_internal.client_sigalg() if self._sslobj_internal else None

    def server_sigalg(self) -> str | None:
        return self._sslobj_internal.server_sigalg() if self._sslobj_internal else None

    def selected_alpn_protocol(self) -> str | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.selected_alpn_protocol()

    def pending(self) -> int:
        return self._sslobj_internal.pending() if self._sslobj_internal else 0

    def get_channel_binding(self, cb_type: str = "tls-unique") -> bytes | None:
        _validate_channel_binding_type(cb_type)
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.get_channel_binding(cb_type)

    def unwrap(self) -> Any:
        if self._sslobj_internal is not None:
            while True:
                try:
                    self._sslobj_internal.unwrap()
                except SSLWantReadError:
                    self._flush_outgoing()
                    if (
                        self._transport.gettimeout() == 0
                        or self._sslobj_internal.pending()
                        or self._sslobj_internal._pending_plaintext
                    ):
                        raise
                    self._pull_incoming()
                else:
                    self._flush_outgoing()
                    break
            self._sslobj_internal = None
        return self._transport

    def shutdown(self, how: int) -> None:
        self._transport.shutdown(how)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._sslobj_internal is not None:
            try:
                self._sslobj_internal.unwrap()
                self._flush_outgoing()
            except Exception:
                pass
            self._sslobj_internal = None
        self._transport.close()

    def get_verified_chain(self) -> list[bytes]:
        if self._sslobj_internal is None:
            return []
        return self._sslobj_internal.get_verified_chain()

    def get_unverified_chain(self) -> list[bytes]:
        if self._sslobj_internal is None:
            return []
        return self._sslobj_internal.get_unverified_chain()

    @property
    def context(self) -> TLSContext:
        return self._rtls_context

    @property
    def server_side(self) -> bool:
        return self._server_side

    @property
    def server_hostname(self) -> str | None:
        return self._server_hostname

    @property
    def session(self) -> Any:
        if self._sslobj_internal is None:
            return self._pending_session
        return self._sslobj_internal.session

    @session.setter
    def session(self, value: Any) -> None:
        _validate_session_type(value)
        if self._server_side:
            raise ValueError("Cannot set session for server-side SSLSocket.")
        if self._sslobj_internal is None:
            self._pending_session = value
        else:
            self._sslobj_internal.session = value

    @property
    def session_reused(self) -> bool | None:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal.session_reused

    @property
    def _sslobj(self) -> Any:
        if self._sslobj_internal is None:
            return None
        return self._sslobj_internal._sslobj

    @property
    def sslobj(self) -> _TLSConnection | None:
        return self._sslobj_internal

    def __getattr__(self, name: str) -> Any:
        return getattr(self._transport, name)

    def __enter__(self) -> TLSStreamSocket:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
