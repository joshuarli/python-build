import os

from rtls import *
from rtls import __all__, __version__
from rtls import SSLContext as _RTLS_SSLContext


_PYTHON_BUILD_DEFAULT_CA_BUNDLE = os.path.join(
    os.path.dirname(__file__), "python-build-cacert.pem"
)
_PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE = "PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE"


class SSLContext(_RTLS_SSLContext):
    def load_default_certs(self, purpose=Purpose.SERVER_AUTH):
        super().load_default_certs(purpose)
        default_paths = get_default_verify_paths()
        explicit_path = any(
            name in os.environ
            for name in (
                default_paths.openssl_cafile_env,
                default_paths.openssl_capath_env,
            )
        )
        if (
            not explicit_path
            and default_paths.cafile is None
            and default_paths.capath is None
            and os.environ.get(_PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE) != "1"
        ):
            self.load_verify_locations(cafile=_PYTHON_BUILD_DEFAULT_CA_BUNDLE)


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
        context.verify_flags |= (
            VERIFY_X509_PARTIAL_CHAIN
            | VERIFY_X509_STRICT
            | VERIFY_X509_TRUSTED_FIRST
        )
    if cafile or capath or cadata:
        context.load_verify_locations(cafile, capath, cadata)
    else:
        context.load_default_certs(purpose)
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
    context.check_hostname = False
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

from _ssl_metadata import _TLSContentType, _TLSAlertType, _TLSMessageType
import _ssl
from rtls import _constants

HAS_PSK_TLS13 = False
_PROTOCOL_NAMES = {
    value: name
    for name, value in vars(_constants).items()
    if name.startswith("PROTOCOL_") and name != "PROTOCOL_SSLv23"
}
