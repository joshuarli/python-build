from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

from buildsys.product_process import run_product_process


_TLS12_CIPHERS = frozenset(
    {
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-CHACHA20-POLY1305",
        "ECDHE-RSA-CHACHA20-POLY1305",
    }
)
_TLS13_CIPHERS = frozenset(
    {
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
    }
)
_GROUPS = frozenset(
    {"X25519MLKEM768", "x25519", "secp256r1", "secp384r1"}
)
_SIGNATURE_ALGORITHMS = frozenset(
    {
        "ecdsa_secp256r1_sha256",
        "ecdsa_secp384r1_sha384",
        "ed25519",
        "rsa_pss_rsae_sha512",
        "rsa_pss_rsae_sha384",
        "rsa_pss_rsae_sha256",
        "rsa_pkcs1_sha512",
        "rsa_pkcs1_sha384",
        "rsa_pkcs1_sha256",
    }
)
_REQUIRED_VERIFY_FLAGS = (
    "VERIFY_X509_STRICT",
    "VERIFY_X509_PARTIAL_CHAIN",
    "VERIFY_X509_TRUSTED_FIRST",
)
_LOCKED_CRATES = ("rustls", "rustls-graviola", "graviola")
_HASHLIB_SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

_RUNTIME_PROBE = r'''
import _hashlib
import _hashlib_graviola
import _ssl
import hashlib
import importlib.machinery
import json
from pathlib import Path
import ssl
import sys
import rtls
from rtls import _native


def module_path(module):
    return str(Path(module.__file__).resolve())


context = ssl.create_default_context()
native_library = Path(_native._library._name).resolve()
hashlib_provider = Path(_hashlib_graviola.__file__).resolve()
ciphers = [
    {"name": cipher["name"], "protocol": cipher["protocol"]}
    for cipher in context.get_ciphers()
]
verify_flag_values = {
    name: getattr(ssl, name, None)
    for name in (
        "VERIFY_X509_STRICT",
        "VERIFY_X509_PARTIAL_CHAIN",
        "VERIFY_X509_TRUSTED_FIRST",
    )
}
extension_suffixes = importlib.machinery.EXTENSION_SUFFIXES

print(
    json.dumps(
        {
            "executable": str(Path(sys.executable).resolve()),
            "prefix": str(Path(sys.prefix).resolve()),
            "backend": {
                "version": ssl.OPENSSL_VERSION,
                "version_info": list(ssl.OPENSSL_VERSION_INFO),
                "rustls_version": _native.rustls_version(),
                "provider": _native.crypto_provider(),
                "provider_version": _native.crypto_provider_version(),
                "graviola_version": _native.graviola_version(),
            },
            "modules": {
                "_ssl": {
                    "path": module_path(_ssl),
                    "source_loader": isinstance(
                        _ssl.__spec__.loader,
                        importlib.machinery.SourceFileLoader,
                    ),
                },
                "_hashlib": {
                    "path": module_path(_hashlib),
                    "source_loader": isinstance(
                        _hashlib.__spec__.loader,
                        importlib.machinery.SourceFileLoader,
                    ),
                    "used_by_hashlib": getattr(hashlib, "_hashlib", None)
                    is _hashlib,
                    "sha256_abc": hashlib.sha256(b"abc").hexdigest(),
                },
                "_hashlib_graviola": {
                    "path": str(hashlib_provider),
                    "extension_loader": isinstance(
                        _hashlib_graviola.__spec__.loader,
                        importlib.machinery.ExtensionFileLoader,
                    ),
                    "extension_suffix": any(
                        str(hashlib_provider).endswith(suffix)
                        for suffix in extension_suffixes
                    ),
                },
                "rtls_native": {
                    "path": str(native_library),
                    "extension_suffix": any(
                        str(native_library).endswith(suffix)
                        for suffix in extension_suffixes
                    ),
                },
                "ssl": module_path(ssl),
                "ssl_uses_ssl_shim": getattr(ssl, "_ssl", None) is _ssl,
                "rtls": module_path(rtls),
            },
            "protocols": {
                "TLSv1": bool(ssl.HAS_TLSv1),
                "TLSv1_1": bool(ssl.HAS_TLSv1_1),
                "TLSv1_2": bool(ssl.HAS_TLSv1_2),
                "TLSv1_3": bool(ssl.HAS_TLSv1_3),
            },
            "ciphers": ciphers,
            "groups": list(context.get_groups()),
            "signature_algorithms": list(ssl.get_sigalgs()),
            "default_client_context": {
                "is_ssl_context": isinstance(context, ssl.SSLContext),
                "verify_required": context.verify_mode == ssl.CERT_REQUIRED,
                "check_hostname": bool(context.check_hostname),
                "verify_flags": int(context.verify_flags),
                "verify_flag_values": verify_flag_values,
                "store_stats": context.cert_store_stats(),
            },
        },
        sort_keys=True,
    )
)
'''


