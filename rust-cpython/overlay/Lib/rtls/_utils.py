from __future__ import annotations

import base64
import calendar
import ctypes
import operator
import os
import socket
from typing import Any

from ._constants import (
    CERT_REQUIRED,
    PROTOCOL_TLS_CLIENT,
    DefaultVerifyPaths,
    Purpose,
    _get_default_verify_paths,
)
from ._exceptions import SSLCertVerificationError, SSLError

_C_INT_BITS = ctypes.sizeof(ctypes.c_int) * 8
_C_INT_MIN = -(1 << (_C_INT_BITS - 1))
_C_INT_MAX = (1 << (_C_INT_BITS - 1)) - 1

PEM_HEADER = "-----BEGIN CERTIFICATE-----"
PEM_FOOTER = "-----END CERTIFICATE-----"


def create_default_context(
    purpose: Any = Purpose.SERVER_AUTH,
    *,
    cafile: str | None = None,
    capath: str | None = None,
    cadata: str | bytes | None = None,
):
    """Create an SSLContext with secure default settings.

    Same as ssl.create_default_context(): loads system CAs, enables cert
    verification and hostname checking.
    """
    # Import here to avoid circular
    from ._context import TLSContext

    if hasattr(purpose, "oid") and purpose.oid == "1.3.6.1.5.5.7.3.1":
        # SERVER_AUTH: we are a client authenticating a server
        context = TLSContext(PROTOCOL_TLS_CLIENT)
        context.verify_mode = CERT_REQUIRED
        context.check_hostname = True
    else:
        # CLIENT_AUTH: we are a server authenticating a client
        from ._constants import PROTOCOL_TLS_SERVER

        context = TLSContext(PROTOCOL_TLS_SERVER)

    if cafile or capath or cadata:
        context.load_verify_locations(cafile, capath, cadata)
    else:
        context.load_default_certs()

    return context


def cert_time_to_seconds(cert_time: str) -> int:
    """Convert a certificate time string to seconds since epoch.

    The input format is the OpenSSL time format:
    "Jan  5 09:34:43 2018 GMT"
    """
    import time as _time

    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    time_format = " %d %H:%M:%S %Y GMT"
    try:
        month_number = months.index(cert_time[:3].title()) + 1
    except ValueError:
        raise ValueError(
            f'time data {cert_time!r} does not match format "%b{time_format}"'
        ) from None

    parsed = _time.strptime(cert_time[3:], time_format)
    return calendar.timegm((parsed[0], month_number) + parsed[2:6])


def DER_cert_to_PEM_cert(der_cert_bytes: bytes) -> str:
    """Convert a DER-encoded certificate to PEM format."""
    f = str(base64.standard_b64encode(der_cert_bytes), "ASCII", "strict")
    ss = [PEM_HEADER]
    ss += [f[i : i + 64] for i in range(0, len(f), 64)]
    ss.append(PEM_FOOTER + "\n")
    return "\n".join(ss)


def PEM_cert_to_DER_cert(pem_cert_string: str) -> bytes:
    """Convert a PEM-encoded certificate to DER format."""
    # Strip header/footer and whitespace
    if not pem_cert_string.startswith(PEM_HEADER):
        raise ValueError(  # Defensive: stdlib cpy
            f"Invalid PEM encoding; must start with {PEM_HEADER}"
        )
    if not pem_cert_string.strip().endswith(PEM_FOOTER):
        raise ValueError(  # Defensive: stdlib cpy
            f"Invalid PEM encoding; must end with {PEM_FOOTER}"
        )
    d = pem_cert_string.strip()[len(PEM_HEADER) : -len(PEM_FOOTER)]
    return base64.decodebytes(d.encode("ASCII", "strict"))


