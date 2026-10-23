import importlib

from _ssl_metadata import _SSL_CONSTANTS

globals().update(_SSL_CONSTANTS)

_RUSTLS_BACKEND = True
_OPENSSL_API_VERSION = (0, 0, 0, 0, 0)
ENCODING_PEM = 1
ENCODING_DER = 2
PROTO_MINIMUM_SUPPORTED = -2
PROTO_MAXIMUM_SUPPORTED = -1
PROTO_SSLv3 = 0x0300
PROTO_TLSv1 = 0x0301
PROTO_TLSv1_1 = 0x0302
PROTO_TLSv1_2 = 0x0303
PROTO_TLSv1_3 = 0x0304


def _test_decode_cert(path):
    import base64
    import re
    from rtls import _rustls

    try:
        with open(path, "rb") as source:
            pem = source.read()
    except OSError as error:
        raise __getattr__("SSLError")("Can't open file") from error
    match = re.search(
        rb"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
        pem,
        re.DOTALL,
    )
    if match is None:
        raise __getattr__("SSLError")("Error decoding PEM-encoded file")
    try:
        der = base64.b64decode(b"".join(match[1].split()), validate=True)
        certificate = _rustls.parse_certificate_dict(der)
    except ValueError as error:
        raise __getattr__("SSLError")("Error decoding PEM-encoded file") from error
    return certificate


def __getattr__(name):
    if name == "Certificate":
        from rtls._certificate import TLSCertificate

        return TLSCertificate
    if name.startswith("__"):
        raise AttributeError(name)
    module = importlib.import_module("ssl")
    aliases = {"_SSLContext": "SSLContext", "_SSLSocket": "SSLSocket"}
    try:
        return getattr(module, aliases.get(name, name))
    except AttributeError:
        raise AttributeError(f"module '_ssl' has no attribute {name!r}") from None
