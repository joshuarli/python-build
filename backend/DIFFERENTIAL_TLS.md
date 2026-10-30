# Differential TLS checks

`differential_tls.py` runs one generated corpus under two interpreters and
diffs the outcomes: 14 leaf certificates (exact, upper case, trailing dot,
wildcards including partial, TLD and double, IDNA, IPv4, IPv6, an IP written as
a DNS name, CN-only, CN with a different SAN, several SANs) against 17 hostnames
in an in-memory handshake, and 53 mutated PEM variants of the CA (truncations,
bit flips, wrong labels, CRLF, blank lines, text around the block) loaded as a
trust anchor and converted with `PEM_cert_to_DER_cert`.

```sh
python3 backend/differential_tls.py corpus .work/tmp/dtls/corpus
<openssl-reference-python> -I backend/differential_tls.py run .work/tmp/dtls/corpus ref.json
<product-python> -I backend/differential_tls.py run .work/tmp/dtls/corpus prod.json
python3 backend/differential_tls.py diff ref.json prod.json
```

## Result, 2026-10-30

Reference OpenSSL 3.5.7 against the macOS product build at `38faf1d`: 356 cases,
305 agree, 51 differ.

Handshakes: 195 of 238 agree, including every wildcard, IDNA, IP SAN, CN-only,
CN-fallback, and multi-SAN case. The 43 differences:

- 39 are rejections by both with a different `verify_code`: an IP address
  mismatch is reported as 62 (hostname mismatch) instead of OpenSSL's 64.
- 4 are trailing-dot handling. The product treats `example.com.` as
  `example.com` (3 cases accept where OpenSSL rejects) and does not match a
  certificate whose SAN itself ends in a dot (1 case rejects where OpenSSL
  accepts). Both are the same host name; neither admits a different host.

No hostname or IP case is accepted by the product that names a different host.

PEM and DER loading, 8 differences, all unresolved and none a verification
bypass, since a trust anchor contributes only its subject and key:

- Blank lines inside the base64 body load in the product and fail in OpenSSL.
- Five single-bit flips of the CA DER load in OpenSSL and fail in the product;
  one flip loads in the product and fails in OpenSSL.
- Loading an empty `cadata` raises `ValueError` in OpenSSL and `SSLError` in
  the product.
