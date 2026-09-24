Upstream source: CPython 3.14.6, `Lib/ssl.py`.
Origin: project-authored; no third-party Python package code is copied.
License: Python Software Foundation License Version 2.

Explanation: Minimal images can have an OpenSSL library but no configured
trusted CA roots. Keep OpenSSL's normal default-path loading. Only if that
loads zero CA certificates, and the caller has not set `SSL_CERT_FILE`,
`SSL_CERT_DIR`, or `PYTHON_BUILD_NO_DEFAULT_CA_BUNDLE=1`, load the locked
Mozilla bundle from the installed standard-library directory. The bundle is
installed by `buildsys.ca_bundle` from the source-locked `certifi-ca` input;
it is not updated at runtime. Its license is shipped beside the bundle.

Scope: All current macOS and Linux musl targets. The runtime fallback follows
the installation tree, and never adds Mozilla roots when a configured
platform or user trust store already contains roots.

Applicability check: applies without fuzz to the locked CPython 3.14.6
`Lib/ssl.py` source.

Regression test: `buildsys.standalone_compat.py::_fallback_ca_check` verifies
a local TLS chain with the fallback, verifies the same chain through an
explicit `SSL_CERT_FILE`, and checks the opt-out. The relocated sysconfig
probe also loads the installed bundle after moving the full tree.
