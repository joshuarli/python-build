Upstream source: CPython 3.15.1, `Lib/ssl.py`, from
[`Python-3.15.1.tar.xz`](https://www.python.org/ftp/python/3.15.1/Python-3.15.1.tar.xz),
SHA-256 `673ae7232d84c894729882c8257d300ef2d26523911bfd3917ec8ce7f526f99b`,
size 35,789,408 bytes.
Origin: project-authored. No third-party Python package code is copied.
License: Python Software Foundation License Version 2.

Explanation: `SSLContext.load_default_certs()` first loads OpenSSL's configured
paths. It loads the installed Mozilla bundle only when neither `SSL_CERT_FILE`
nor `SSL_CERT_DIR` is present, `PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE` is not `1`,
and `get_default_verify_paths()` reports neither a cafile nor a capath. An
existing empty cafile and an existing hashed capath both count as configured
host sources. An explicitly present SSL path variable suppresses the fallback
even when its value is empty or invalid, including under `-E` and `-I`.

The bundle comes from the source-locked `certifi-ca` input and is installed at
package time. The runtime does not download or update it.

Scope: All current macOS and Linux musl targets. The bundle path follows the
installation tree.

Applicability check: applies with zero fuzz to CPython 3.15.1 after the existing
source patches are applied.

Regression test: `tests/test_ssl_fallback_patch.py` covers missing and
configured defaults, an explicit file, a hashed directory, empty and invalid
SSL path values, the opt-out, and `-E` and `-I` startup. The existing
`buildsys.standalone_compat.py::_fallback_ca_check` covers a local TLS chain
with the fallback, an explicit `SSL_CERT_FILE`, and the opt-out. The relocated
sysconfig probe checks fallback loading after moving the installation tree.