def modern_replacement_for_legacy_check(check_name: str) -> str | None:
    if check_name == "ssl_capabilities":
        return "modern_tls_capabilities"
    return None


def _locked_versions(lock_path: Path) -> dict[str, str]:
    with lock_path.open("rb") as source:
        packages = tomllib.load(source).get("package")
    if not isinstance(packages, list):
        raise ValueError("RTLS Cargo.lock has no package list")
    versions: dict[str, str] = {}
    for crate_name in _LOCKED_CRATES:
        matches = [
            package.get("version")
            for package in packages
            if isinstance(package, dict) and package.get("name") == crate_name
        ]
        if len(matches) != 1 or not isinstance(matches[0], str):
            raise ValueError(
                f"RTLS Cargo.lock does not identify one {crate_name} version"
            )
        versions[crate_name] = matches[0]
    return versions


def _rustls_version_info(version: str) -> list[int]:
    components = version.split(".")
    if len(components) != 3 or any(not part.isdecimal() for part in components):
        raise ValueError(f"RTLS Cargo.lock has an unsupported rustls version: {version}")
    return [int(part) for part in components] + [0, 0]


def _under_prefix(path: str, prefix: Path) -> bool:
    try:
        Path(path).resolve().relative_to(prefix)
    except (OSError, ValueError):
        return False
    return True


def _difference(expected: frozenset[str], actual: list[str]) -> tuple[list[str], list[str]]:
    actual_set = set(actual)
    return sorted(expected - actual_set), sorted(actual_set - expected)


