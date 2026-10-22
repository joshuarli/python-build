import os
from pathlib import Path

from rtls import *
from rtls import __all__, __version__


def create_default_context(
    purpose=Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None
):
    if not hasattr(purpose, "oid"):
        raise TypeError(purpose)
    context = SSLContext(
        PROTOCOL_TLS_CLIENT
        if purpose == Purpose.SERVER_AUTH
        else PROTOCOL_TLS_SERVER
    )
    if purpose == Purpose.SERVER_AUTH:
        context.verify_mode = CERT_REQUIRED
        context.check_hostname = True
        context.verify_flags |= VERIFY_X509_PARTIAL_CHAIN | VERIFY_X509_STRICT
    if cafile or capath or cadata:
        context.load_verify_locations(cafile, capath, cadata)
    elif "SSL_CERT_FILE" in os.environ or "SSL_CERT_DIR" in os.environ:
        cafile = os.environ.get("SSL_CERT_FILE")
        capath = os.environ.get("SSL_CERT_DIR")
        if cafile and os.path.isfile(cafile):
            context.load_verify_locations(cafile=cafile)
        if capath and os.path.isdir(capath):
            context.load_verify_locations(capath=capath)
    elif os.environ.get("PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE") != "1":
        bundle = Path(__file__).with_name("python-build-cacert.pem")
        context.load_verify_locations(cafile=str(bundle))
    return context


def _create_unverified_context(
    protocol=None,
    *,
    cert_reqs=CERT_NONE,
    check_hostname=False,
    purpose=Purpose.SERVER_AUTH,
    certfile=None,
    keyfile=None,
    cafile=None,
    capath=None,
    cadata=None,
):
    protocol = protocol or PROTOCOL_TLS_CLIENT
    context = SSLContext(protocol)
    if cert_reqs is not None:
        context.verify_mode = cert_reqs
    context.check_hostname = check_hostname
    if cafile or capath or cadata:
        context.load_verify_locations(cafile, capath, cadata)
    if certfile:
        context.load_cert_chain(certfile, keyfile)
    return context


_create_stdlib_context = _create_unverified_context
_create_default_https_context = create_default_context
