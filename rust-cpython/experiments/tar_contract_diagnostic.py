"""Inspect checksum binding fallbacks from a patched tarfile source overlay."""

import ast
import builtins
import json
import struct
import sys
import types
from pathlib import Path


source = Path(sys.argv[1])
tree = ast.parse(source.read_text())
guard_nodes = []
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id.startswith(("_ORIGINAL_", "_NATIVE_", "_CHECKSUM_", "_RUST_TAR_"))
        for target in node.targets
    ):
        guard_nodes.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name in (
        "_unchanged_import_path", "_trusted_checksum_scan", "calc_chksums"
    ):
        guard_nodes.append(node)

guard_code = compile(ast.Module(body=guard_nodes, type_ignores=[]), str(source), "exec")
baseline_code = compile(
    "def baseline(buf):\n"
    "    unsigned = 256 + sum(struct.unpack_from('148B8x356B', buf))\n"
    "    signed = 256 + sum(struct.unpack_from('148b8x356b', buf))\n"
    "    return unsigned, signed\n",
    "<pinned calc_chksums body>",
    "exec",
)
header = bytes(range(256)) * 2
observations = []


def observe(name, configure=None, value=header):
    namespace = {"builtins": builtins, "sys": sys, "struct": struct}
    exec(guard_code, namespace)
    exec(baseline_code, namespace)
    events = []
    cleanup = lambda: None
    if configure is not None:
        cleanup = configure(namespace, events)
    else:
        native = namespace["baseline"]
        namespace["_trusted_checksum_scan"] = lambda buf: (
            events.append("native"), native(buf)
        )[1]
    try:
        results = []
        for function in (namespace["calc_chksums"], namespace["baseline"]):
            before = len(events)
            try:
                outcome = {"result": function(value)}
            except Exception as error:
                outcome = {"error": type(error).__name__, "message": str(error)}
            outcome["events"] = events[before:]
            results.append(outcome)
        observations.append({"case": name, "candidate": results[0], "baseline": results[1]})
    finally:
        cleanup()


def replace_binding(name, replacement):
    def configure(namespace, events):
        namespace[name] = replacement(events)
        return lambda: None
    return configure


observe("ordinary_proxy")
observe("bytearray", value=bytearray(header))
observe("short_bytes", value=header[:-1])
observe("type_binding", replace_binding("type", lambda events: lambda obj: (events.append("type"), type(obj))[1]))
observe("bytes_binding", replace_binding("bytes", lambda events: bytearray))
observe("len_binding", replace_binding("len", lambda events: lambda obj: (events.append("len"), len(obj))[1]))
observe("sum_binding", replace_binding("sum", lambda events: lambda values: (events.append("sum"), sum(values))[1]))


def changed_struct(namespace, events):
    namespace["struct"] = types.SimpleNamespace(
        unpack_from=lambda *args: (events.append("unpack_from"), struct.unpack_from(*args))[1]
    )
    return lambda: None


observe("struct_binding", changed_struct)


def changed_import(namespace, events):
    original = builtins.__import__
    builtins.__import__ = lambda *args, **kwargs: (
        events.append("import"), original(*args, **kwargs)
    )[1]
    return lambda: setattr(builtins, "__import__", original)


observe("import_hook", changed_import)


def changed_meta_path(namespace, events):
    finder = object()
    sys.meta_path.append(finder)
    return lambda: sys.meta_path.remove(finder)


observe("meta_path", changed_meta_path)


def preloaded_private(namespace, events):
    fake = types.ModuleType("_rust_tar_checksum")
    fake.scan = lambda buf: (events.append("fake_scan"), (0, 0))[1]
    previous = sys.modules.get("_rust_tar_checksum")
    sys.modules["_rust_tar_checksum"] = fake
    def cleanup():
        if previous is None:
            del sys.modules["_rust_tar_checksum"]
        else:
            sys.modules["_rust_tar_checksum"] = previous
    return cleanup


observe("preloaded_private", preloaded_private)


def replaced_private(namespace, events):
    namespace["_RUST_TAR_MODULE"] = types.ModuleType("_rust_tar_checksum")
    namespace["_RUST_TAR_SCAN"] = lambda buf: (events.append("stale_scan"), (0, 0))[1]
    previous = sys.modules.get("_rust_tar_checksum")
    sys.modules["_rust_tar_checksum"] = types.ModuleType("_rust_tar_checksum")
    def cleanup():
        if previous is None:
            del sys.modules["_rust_tar_checksum"]
        else:
            sys.modules["_rust_tar_checksum"] = previous
    return cleanup


observe("replaced_private", replaced_private)


def changed_scan_attribute(namespace, events):
    module = types.ModuleType("_rust_tar_checksum")
    namespace["_RUST_TAR_MODULE"] = module
    namespace["_RUST_TAR_SCAN"] = lambda buf: (
        events.append("cached_scan"), namespace["baseline"](buf)
    )[1]
    module.scan = lambda buf: (events.append("changed_scan"), (0, 0))[1]
    previous = sys.modules.get("_rust_tar_checksum")
    sys.modules["_rust_tar_checksum"] = module
    def cleanup():
        if previous is None:
            del sys.modules["_rust_tar_checksum"]
        else:
            sys.modules["_rust_tar_checksum"] = previous
    return cleanup


observe("changed_scan_attribute", changed_scan_attribute)
print(json.dumps({"source": str(source), "observations": observations}, indent=2))
