"""Differential TLS checks: run one corpus under two interpreters and diff.

    differential_tls.py corpus DIR            build the corpus with the openssl CLI
    differential_tls.py run DIR OUT.json      outcomes under the running interpreter
    differential_tls.py diff A.json B.json    list every case whose outcome differs

`run` records, for each generated leaf certificate and hostname, whether an
in-memory TLS handshake succeeds, plus the outcome of loading every mutated
PEM and DER variant of the CA as a trust anchor. Run it under the OpenSSL
reference interpreter and the product interpreter, then diff the two files.
"""

from __future__ import annotations

import base64
import json
import random
import re
import shutil
import ssl
import subprocess
import sys
from pathlib import Path

LEAVES = {
    "exact": (None, "DNS:example.com"),
    "upper": (None, "DNS:EXAMPLE.COM"),
    "trailing_dot": (None, "DNS:example.com."),
    "wildcard": (None, "DNS:*.example.com"),
    "wildcard_partial": (None, "DNS:f*.example.com"),
    "wildcard_tld": (None, "DNS:*.com"),
    "wildcard_double": (None, "DNS:*.*.example.com"),
    "idna": (None, "DNS:xn--bcher-kva.example"),
    "ip4": (None, "IP:192.0.2.1"),
    "ip6": (None, "IP:2001:db8::1"),
    "ip_text_in_dns": (None, "DNS:192.0.2.1"),
    "cn_only": ("example.com", None),
    "cn_and_other_san": ("example.com", "DNS:other.example"),
    "multiple": (None, "DNS:a.example,DNS:b.example,IP:192.0.2.9"),
}
HOSTS = [
    "example.com", "EXAMPLE.com", "example.com.", "www.example.com",
    "a.b.example.com", "foo.example.com", "f.example.com", "fa.example.com",
    "com", "xn--bcher-kva.example", "bücher.example", "192.0.2.1", "2001:db8::1",
    "a.example", "b.example", "192.0.2.9", "other.example",
]


CHAIN_CASES = {
    "valid": {},
    "expired": {"not_before": "20200101000000Z", "not_after": "20200102000000Z"},
    "not_yet_valid": {"not_before": "20990101000000Z", "not_after": "20990102000000Z"},
    "eku_client_only": {"eku": "clientAuth"},
    "eku_absent": {"eku": None},
    "eku_any": {"eku": "anyExtendedKeyUsage"},
    "ku_key_agreement_only": {"ku": "keyAgreement"},
    "ku_absent": {"ku": None},
    "no_basic_constraints": {"bc": None},
    "leaf_marked_ca": {"bc": "critical,CA:TRUE"},
    "no_aki": {"aki": None},
    "ecdsa_p256": {"key": "ec:prime256v1"},
    "rsa_1024": {"key": "rsa:1024"},
    "via_intermediate": {"issuer": "int"},
    "via_intermediate_not_sent": {"issuer": "int", "send_intermediate": False},
    "via_intermediate_pathlen_exceeded": {"issuer": "int2"},
    "self_signed_leaf": {"issuer": "self"},
}
CHAIN_HOST = "example.com"


def _openssl(*arguments: str) -> None:
    subprocess.run(["openssl", *arguments], check=True, capture_output=True)


def build_corpus(directory: Path) -> None:
    if directory.exists():
        raise SystemExit(f"{directory} already exists")
    directory.mkdir(parents=True)
    _openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(directory / "ca.key"),
             "-out", str(directory / "ca.pem"), "-subj", "/CN=Differential CA", "-days", "30",
             "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign",
             "-addext", "subjectKeyIdentifier=hash")
    for name, (common_name, san) in LEAVES.items():
        key, csr, pem = (directory / f"{name}.{kind}" for kind in ("key", "csr", "pem"))
        _openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(csr),
                 "-subj", f"/CN={common_name or 'leaf.invalid'}")
        extensions = directory / f"{name}.ext"
        lines = ["basicConstraints=critical,CA:FALSE", "keyUsage=critical,digitalSignature",
                 "extendedKeyUsage=serverAuth", "subjectKeyIdentifier=hash",
                 "authorityKeyIdentifier=keyid"]
        if san:
            lines.append(f"subjectAltName={san}")
        extensions.write_text("\n".join(lines) + "\n")
        _openssl("x509", "-req", "-in", str(csr), "-CA", str(directory / "ca.pem"),
                 "-CAkey", str(directory / "ca.key"), "-CAcreateserial", "-out", str(pem),
                 "-days", "30", "-extfile", str(extensions))
    shutil.copyfile(directory / "ca.pem", directory / "ca-original.pem")
    _build_chain_corpus(directory)


