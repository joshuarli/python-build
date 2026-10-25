from __future__ import annotations

from ._immutable import ImmutableType

from typing import Any

from ._stdlib import ssl as _ssl


class SSLError(_ssl.SSLError, metaclass=ImmutableType):
    """Base SSL error, analogous to ssl.SSLError."""

    library: str | None
    reason: str | None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        library = kwargs.pop("library", None)
        reason = kwargs.pop("reason", None)
        super().__init__(*args, **kwargs)
        self.library = library
        self.reason = reason

    def __str__(self) -> str:
        if len(self.args) == 2 and isinstance(self.args[0], int):
            return str(self.args[1])
        return str(self.args)


class SSLZeroReturnError(SSLError, _ssl.SSLZeroReturnError):
    """SSL connection has been closed cleanly."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class SSLWantReadError(SSLError, _ssl.SSLWantReadError):
    """Non-blocking SSL socket needs to read more data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class SSLWantWriteError(SSLError, _ssl.SSLWantWriteError):
    """Non-blocking SSL socket needs to write data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class SSLSyscallError(SSLError, _ssl.SSLSyscallError):
    """System call error during SSL operation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class SSLEOFError(SSLError, _ssl.SSLEOFError):
    """SSL connection terminated abruptly (EOF without close_notify)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)


class SSLCertVerificationError(SSLError, _ssl.SSLCertVerificationError):
    """Certificate verification failed."""

    verify_code: int
    verify_message: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        verify_code = kwargs.pop("verify_code", None)
        verify_message = kwargs.pop("verify_message", None)
        if verify_code is None and verify_message is None:
            super().__init__(*args, **kwargs)
            return
        message = str(
            args[1] if len(args) > 1 and isinstance(args[0], int) else args[0]
        )
        self.verify_message = verify_message if verify_message is not None else message
        if verify_code is not None:
            self.verify_code = verify_code
        kwargs.setdefault("library", "SSL")
        kwargs.setdefault("reason", "CERTIFICATE_VERIFY_FAILED")
        details = f": {self.verify_message}" if self.verify_message else ""
        normalized_message = (
            f"[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed{details}"
        )
        super().__init__(
            1,
            normalized_message,
            **kwargs,
        )


# Alias used by CPython
CertificateError = SSLCertVerificationError
