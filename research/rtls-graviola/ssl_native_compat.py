import importlib

_RUSTLS_BACKEND = True
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

    with open(path, "rb") as source:
        pem = source.read()
    match = re.search(
        rb"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
        pem,
        re.DOTALL,
    )
    if match is None:
        raise __getattr__("SSLError")("No certificate found")
    der = base64.b64decode(b"".join(match[1].split()), validate=True)
    return _rustls.parse_certificate_dict(der)


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