def probe_modern_tls(
    candidate_python: str | Path,
    prefix: str | Path,
    prepared_rtls_source: str | Path,
    workdir: str | Path,
) -> dict[str, object]:
    candidate = Path(candidate_python).resolve()
    install = Path(prefix).resolve()
    source = Path(prepared_rtls_source).resolve()
    working_directory = Path(workdir).resolve()
    evidence: dict[str, object] = {}

    if not candidate.is_file() or not candidate.is_relative_to(install):
        return {
            "ok": False,
            "evidence": evidence,
            "error": "candidate Python must be an executable inside the prefix",
        }
    if not source.is_dir() or not working_directory.is_dir():
        return {
            "ok": False,
            "evidence": evidence,
            "error": "prepared RTLS source and probe workdir must exist",
        }

    try:
        locked_versions = _locked_versions(source / "rust" / "Cargo.lock")
        expected_version_info = _rustls_version_info(locked_versions["rustls"])
    except (OSError, UnicodeError, ValueError) as error:
        return {"ok": False, "evidence": evidence, "error": str(error)}

    evidence["locked_versions"] = locked_versions
    try:
        completed = run_product_process(
            [candidate, "-I", "-B", "-c", _RUNTIME_PROBE, str(install)],
            install,
            working_directory,
            timeout_seconds=20,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "evidence": evidence,
            "error": "modern TLS capability probe timed out",
        }
    except OSError as error:
        return {"ok": False, "evidence": evidence, "error": str(error)}

    if completed.returncode != 0:
        detail = completed.stderr.strip()[:2000]
        return {
            "ok": False,
            "evidence": evidence,
            "error": f"candidate capability probe exited {completed.returncode}: {detail}",
        }
    try:
        runtime = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return {
            "ok": False,
            "evidence": evidence,
            "error": f"candidate capability probe returned invalid JSON: {error}",
        }
    if not isinstance(runtime, dict):
        return {
            "ok": False,
            "evidence": evidence,
            "error": "candidate capability probe returned invalid evidence",
        }

    evidence["runtime"] = runtime
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(runtime.get("executable") == str(candidate), "runtime executable differs from candidate")
    require(runtime.get("prefix") == str(install), "runtime prefix differs from selected prefix")

    backend = runtime.get("backend")
    if not isinstance(backend, dict):
        backend = {}
    expected_identity = (
        f"Rustls {locked_versions['rustls']} — rustls-graviola "
        f"{locked_versions['rustls-graviola']}"
    )
    require(backend.get("rustls_version") == locked_versions["rustls"], "runtime rustls version differs from Cargo.lock")
    require(backend.get("provider") == "rustls-graviola", "runtime TLS provider is not rustls-graviola")
    require(
        backend.get("provider_version") == locked_versions["rustls-graviola"],
        "runtime provider version differs from Cargo.lock",
    )
    require(backend.get("graviola_version") == locked_versions["graviola"], "runtime Graviola version differs from Cargo.lock")
    require(backend.get("version") == expected_identity, "ssl backend identity does not match the native provider and Cargo.lock")
    require(backend.get("version_info") == expected_version_info, "ssl version tuple does not match the locked rustls version")

    modules = runtime.get("modules")
    if not isinstance(modules, dict):
        modules = {}
    ssl_shim = modules.get("_ssl")
    hashlib_shim = modules.get("_hashlib")
    hashlib_provider = modules.get("_hashlib_graviola")
    tls_native = modules.get("rtls_native")
    for label, module in (("_ssl", ssl_shim), ("_hashlib", hashlib_shim)):
        if not isinstance(module, dict):
            module = {}
        require(
            module.get("source_loader") is True
            and isinstance(module.get("path"), str)
            and module["path"].endswith(".py")
            and _under_prefix(module["path"], install),
            f"{label} is not a Python shim loaded from the selected prefix",
        )
    require(modules.get("ssl_uses_ssl_shim") is True, "ssl did not load the _ssl shim")
    for label in ("ssl", "rtls"):
        path = modules.get(label)
        require(
            isinstance(path, str)
            and path.endswith(".py")
            and _under_prefix(path, install),
            f"{label} is not loaded from the selected prefix",
        )
    if not isinstance(hashlib_shim, dict):
        hashlib_shim = {}
    require(hashlib_shim.get("used_by_hashlib") is True, "hashlib did not load the _hashlib shim")
    require(hashlib_shim.get("sha256_abc") == _HASHLIB_SHA256_ABC, "_hashlib shim failed its SHA-256 compatibility check")
    for label, module in (("_hashlib_graviola", hashlib_provider), ("RTLS native provider", tls_native)):
        if not isinstance(module, dict):
            module = {}
        require(
            module.get("extension_suffix") is True
            and isinstance(module.get("path"), str)
            and _under_prefix(module["path"], install),
            f"{label} is not a native extension loaded from the selected prefix",
        )
    if not isinstance(hashlib_provider, dict):
        hashlib_provider = {}
    require(hashlib_provider.get("extension_loader") is True, "_hashlib Graviola backend is not a native extension")

    protocols = runtime.get("protocols")
    if not isinstance(protocols, dict):
        protocols = {}
    require(protocols.get("TLSv1") is False, "TLS 1.0 is advertised")
    require(protocols.get("TLSv1_1") is False, "TLS 1.1 is advertised")
    require(protocols.get("TLSv1_2") is True, "TLS 1.2 is unavailable")
    require(protocols.get("TLSv1_3") is True, "TLS 1.3 is unavailable")

    cipher_rows = runtime.get("ciphers")
    if not isinstance(cipher_rows, list) or any(not isinstance(row, dict) for row in cipher_rows):
        cipher_rows = []
    cipher_names = [row.get("name") for row in cipher_rows if isinstance(row.get("name"), str)]
    require(len(cipher_names) == len(cipher_rows), "cipher suite entries are malformed")
    all_ciphers = _TLS12_CIPHERS | _TLS13_CIPHERS
    missing_ciphers, extra_ciphers = _difference(all_ciphers, cipher_names)
    require(not missing_ciphers, f"modern cipher suites missing: {missing_ciphers}")
    require(not extra_ciphers, f"cipher suites outside the modern allowlist: {extra_ciphers}")
    require(len(cipher_names) == len(set(cipher_names)), "cipher suite list contains duplicates")
    cipher_protocols = {
        row["name"]: row.get("protocol")
        for row in cipher_rows
        if isinstance(row.get("name"), str)
    }
    require(
        all(cipher_protocols.get(name) == "TLSv1.2" for name in _TLS12_CIPHERS),
        "TLS 1.2 cipher suite protocol labels are incorrect",
    )
    require(
        all(cipher_protocols.get(name) == "TLSv1.3" for name in _TLS13_CIPHERS),
        "TLS 1.3 cipher suite protocol labels are incorrect",
    )
    forbidden_ciphers = sorted(
        name
        for name in cipher_names
        if "CBC" in name.upper()
        or "SHA1" in name.upper()
        or ("RSA" in name.upper() and not name.upper().startswith("ECDHE-RSA-"))
    )
    require(not forbidden_ciphers, f"retired cipher suites are advertised: {forbidden_ciphers}")

    groups = runtime.get("groups")
    if not isinstance(groups, list) or any(not isinstance(group, str) for group in groups):
        groups = []
    missing_groups, extra_groups = _difference(_GROUPS, groups)
    require(not missing_groups, f"required key exchange groups missing: {missing_groups}")
    require(not extra_groups, f"key exchange groups outside the modern allowlist: {extra_groups}")
    require(len(groups) == len(set(groups)), "key exchange group list contains duplicates")

    signature_algorithms = runtime.get("signature_algorithms")
    if not isinstance(signature_algorithms, list) or any(
        not isinstance(algorithm, str) for algorithm in signature_algorithms
    ):
        signature_algorithms = []
    missing_signatures, extra_signatures = _difference(
        _SIGNATURE_ALGORITHMS, signature_algorithms
    )
    require(not missing_signatures, f"required SHA-2 signature algorithms missing: {missing_signatures}")
    require(not extra_signatures, f"signature algorithms outside the modern allowlist: {extra_signatures}")
    require(
        not any("sha1" in algorithm.lower() for algorithm in signature_algorithms),
        "SHA-1 signature algorithms are advertised",
    )

    client_context = runtime.get("default_client_context")
    if not isinstance(client_context, dict):
        client_context = {}
    require(client_context.get("is_ssl_context") is True, "create_default_context did not return an SSLContext")
    require(client_context.get("verify_required") is True, "default client context does not require certificates")
    require(client_context.get("check_hostname") is True, "default client context does not check hostnames")
    verify_flags = client_context.get("verify_flags")
    verify_flag_values = client_context.get("verify_flag_values")
    if not isinstance(verify_flags, int) or not isinstance(verify_flag_values, dict):
        verify_flags = 0
        verify_flag_values = {}
    for flag_name in _REQUIRED_VERIFY_FLAGS:
        flag_value = verify_flag_values.get(flag_name)
        require(
            isinstance(flag_value, int)
            and flag_value != 0
            and verify_flags & flag_value == flag_value,
            f"default client context does not enable {flag_name}",
        )
    store_stats = client_context.get("store_stats")
    require(
        isinstance(store_stats, dict)
        and isinstance(store_stats.get("x509_ca"), int)
        and store_stats["x509_ca"] > 0,
        "default client context has no trusted CA certificates",
    )

    return {
        "ok": not failures,
        "evidence": evidence,
        "error": "; ".join(failures) if failures else None,
    }
