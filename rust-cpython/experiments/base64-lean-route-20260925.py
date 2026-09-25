"""Check and measure two standalone binascii builds with the public Base64 API."""

import argparse
import array
import base64
import binascii
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
import uuid


STAGE_INCLUDE = Path("/Users/josh/d/python-build/rust-cpython/stage/include/python3.16")
CLANG = Path("/Users/josh/d/python-build/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1/bin/clang")
SDK = Path("/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk")
EXPERIMENTS = Path(__file__).resolve().parent
SOURCE_HASHES = {
    "binascii.c": "e2653c0d14867d5e6340f1845e59f7d9a072e0a3b00c8a9e02aaa2f0b3a4dae1",
    "_base64/src/lib.rs": "7dd969bdf6f4d44d84daf351cd17c79b7c9a54ab8956e41b0a1626a9e6edeba2",
    "_base64/src/lean_route.rs": "45c298891de1e03dbcd1bb8eca41f569d6e262fa4dae4f7b398f7cabf77def2e",
}
ORIGINAL_HASHES = {
    "binascii.c": "6a87f282b9bb1501cbd17ef652d9c003e047402a6a7916d7cc3f8863c58c610e",
    "clinic/binascii.c.h": "ce732ade621a63cf2dda3d28185505350e110e92431ea437b64e53fc99305797",
    "_base64/src/lib.rs": "3bcc6396bc10c4ae3022b05d7093751428414c0b6c694ee9bace47b725218a17",
}


def build(scratch, pinned_modules):
    for name, expected in ORIGINAL_HASHES.items():
        path = pinned_modules / name
        actual = digest(path.read_bytes())
        if actual != expected:
            raise RuntimeError(f"original source mismatch for {name}: {actual}")
    source = scratch / "source/Modules"
    (source / "_base64/src/lean_route.rs").unlink(missing_ok=True)
    for name in ORIGINAL_HASHES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pinned_modules / name, path)
        if digest(path.read_bytes()) != ORIGINAL_HASHES[name]:
            raise RuntimeError(f"copied source mismatch for {name}")
    commands = []
    for name in ("base64-neon-20260925", "base64-binascii-route-20260925",
                 "base64-lean-route-20260925"):
        commands.append(["patch", "-p1", "-d", str(scratch / "source"),
                         "-i", str(EXPERIMENTS / (name + ".patch"))])
    source_rust = source / "_base64/src/lib.rs"
    # The standard-library route is extracted from the same patched kernel.
    commands.append(["rustc", "+nightly-2026-09-15", "--crate-type", "staticlib", "-O",
                     "-C", "target-cpu=apple-m1", "-C", "panic=abort",
                     str(scratch / "route-kernel.rs"), "-o", str(scratch / "libroute_kernel.a")])
    commands.append(["rustc", "+nightly-2026-09-15", "--crate-type", "staticlib", "-O",
                     "-C", "target-cpu=apple-m1", "-C", "panic=abort",
                     str(source / "_base64/src/lean_route.rs"), "-o", str(scratch / "liblean_kernel.a")])
    common = [str(CLANG), "-O3", "-mcpu=apple-m1", "-fPIC", "-mmacosx-version-min=26.0",
              "-isysroot", str(SDK), "-I" + str(STAGE_INCLUDE),
              "-I" + str(STAGE_INCLUDE / "internal")]
    for arm in ("control", "route", "lean"):
        (scratch / arm).mkdir(parents=True, exist_ok=True)
        modules = pinned_modules if arm == "control" else source
        commands.append([*common, "-I" + str(modules), "-c", str(modules / "binascii.c"),
                         "-o", str(scratch / arm / "binascii.o")])
    for arm in ("control", "route", "lean"):
        command = [str(CLANG), "-bundle", "-undefined", "dynamic_lookup",
                   "-mmacosx-version-min=26.0", "-isysroot", str(SDK)]
        if arm != "control":
            command += ["-Wl,-dead_strip", "-Wl,-exported_symbol,_PyInit_binascii"]
        command += [str(scratch / arm / "binascii.o")]
        if arm != "control":
            command.append(str(scratch / ("libroute_kernel.a" if arm == "route" else "liblean_kernel.a")))
        command += ["-o", str(scratch / arm / "binascii.cpython-316-darwin.so")]
        commands.append(command)
    measurements = []
    for index, command in enumerate(commands):
        if index == 3:
            for name, expected in SOURCE_HASHES.items():
                actual = digest((source / name).read_bytes())
                if actual != expected:
                    raise RuntimeError(f"patched source mismatch for {name}: {actual}")
            text = source_rust.read_text()
            (scratch / "route-kernel.rs").write_text(text[text.index("const PAD_BYTE:"):text.index("struct BorrowedBuffer {")])
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = time.perf_counter_ns()
        result = subprocess.run(["/usr/bin/time", "-l", *command], capture_output=True, text=True)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        measurements.append({"id": f"build-{index:02d}", "kind": "build",
                             "outcome": "ok" if result.returncode == 0 else "failed",
                             "command": command, "wall_ns": time.perf_counter_ns() - started,
                             "user_s": after.ru_utime - before.ru_utime,
                             "system_s": after.ru_stime - before.ru_stime,
                             **time_fields(result.stderr),
                             "error": result.stderr[-1000:] if result.returncode else None})
        if result.returncode:
            raise RuntimeError(f"build command {index} failed: {result.stderr[-1000:]}")
    return measurements