def _issue(directory: Path, name: str, subject: str, extensions: list[str], issuer: str | None,
           key: str = "rsa:2048", validity: tuple[str, str] | None = None) -> None:
    key_path, csr, pem = (directory / f"{name}.{kind}" for kind in ("key", "csr", "pem"))
    key_arguments = (["-newkey", "EC", "-pkeyopt", f"ec_paramgen_curve:{key.split(':')[1]}"]
                     if key.startswith("ec:") else ["-newkey", key])
    _openssl("req", *key_arguments, "-nodes", "-keyout", str(key_path), "-out", str(csr),
             "-subj", f"/CN={subject}")
    extension_file = directory / f"{name}.ext"
    extension_file.write_text("\n".join(extensions) + "\n")
    command = ["x509", "-req", "-in", str(csr), "-out", str(pem), "-extfile", str(extension_file)]
    if validity:
        command += ["-not_before", validity[0], "-not_after", validity[1]]
    else:
        command += ["-days", "30"]
    if issuer is None:
        command += ["-signkey", str(key_path)]
    else:
        command += ["-CA", str(directory / f"{issuer}.pem"), "-CAkey", str(directory / f"{issuer}.key"),
                    "-CAcreateserial"]
    _openssl(*command)


def _build_chain_corpus(directory: Path) -> None:
    ca_extensions = ["basicConstraints=critical,CA:TRUE,pathlen:0", "keyUsage=critical,keyCertSign,cRLSign",
                     "subjectKeyIdentifier=hash", "authorityKeyIdentifier=keyid"]
    _issue(directory, "int", "Differential Intermediate", ca_extensions, "ca")
    sub_extensions = ["basicConstraints=critical,CA:TRUE", "keyUsage=critical,keyCertSign,cRLSign",
                      "subjectKeyIdentifier=hash", "authorityKeyIdentifier=keyid"]
    _issue(directory, "int2", "Differential Sub Intermediate", sub_extensions, "int")
    for name, options in CHAIN_CASES.items():
        extensions = []
        basic = options.get("bc", "critical,CA:FALSE")
        if basic:
            extensions.append(f"basicConstraints={basic}")
        usage = options.get("ku", "critical,digitalSignature")
        if usage:
            extensions.append(f"keyUsage={usage}")
        if options.get("eku", "serverAuth"):
            extensions.append(f"extendedKeyUsage={options.get('eku', 'serverAuth')}")
        extensions.append("subjectKeyIdentifier=hash")
        if options.get("aki", "keyid"):
            extensions.append("authorityKeyIdentifier=keyid")
        extensions.append(f"subjectAltName=DNS:{CHAIN_HOST}")
        issuer = options.get("issuer", "ca")
        _issue(directory, f"chain_{name}", CHAIN_HOST, extensions, None if issuer == "self" else issuer,
               key=options.get("key", "rsa:2048"), validity=(
                   (options["not_before"], options["not_after"]) if "not_before" in options else None))


