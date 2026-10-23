# TLS error behavior

Generated SSL errors preserve CPython's `(numeric_code, message)` arguments
and `errno`. Their string form is the message alone. Manually constructed
errors retain caller arguments and leave `library` and `reason` unset.
An empty CA directory reports X509 code 113 with reason `INVALID_DIRECTORY`.
The server acceptor retains typed rustls failures through the shared exception
mapper, preserving `NO_SHARED_CIPHER` and peer-alert reason metadata.

Rustls peer alerts use code `SSL_ERROR_SSL` and expose OpenSSL-compatible
reason names such as `SSLV3_ALERT_BAD_CERTIFICATE`. Certificate verification
keeps its mapped verify code and verify message, including CRL signature failure
code 8, CRL not-yet-valid code 11, unknown revocation status code 3, and expired
CRL code 12.