def get_server_certificate(
    addr: tuple[str, int],
    ssl_version: int = PROTOCOL_TLS_CLIENT,
    ca_certs: str | None = None,
    timeout: float = 10.0,
) -> str:
    """Retrieve the certificate from a TLS server as a PEM string."""
    from ._constants import CERT_NONE
    from ._context import TLSContext

    host, port = addr
    context = TLSContext(PROTOCOL_TLS_CLIENT)
    # Match CPython behavior: always disable hostname check in get_server_certificate.
    # When ca_certs is provided, verify the cert chain but NOT the hostname.
    context.check_hostname = False

    if ca_certs:
        context.load_verify_locations(ca_certs)
        context.verify_mode = CERT_REQUIRED
    else:
        context.verify_mode = CERT_NONE

    with socket.create_connection(addr, timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as sslsock:
            der = sslsock.getpeercert(binary_form=True)
            if der is None:
                raise ValueError("No certificate received from server")
            return DER_cert_to_PEM_cert(der)


def get_default_verify_paths() -> DefaultVerifyPaths:
    """Return the default paths used for certificate verification."""
    return _get_default_verify_paths()


def match_hostname(cert: dict, hostname: str) -> None:
    """Verify that *cert* (in decoded format as returned by
    SSLSocket.getpeercert()) matches the *hostname*.

    .. deprecated:: 3.7
        Use SSLContext.check_hostname instead.
    """
    import warnings

    warnings.warn(
        "ssl.match_hostname() is deprecated, use SSLContext.check_hostname",
        DeprecationWarning,
        stacklevel=2,
    )

    if not cert:
        raise SSLCertVerificationError(
            "empty or no certificate",
            verify_code=1,
            verify_message="empty or no certificate",
        )

    san = cert.get("subjectAltName", ())
    dns_names = [v for k, v in san if k == "DNS"]

    if dns_names:
        if not _hostname_matches(hostname, dns_names):
            names = ", ".join(map(repr, dns_names))
            raise SSLCertVerificationError(
                f"hostname {hostname!r} doesn't match {names}",
                verify_code=1,
                verify_message=(f"hostname {hostname!r} doesn't match certificate"),
            )
    else:
        # Fall back to CN
        subject = cert.get("subject", ())
        for rdn in subject:
            for key, value in rdn:
                if key == "commonName":
                    if _hostname_matches(hostname, [value]):
                        return
        raise SSLCertVerificationError(
            f"hostname {hostname!r} doesn't match certificate",
            verify_code=1,
            verify_message=f"hostname {hostname!r} doesn't match certificate",
        )


def _hostname_matches(hostname: str, patterns: list[str]) -> bool:
    """Check if hostname matches any of the patterns (with wildcard support)."""
    for pattern in patterns:
        if _match_hostname_pattern(hostname, pattern):
            return True
    return False


def _match_hostname_pattern(hostname: str, pattern: str) -> bool:
    """Match a hostname against a single pattern (supports wildcards)."""
    hostname = hostname.lower()
    pattern = pattern.lower()

    if pattern == hostname:
        return True

    # Wildcard matching: *.example.com
    if pattern.startswith("*."):
        suffix = pattern[2:]
        # hostname must have at least one dot
        dot_idx = hostname.find(".")
        if dot_idx > 0 and hostname[dot_idx + 1 :] == suffix:
            return True

    return False


def RAND_bytes(num: int) -> bytes:
    """Generate num cryptographically secure random bytes."""
    num = operator.index(num)
    if num < _C_INT_MIN or num > _C_INT_MAX:
        raise OverflowError("Python int too large to convert to C int")
    if num < 0:
        raise ValueError("num must be positive")
    from . import _rustls

    return _rustls.rand_bytes(num)


def RAND_status() -> bool:
    """Return whether the selected provider can generate secure random bytes."""
    try:
        RAND_bytes(1)
    except SSLError:
        return False
    return True


def RAND_add(data: bytes, entropy: float) -> None:
    """Report that external entropy injection is unsupported."""
    raise NotImplementedError(
        "RAND_add entropy injection is unsupported by the selected random source"
    )