def _mutations(pem: str) -> dict[str, str]:
    random_source = random.Random(20261030)
    lines = pem.strip().splitlines()
    body = "".join(lines[1:-1])
    raw = base64.b64decode(body)
    cases = {
        "valid": pem,
        "empty": "",
        "header_only": lines[0] + "\n",
        "missing_footer": "\n".join(lines[:-1]) + "\n",
        "wrong_label": pem.replace("CERTIFICATE", "TRUSTED CERTIFICATE"),
        "crlf": pem.replace("\n", "\r\n"),
        "leading_text": "junk before\n" + pem,
        "trailing_text": pem + "junk after\n",
        "two_copies": pem + pem,
        "extra_blank_lines": "\n\n".join(lines) + "\n",
        "spaces_in_body": lines[0] + "\n" + " ".join(lines[1:-1]) + "\n" + lines[-1] + "\n",
        "bad_base64_char": pem.replace(lines[1][:4], "!!!!", 1),
        "truncated_base64": "\n".join([lines[0], *lines[1:-2], lines[-2][:-3], lines[-1]]) + "\n",
    }
    for cut in (1, 4, 10, 100, len(raw) // 2, len(raw) - 1):
        cases[f"der_truncated_{cut}"] = _pem(raw[:cut])
    for index in range(40):
        mutated = bytearray(raw)
        mutated[random_source.randrange(len(mutated))] ^= 1 << random_source.randrange(8)
        cases[f"der_bitflip_{index}"] = _pem(bytes(mutated))
    return cases


def _pem(der: bytes) -> str:
    return ssl.DER_cert_to_PEM_cert(der)


def _outcome(function) -> str:
    try:
        function()
    except ssl.SSLCertVerificationError as error:
        return f"SSLCertVerificationError:{error.verify_code}"
    except Exception as error:  # noqa: BLE001
        return type(error).__name__
    return "ok"


def _handshake(directory: Path, leaf: str, hostname: str, *, trust: str = "ca", chain: tuple[str, ...] = ()) -> str:
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    certificates = directory / f"{leaf}.pem"
    if chain:
        certificates = directory / f"{leaf}.bundle.pem"
        certificates.write_text("".join((directory / f"{name}.pem").read_text() for name in (leaf, *chain)))
    try:
        server.load_cert_chain(certificates, directory / f"{leaf}.key")
    except Exception as error:  # noqa: BLE001
        return f"server_load:{type(error).__name__}"
    client = ssl.create_default_context(cafile=str(directory / f"{trust}.pem"))
    client_in, client_out, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
    try:
        client_side = client.wrap_bio(client_in, client_out, server_hostname=hostname)
    except Exception as error:  # noqa: BLE001
        return f"wrap:{type(error).__name__}"
    server_side = server.wrap_bio(server_in, server_out, server_side=True)
    finished = {"client": False, "server": False}
    for _ in range(40):
        for name, side in (("client", client_side), ("server", server_side)):
            if finished[name]:
                continue
            try:
                side.do_handshake()
                finished[name] = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            except ssl.SSLCertVerificationError as error:
                return f"{name}:SSLCertVerificationError:{error.verify_code}"
            except Exception as error:  # noqa: BLE001
                return f"{name}:{type(error).__name__}"
        pending = client_out.read()
        if pending:
            server_in.write(pending)
        pending = server_out.read()
        if pending:
            client_in.write(pending)
        if all(finished.values()):
            return "ok"
    return "incomplete"


def run(directory: Path, output: Path) -> None:
    results: dict[str, str] = {}
    for leaf in LEAVES:
        for hostname in HOSTS:
            results[f"handshake {leaf} -> {hostname}"] = _handshake(directory, leaf, hostname)
    for name, options in CHAIN_CASES.items():
        issuer = options.get("issuer", "ca")
        chain = {"int": ("int",), "int2": ("int2", "int")}.get(issuer, ())
        if issuer == "int" and options.get("send_intermediate") is False:
            chain = ()
        trust = "chain_self_signed_leaf" if issuer == "self" else "ca"
        results[f"chain {name}"] = _handshake(
            directory, f"chain_{name}", CHAIN_HOST, trust=trust, chain=chain)
    ca_pem = (directory / "ca-original.pem").read_text()
    for label, pem in _mutations(ca_pem).items():
        def load(pem=pem):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cadata=pem)
            if not context.cert_store_stats()["x509_ca"]:
                raise ValueError("no certificate loaded")
        results[f"load pem {label}"] = _outcome(load)
    for label, pem in _mutations(ca_pem).items():
        results[f"pem_to_der {label}"] = _outcome(lambda pem=pem: ssl.PEM_cert_to_DER_cert(pem))
    output.write_text(json.dumps({"backend": ssl.OPENSSL_VERSION, "results": results}, indent=2, sort_keys=True) + "\n")


def diff(first: Path, second: Path) -> int:
    a, b = (json.loads(path.read_text()) for path in (first, second))
    names = sorted(a["results"].keys() | b["results"].keys())
    differing = [(name, a["results"].get(name), b["results"].get(name)) for name in names
                 if a["results"].get(name) != b["results"].get(name)]
    print(f"{len(names)} cases; {len(differing)} differ ({a['backend']} vs {b['backend']})")
    for name, left, right in differing:
        print(f"  {name}: {left} | {right}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "corpus":
        build_corpus(Path(argv[2]))
        return 0
    if len(argv) == 4 and argv[1] == "run":
        run(Path(argv[2]), Path(argv[3]))
        return 0
    if len(argv) == 4 and argv[1] == "diff":
        return diff(Path(argv[2]), Path(argv[3]))
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