def digest(value):
    return hashlib.sha256(value).hexdigest()


def swap():
    return subprocess.run(["sysctl", "-n", "vm.swapusage"], check=True,
                          capture_output=True, text=True).stdout.strip()


def usage():
    value = resource.getrusage(resource.RUSAGE_SELF)
    return value.ru_utime, value.ru_stime, value.ru_maxrss


class Evidence:
    def __init__(self, path, recipe):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"runs": []}
        self.run = {"id": time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8],
                    "recipe": recipe, "attempts": []}
        self.data["runs"].append(self.run)
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("x") as stream:
            json.dump(self.data, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def add(self, attempt_id, kind, **fields):
        if kind == "build" and "command" in fields:
            command = fields.pop("command")
            command_id = hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest()[:16]
            commands = self.data.setdefault("build_commands", {})
            if command_id in commands and commands[command_id] != command:
                raise RuntimeError("build command identity collision")
            commands[command_id] = command
            fields["command_id"] = command_id
        self.run["attempts"].append({"id": attempt_id, "kind": kind, **fields})
        self.save()


def install(path):
    sys.modules.pop("binascii", None)
    spec = importlib.util.spec_from_file_location("binascii", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load binascii extension")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["binascii"] = module
    base64.binascii = module
    if Path(module.__file__).resolve() != path.resolve():
        raise RuntimeError("unexpected binascii extension: " + module.__file__)
    return module


def outcome(call):
    try:
        value = call()
        return ["bytes", digest(value), len(value)]
    except Exception as error:
        return [type(error).__name__, str(error)]


def cases():
    for size in (0, 1, 2, 3, 47, 48, 49, 95, 96, 97, 4095, 4096, 4097,
                 65536, 65537, 65538, 1048576, 1048577, 1048578):
        for pattern, value in (("shake", hashlib.shake_256(b"base64-lean-20260925").digest(size)),
                               ("zero", bytes(size)), ("ff", b"\xff" * size)):
            yield f"public-{size}-{pattern}", lambda v=value: base64.b64encode(v)
            yield f"direct-{size}-{pattern}", lambda v=value: base64.binascii.b2a_base64(v, newline=False)
    value = hashlib.shake_256(b"base64-options").digest(65538)
    for label, kwargs in (("altchars", {"altchars": b"-_"}),
                          ("padded", {"padded": False}),
                          ("wrap", {"wrapcol": 76}),
                          ("altchars-padded-wrap", {"altchars": b"-_", "padded": False, "wrapcol": 76})):
        yield label, lambda v=value, k=kwargs: base64.b64encode(v, **k)
    for label, kwargs in (("newline", {"newline": True}),
                          ("alphabet", {"newline": False, "alphabet": b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"}),
                          ("bad-alphabet", {"newline": False, "alphabet": b"short"})):
        yield label, lambda v=value, k=kwargs: base64.binascii.b2a_base64(v, **k)
    for label, value in (("bytearray", bytearray(value)),
                         ("memoryview", memoryview(value)),
                         ("array", array.array("B", value)),
                         ("strided", memoryview(value)[::2])):
        yield label, lambda v=value: base64.b64encode(v)
    yield "invalid-public-altchars", lambda: base64.b64encode(value, altchars=b"x")
    yield "invalid-direct-type", lambda: base64.binascii.b2a_base64("abc", newline=False)


def catalog():
    result = hashlib.sha256()
    for number in range(20000):
        value = hashlib.sha256(number.to_bytes(4, "little")).digest()
        result.update(base64.b64encode(value))
    return result.hexdigest()


def measure(label, size, count):
    value = hashlib.shake_256(b"base64-timing-20260925").digest(size)
    before = usage()
    start = time.perf_counter_ns()
    for _ in range(count):
        output = base64.b64encode(value)
    wall = time.perf_counter_ns() - start
    after = usage()
    return {"label": label, "size": size, "count": count, "wall_ns": wall,
            "user_s": after[0] - before[0], "system_s": after[1] - before[1],
            "process_peak_rss_bytes": after[2], "output_sha256": digest(output),
            "swap_after": swap()}


def time_fields(stderr):
    fields = {}
    for name, marker in (("time_peak_rss_bytes", "maximum resident set size"),
                         ("page_reclaims", "page reclaims"),
                         ("page_faults", "page faults"),
                         ("swaps", "swaps")):
        match = re.search(r"(?m)^\s*(\d+)\s+" + re.escape(marker) + r"\s*$", stderr)
        fields[name] = int(match.group(1)) if match else None
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--source-modules", type=Path,
                        help="Modules directory from the verified pinned source archive; required with --build")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--memory-arm", choices=("control", "lean"))
    args = parser.parse_args()
    if args.build and args.source_modules is None:
        parser.error("--source-modules is required with --build")
    build_records = build(args.scratch, args.source_modules) if args.build else []
    paths = {label: args.scratch / label / "binascii.cpython-316-darwin.so"
             for label in ("control", "route", "lean")}
    for path in paths.values():
        if not path.is_file():
            raise RuntimeError("missing extension: " + str(path))
    if args.memory_arm:
        module = install(paths[args.memory_arm])
        value = hashlib.shake_256(b"base64-memory-20260925").digest(1048576)
        encoded = base64.b64encode(value)
        print(json.dumps({"arm": args.memory_arm, "module_file": module.__file__,
                          "module_sha256": digest(paths[args.memory_arm].read_bytes()),
                          "output_sha256": digest(encoded), "peak_rss_bytes": usage()[2]}))
        return
    if args.evidence is None:
        parser.error("--evidence is required outside --memory-arm")
    original = binascii.__file__
    evidence = Evidence(args.evidence, {"python": sys.version, "python_executable": sys.executable,
                                       "staged_binascii": original,
                                       "extensions": {label: {"sha256": digest(path.read_bytes()),
                                                              "bytes": path.stat().st_size}
                                                      for label, path in paths.items()},
                                       "input": "SHAKE256, zeros, 0xff; 20,000 SHA256 catalog records",
                                       "timing": "perf_counter_ns and getrusage(RUSAGE_SELF); peak RSS is process-wide high-water mark",
                                       "load_before": os.getloadavg(), "swap_before": swap(),
                                       "benchmark": args.benchmark})
    for record in build_records:
        evidence.add(record.pop("id"), record.pop("kind"), **record)
    outputs = {}
    for label, path in paths.items():
        module = install(path)
        hashes = {}
        for case_label, call in cases():
            hashes[case_label] = outcome(call)
        hashes["catalog"] = catalog()
        outputs[label] = hashes
        evidence.add("identity-" + label, "identity", outcome="ok", module_file=module.__file__,
                     module_sha256=digest(path.read_bytes()), cases=len(hashes),
                     result_digest=digest(json.dumps(hashes, sort_keys=True).encode()),
                     catalog_sha256=hashes["catalog"])
    differences = {label: {key: [outputs["control"][key], outputs[label][key]]
                           for key in outputs["control"] if outputs["control"][key] != outputs[label][key]}
                   for label in ("route", "lean")}
    differences = {label: values for label, values in differences.items() if values}
    evidence.add("identity-compare", "identity", outcome="ok" if not differences else "mismatch",
                 differences=differences)
    if differences:
        raise RuntimeError("public Base64 outputs differ")
    if args.benchmark:
        for size in (65538, 1048576):
            count = max(1, 32 * 1024 * 1024 // size)
            for round_no in range(5):
                order = ("control", "lean") if round_no % 2 == 0 else ("lean", "control")
                for position, label in enumerate(order):
                    install(paths[label])
                    sample = measure(label, size, count)
                    evidence.add(f"sample-{size}-{round_no}-{position}", "sample", outcome="ok",
                                 round=round_no, position=position, order=order, **sample)
        memory_plan = (("control", "lean"), ("lean", "control"),
                       ("control", "lean"), ("control", "control"))
        for pair_no, order in enumerate(memory_plan):
            for position, label in enumerate(order):
                command = ["/usr/bin/time", "-l", sys.executable, "-S", str(Path(__file__).resolve()),
                           "--scratch", str(args.scratch), "--memory-arm", label]
                before = resource.getrusage(resource.RUSAGE_CHILDREN)
                started = time.perf_counter_ns()
                result = subprocess.run(command, capture_output=True, text=True)
                after = resource.getrusage(resource.RUSAGE_CHILDREN)
                identity = json.loads(result.stdout) if result.returncode == 0 else None
                evidence.add(f"memory-{pair_no}-{position}", "memory",
                             outcome="ok" if result.returncode == 0 else "failed",
                             pair=pair_no, position=position, order=order, arm=label,
                             wall_ns=time.perf_counter_ns() - started,
                             user_s=after.ru_utime - before.ru_utime,
                             system_s=after.ru_stime - before.ru_stime,
                             child=identity, **time_fields(result.stderr),
                             error=result.stderr[-1000:] if result.returncode else None,
                             swap_after=swap())
                if result.returncode:
                    raise RuntimeError("memory subprocess failed for " + label)
    evidence.add("finish", "finish", load_after=os.getloadavg(), swap_after=swap(),
                 process_peak_rss_bytes=usage()[2])
    print(str(args.evidence) + "#" + evidence.run["id"])


if __name__ == "__main__":
    main()
