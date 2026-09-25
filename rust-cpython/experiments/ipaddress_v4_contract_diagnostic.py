"""Compare pinned IPv4 parser dispatch with a patched source overlay."""

import importlib.util
import json
from pathlib import Path
import sys
import types


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def result(module, text: str):
    try:
        return ["value", module.IPv4Address._ip_int_from_string(text)]
    except Exception as exc:
        return ["error", type(exc).__name__, str(exc)]


def observations(module):
    cases = {text: result(module, text) for text in (
        "1.2.3.4", "01.2.3.4", "256.2.3.4", "1.2.3", "1.2.3.4.5",
        "1.2.3.é", "",
    )}
    hooks = {
        "len": lambda value: 0,
        "map": lambda function, octets: iter([9, 9, 9, 9]),
        "int": types.SimpleNamespace(from_bytes=lambda *args: 99),
        "type": lambda value: str,
        "__import__": lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("import hook ran")),
    }
    for name, hook in hooks.items():
        setattr(module, name, hook)
        try:
            cases[f"hook:{name}"] = result(module, "1.2.3.4")
        finally:
            delattr(module, name)
    original = module._BaseV4.__dict__["_parse_octet"]
    module._BaseV4._parse_octet = classmethod(lambda cls, octet: 7)
    try:
        cases["base_parser_replaced"] = result(module, "1.2.3.4")
    finally:
        module._BaseV4._parse_octet = original
    module.IPv4Address._parse_octet = classmethod(lambda cls, octet: 7)
    try:
        cases["address_parser_replaced"] = result(module, "1.2.3.4")
    finally:
        del module.IPv4Address._parse_octet
    return cases


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: ipaddress_v4_contract_diagnostic.py BASE PATCHED")
    private = types.ModuleType("_rust_ipv4_scan")
    private.scan = lambda text: 99
    sys.modules[private.__name__] = private
    base, patched = (
        observations(load(name, Path(path)))
        for name, path in zip(("ipv4_base", "ipv4_patched"), sys.argv[1:])
    )
    print(json.dumps({"equal": base == patched, "base": base, "patched": patched},
                     sort_keys=True, ensure_ascii=False))
