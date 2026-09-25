"""Diagnostic for a guarded public Base64 route on the pinned Rust fork.

Run with the staged Rust interpreter. Timings under competing host load are
diagnostic only and are not suitable for a performance claim.
"""

import base64
import binascii
import hashlib
import json
import resource
import subprocess
import sys
import time
from _base64 import standard_b64encode as rust_encode

original_b2a_base64 = binascii.b2a_base64


def guarded(value, altchars=None, *, padded=True, wrapcol=0):
    if (type(value) is bytes and len(value) <= 256 and altchars is None
            and padded is True and type(wrapcol) is int and wrapcol == 0
            and binascii.b2a_base64 is original_b2a_base64):
        return rust_encode(value)
    return base64.b64encode(value, altchars, padded=padded, wrapcol=wrapcol)


def measure(call, value, count):
    start_wall = time.perf_counter_ns()
    start_cpu = time.process_time_ns()
    total = 0
    for _ in range(count):
        total += len(call(value))
    return {
        "ns_per_call_wall": (time.perf_counter_ns() - start_wall) / count,
        "ns_per_call_cpu": (time.process_time_ns() - start_cpu) / count,
        "total_output_bytes": total,
    }


def catalog(encoder, records):
    lines = []
    for number, data in enumerate(records):
        lines.append(str(number).encode("ascii") + b":" + encoder(data) + b"\n")
    return hashlib.sha256(b"".join(lines)).hexdigest()


def main():
    by_size = {}
    for size in (0, 1, 16, 32, 64, 128, 256, 512, 1024, 4096):
        value = bytes(range(256)) * (size // 256) + bytes(range(size % 256))
        count = max(20000, 1000000 // max(size, 1))
        methods = {
            "binascii": lambda data: binascii.b2a_base64(data, newline=False),
            "public": base64.b64encode,
            "rust": rust_encode,
            "guarded": guarded,
        }
        if len({method(value) for method in methods.values()}) != 1:
            raise RuntimeError(f"output differs at {size} bytes")
        rounds = []
        names = tuple(methods)
        for round_number in range(3):
            order = names if round_number % 2 == 0 else names[::-1]
            rounds.append({"order": order,
                           "samples": {name: measure(methods[name], value, count)
                                       for name in order}})
        by_size[str(size)] = {"count": count, "rounds": rounds}

    shapes = {
        "bytes": b"abcd",
        "bytearray": bytearray(b"abcd"),
        "memoryview": memoryview(b"abcd"),
        "strided_memoryview": memoryview(b"abcdef")[::2],
    }
    identity = {}
    for name, value in shapes.items():
        outcome = {}
        for method_name, method in (("public", base64.b64encode),
                                    ("rust", rust_encode), ("guarded", guarded)):
            try:
                outcome[method_name] = method(value).decode("ascii")
            except Exception as error:
                outcome[method_name] = [type(error).__name__, str(error)]
        identity[name] = outcome

    records = [hashlib.sha256(number.to_bytes(4, "little")).digest()
               for number in range(20000)]
    expected = catalog(base64.b64encode, records)
    encoders = {"public": base64.b64encode, "guarded": guarded}
    workloads = []
    for round_number in range(5):
        order = ("public", "guarded") if round_number % 2 == 0 else ("guarded", "public")
        samples = {}
        for name in order:
            wall_start = time.perf_counter_ns()
            cpu_start = time.process_time_ns()
            digest = catalog(encoders[name], records)
            samples[name] = {"wall_ns": time.perf_counter_ns() - wall_start,
                             "cpu_ns": time.process_time_ns() - cpu_start}
            if digest != expected:
                raise RuntimeError(f"catalog output differs for {name}")
        workloads.append({"order": order, "samples": samples})

    executable = sys.executable
    statements = {"base64": "import base64",
                  "base64_and_rust": "import base64, _base64"}
    cold_imports = []
    for round_number in range(5):
        order = (("base64", "base64_and_rust") if round_number % 2 == 0
                 else ("base64_and_rust", "base64"))
        samples = {}
        for name in order:
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = time.perf_counter_ns()
            result = subprocess.run([executable, "-I", "-S", "-B", "-c", statements[name]],
                                    check=True, capture_output=True)
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            samples[name] = {"wall_ns": time.perf_counter_ns() - start,
                             "user_seconds": after.ru_utime - before.ru_utime,
                             "system_seconds": after.ru_stime - before.ru_stime,
                             "returncode": result.returncode}
        cold_imports.append({"order": order, "samples": samples})

    usage = resource.getrusage(resource.RUSAGE_SELF)
    print(json.dumps({
        "python": sys.version,
        "module": rust_encode.__module__,
        "by_size": by_size,
        "buffer_shapes": identity,
        "catalog": {"records": len(records), "record_size": 32,
                    "digest": expected, "rounds": workloads},
        "cold_process_imports": cold_imports,
        "resource": {"user_seconds": usage.ru_utime,
                     "system_seconds": usage.ru_stime,
                     "max_rss_bytes": usage.ru_maxrss},
    }, indent=2))


if __name__ == "__main__":
    main()
