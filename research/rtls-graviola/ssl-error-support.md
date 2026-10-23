# TLS error behavior

Generated SSL errors preserve CPython's `(numeric_code, message)` arguments
and `errno`. Their string form is the message alone. Manually constructed
errors retain caller arguments and leave `library` and `reason` unset.
The reference reports X509 code 113 with reason `INVALID_DIRECTORY` for an
empty CA directory. The v7d candidate still omits that numeric error; this
discrepancy remains a qualification failure.

Rustls peer alerts use code `SSL_ERROR_SSL` and expose OpenSSL-compatible
reason names such as `SSLV3_ALERT_BAD_CERTIFICATE`. Certificate verification
keeps its mapped verify code and verify message, including CRL signature failure
code 8, CRL not-yet-valid code 11, unknown revocation status code 3, and expired
CRL code 12.
