"""Isolated AArch64 Base64 kernel comparison with checkpointed resource evidence."""

import argparse
import binascii
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
import uuid

SOURCE_SHA = "3bcc6396bc10c4ae3022b05d7093751428414c0b6c694ee9bace47b725218a17"
CHUNK_PATCH_SHA = "48f02902978e7ed186e76eb9e677688442efd2baa30b89f9cf1b694394eb42c7"
WRAPPER = '''
#[unsafe(no_mangle)]
pub unsafe extern "C" fn encode_into_raw(input: *const u8, len: usize, output: *mut u8) -> usize {
    let input = unsafe { std::slice::from_raw_parts(input, len) };
    let output = unsafe { std::slice::from_raw_parts_mut(output, encoded_output_len(len).unwrap()) };
    encode_into(input, output)
}
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def swap():
    return subprocess.run(["sysctl", "-n", "vm.swapusage"], check=True,
                          capture_output=True, text=True).stdout.strip()


def usage(who):
    value = resource.getrusage(who)
    return value.ru_utime, value.ru_stime, value.ru_maxrss


class Evidence:
    def __init__(self, path, recipe):
        self.path = path
        self.run = {"id": time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8],
                    "recipe": recipe, "attempts": []}
        self.data = json.loads(path.read_text()) if path.exists() else {"runs": []}
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

    def add(self, attempt_id, kind, **record):
        self.run["attempts"].append({"id": attempt_id, "kind": kind, **record})
        self.save()


def compile_arm(evidence, scratch, label, source, patch):
    tree = scratch / label / "Modules" / "_base64" / "src"
    tree.mkdir(parents=True)
    target = tree / "lib.rs"
    target.write_bytes(source)
    if patch is not None:
        applied = subprocess.run(["patch", "-p1", "-i", str(patch.resolve())],
                                 cwd=scratch / label, capture_output=True, text=True)
        evidence.add("patch-" + label, "patch", outcome="ok" if applied.returncode == 0 else "failed",
                     stdout=applied.stdout, stderr=applied.stderr, source_sha256=sha(target.read_bytes()))
        if applied.returncode or target.read_bytes() == source:
            raise RuntimeError("patch failed to alter pinned source: " + label)
    actual = target.read_text()
    unit = scratch / (label + ".rs")
    unit.write_text(actual[actual.index("const PAD_BYTE:"):actual.index("struct BorrowedBuffer")] + WRAPPER)
    library = scratch / ("lib" + label + ".dylib")
    command = ["rustc", "+nightly-2026-09-15", "--crate-type", "cdylib", "-O",
               "-C", "target-cpu=apple-m1", str(unit), "-o", str(library)]
    before = usage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter_ns()
    result = subprocess.run(["/usr/bin/time", "-l", *command], capture_output=True, text=True)
    after = usage(resource.RUSAGE_CHILDREN)
    evidence.add("compile-" + label, "compile", outcome="ok" if result.returncode == 0 else "failed",
                 source_sha256=sha(target.read_bytes()), unit_sha256=sha(unit.read_bytes()),
                 library_sha256=sha(library.read_bytes()) if library.exists() else None,
                 library_bytes=library.stat().st_size if library.exists() else None,
                 wall_ns=time.perf_counter_ns() - start, user_s=after[0] - before[0],
                 system_s=after[1] - before[1], peak_rss_bytes=after[2],
                 time_l_stderr=result.stderr[-4500:], swap_after=swap())
    if result.returncode:
        raise RuntimeError("rustc failed: " + label)
    object_ = ctypes.CDLL(str(library))
    function = object_.encode_into_raw
    function.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p)
    function.restype = ctypes.c_size_t
    return object_, function


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    if platform.machine() != "arm64":
        raise RuntimeError("this native NEON measurement requires macOS arm64")
    source = args.source.read_bytes()
    chunk_patch = Path(__file__).with_name("base64-bulk-chunks-20260925.patch")
    neon_patch = Path(__file__).with_suffix(".patch")
    if sha(source) != SOURCE_SHA or sha(chunk_patch.read_bytes()) != CHUNK_PATCH_SHA:
        raise RuntimeError("pinned source or chunk patch mismatch")
    scratch = args.scratch / (time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    scratch.mkdir(parents=True)
    recipe = {"source_sha256": sha(source), "chunk_patch_sha256": sha(chunk_patch.read_bytes()),
              "neon_patch_sha256": sha(neon_patch.read_bytes()), "python": sys.version,
              "python_executable": sys.executable,
              "binascii_sha256": sha(Path(binascii.__file__).read_bytes()),
              "host": platform.platform(),
              "rustc": subprocess.run(["rustc", "+nightly-2026-09-15", "-Vv"],
                                      check=True, capture_output=True, text=True).stdout,
              "rustc_flags": ["--crate-type", "cdylib", "-O", "-C", "target-cpu=apple-m1"],
              "allocator": "Rust cdylib uses no heap allocation in the kernel; binascii uses staged CPython allocator",
              "input": "SHAKE256 seed b'base64-neon-20260925' for each length; zeros and 0xff additionally",
              "timing": "perf_counter_ns wall, getrusage(RUSAGE_SELF) user/system; /usr/bin/time -l for rustc process tree",
              "benchmark": args.benchmark, "load_before": os.getloadavg(), "swap_before": swap()}
    evidence = Evidence(args.output, recipe)
    arms = {label: compile_arm(evidence, scratch, label, source, patch)
            for label, patch in (("chunk", chunk_patch), ("neon", neon_patch))}
    identity_digest = hashlib.sha256()
    identity_cases = 0
    for size in (0, 1, 2, 3, 47, 48, 49, 50, 95, 96, 97, 98, 65536, 65537, 65538,
                 1048576, 1048577, 1048578):
        for pattern, value in (("shake", hashlib.shake_256(b"base64-neon-20260925").digest(size)),
                               ("zero", bytes(size)), ("ff", bytes([255]) * size)):
            expected = binascii.b2a_base64(value, newline=False)
            src = ctypes.create_string_buffer(value)
            dst = ctypes.create_string_buffer(len(expected))
            for label, (_, fn) in arms.items():
                got_len = fn(src, size, dst)
                actual = dst.raw[:got_len]
                ok = actual == expected
                identity_digest.update(f"{size}/{pattern}/{label}/{sha(value)}/{sha(actual)}/{sha(expected)}/{got_len}\n".encode())
                identity_cases += 1
                if not ok:
                    evidence.add(f"identity-failure-{size}-{pattern}-{label}", "identity",
                                 outcome="mismatch", size=size, pattern=pattern, label=label,
                                 input_sha256=sha(value), output_sha256=sha(actual),
                                 expected_sha256=sha(expected), output_len=got_len)
                    raise RuntimeError(f"{label} output mismatch at {size}/{pattern}")
    evidence.add("identity-sweep", "identity", outcome="ok", case_count=identity_cases,
                 case_digest_sha256=identity_digest.hexdigest(),
                 lengths=[0, 1, 2, 3, 47, 48, 49, 50, 95, 96, 97, 98, 65536, 65537,
                          65538, 1048576, 1048577, 1048578], patterns=["shake", "zero", "ff"],
                 arms=["chunk", "neon"])
    if args.benchmark:
        for size in (65538, 1048576):
            value = hashlib.shake_256(b"base64-neon-20260925").digest(size)
            expected = binascii.b2a_base64(value, newline=False)
            src = ctypes.create_string_buffer(value)
            dst = ctypes.create_string_buffer(len(expected))
            count = (64 * 1024 * 1024 + size - 1) // size
            for round_no in range(7):
                order = ("chunk", "neon", "binascii")
                order = order[round_no % 3:] + order[:round_no % 3]
                if round_no % 2:
                    order = order[::-1]
                for position, label in enumerate(order):
                    before = usage(resource.RUSAGE_SELF)
                    start = time.perf_counter_ns()
                    if label == "binascii":
                        for _ in range(count):
                            result = binascii.b2a_base64(value, newline=False)
                        actual = result
                    else:
                        fn = arms[label][1]
                        for _ in range(count):
                            got_len = fn(src, size, dst)
                        actual = dst.raw[:got_len]
                    elapsed = time.perf_counter_ns() - start
                    after = usage(resource.RUSAGE_SELF)
                    ok = actual == expected
                    evidence.add(f"sample-{size}-{round_no}-{position}", "sample",
                                 outcome="ok" if ok else "mismatch", size=size, round=round_no,
                                 position=position, order=order, label=label, count=count,
                                 wall_ns=elapsed, user_s=after[0] - before[0],
                                 system_s=after[1] - before[1], process_peak_rss_bytes=after[2],
                                 output_sha256=sha(actual), swap_after=swap())
                    if not ok:
                        raise RuntimeError("timed output mismatch")
    evidence.add("finish", "finish", load_after=os.getloadavg(), swap_after=swap(),
                 process_peak_rss_bytes=usage(resource.RUSAGE_SELF)[2])
    print(str(args.output) + "#" + evidence.run["id"])


if __name__ == "__main__":
    main()
