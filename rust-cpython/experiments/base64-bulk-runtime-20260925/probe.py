"""Measure the pinned Base64 encoder kernel against staged CPython binascii."""

import argparse
import ctypes
import fcntl
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
import binascii


SOURCE_SHA = "3bcc6396bc10c4ae3022b05d7093751428414c0b6c694ee9bace47b725218a17"
PATCH_SHA = "48f02902978e7ed186e76eb9e677688442efd2baa30b89f9cf1b694394eb42c7"
PATCHED_SHA = "712afb7f0d258f68acc7ec1bf38a0501ea6fd9ad5f8fff00803a1214731b357a"
WRAPPER = '''
#[unsafe(no_mangle)]
pub unsafe extern "C" fn encode_into_raw(input: *const u8, len: usize, output: *mut u8) -> usize {
    let input = unsafe { std::slice::from_raw_parts(input, len) };
    let output = unsafe { std::slice::from_raw_parts_mut(output, encoded_output_len(len).unwrap()) };
    encode_into(input, output)
}
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Evidence:
    def __init__(self, path, run_id, recipe):
        self.path = path
        self.run_id = run_id
        self.data = json.loads(path.read_text()) if path.exists() else {"runs": []}
        if any(run["id"] == run_id for run in self.data["runs"]):
            raise RuntimeError(f"run ID already exists: {run_id}")
        self.run = {"id": run_id, "recipe": recipe, "attempts": []}
        self.data["runs"].append(self.run)
        self.checkpoint()

    def checkpoint(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + f".{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x") as stream:
                json.dump(self.data, stream, separators=(",", ":"), sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def add(self, attempt_id, kind, record):
        if any(attempt["id"] == attempt_id for attempt in self.run["attempts"]):
            raise RuntimeError(f"attempt ID already exists: {attempt_id}")
        self.run["attempts"].append({"id": attempt_id, "kind": kind, "record": record})
        self.checkpoint()


def usage():
    value = resource.getrusage(resource.RUSAGE_SELF)
    return value.ru_utime, value.ru_stime, value.ru_maxrss


def swap():
    result = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True,
                            text=True, check=True)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(args.scratch / ".evidence.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    scratch = args.scratch / run_id
    scratch.mkdir(parents=True)
    source = args.source.read_bytes()
    patch = args.patch.read_bytes()
    if digest(source) != SOURCE_SHA or digest(patch) != PATCH_SHA:
        raise RuntimeError("pinned source or patch hash mismatch")
    metadata = {
        "run_id": run_id,
        "source_sha256": digest(source),
        "patch_sha256": digest(patch),
        "python": sys.version,
        "python_executable": sys.executable,
        "binascii_sha256": digest(Path(binascii.__file__).read_bytes()),
        "host": platform.platform(),
        "rustc_version": subprocess.run(["rustc", "+nightly-2026-09-15", "--version", "-v"],
                                        capture_output=True, text=True, check=True).stdout,
        "rustc_flags": ["--crate-type", "cdylib", "-O", "-C", "target-cpu=apple-m1"],
        "sizes": [1048576, 65538],
        "input": "hashlib.shake_256(b'base64-bulk-runtime-20260925').digest(size)",
        "count": "ceil(64 MiB / input length) per arm and round",
        "rounds": 7,
        "timing": "perf_counter_ns wall; getrusage(RUSAGE_SELF) kernel user/system",
        "compile_timing": "/usr/bin/time -l around direct rustc; getrusage(RUSAGE_CHILDREN) delta",
        "swap_before": swap(),
        "load_before": os.getloadavg(),
    }
    evidence = Evidence(args.output, run_id, metadata)
    libraries = {}
    for label in ("baseline", "patched"):
        tree = scratch / label / "Modules" / "_base64" / "src"
        tree.mkdir(parents=True)
        src = tree / "lib.rs"
        src.write_bytes(source)
        if label == "patched":
            result = subprocess.run(["patch", "-p1", "-i", str(args.patch.resolve())],
                                    cwd=scratch / label, capture_output=True, text=True)
            if result.returncode:
                evidence.add("patch-failure", "patch", {"returncode": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr})
                raise RuntimeError("patch failed")
            if digest(src.read_bytes()) != PATCHED_SHA:
                evidence.add("patch-identity-failure", "patch", {
                    "expected_sha256": PATCHED_SHA, "actual_sha256": digest(src.read_bytes())})
                raise RuntimeError("patched source hash mismatch")
        actual = src.read_text()
        kernel = actual[actual.index("const PAD_BYTE:"):actual.index("struct BorrowedBuffer")]
        unit = scratch / f"{label}.rs"
        unit.write_text(kernel + WRAPPER)
        lib = scratch / f"lib{label}.dylib"
        command = ["rustc", "+nightly-2026-09-15", "--crate-type", "cdylib", "-O",
                   "-C", "target-cpu=apple-m1", str(unit), "-o", str(lib)]
        child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        wall_start = time.perf_counter_ns()
        result = subprocess.run(["/usr/bin/time", "-l", *command], capture_output=True,
                                text=True)
        elapsed = time.perf_counter_ns() - wall_start
        child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        record = {"label": label, "source_sha256": digest(src.read_bytes()),
                  "unit_sha256": digest(unit.read_bytes()), "command": command,
                  "returncode": result.returncode, "wall_ns": elapsed,
                  "children_user_s": child_after.ru_utime - child_before.ru_utime,
                  "children_system_s": child_after.ru_stime - child_before.ru_stime,
                  "children_peak_rss_bytes": child_after.ru_maxrss,
                  "time_l_stderr": result.stderr[-4500:], "stdout": result.stdout[-500:],
                  "swap_after": swap()}
        if lib.exists():
            record["library_sha256"] = digest(lib.read_bytes())
        evidence.add(f"compile-{label}", "compile", record)
        if result.returncode:
            raise RuntimeError(f"{label} rustc failed")
        library = ctypes.CDLL(str(lib))
        function = library.encode_into_raw
        function.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p)
        function.restype = ctypes.c_size_t
        libraries[label] = (library, function)

    for size in metadata["sizes"]:
        value = hashlib.shake_256(b"base64-bulk-runtime-20260925").digest(size)
        expected = binascii.b2a_base64(value, newline=False)
        expected_digest = digest(expected)
        input_buffer = ctypes.create_string_buffer(value)
        output_buffer = ctypes.create_string_buffer(len(expected))
        for label in ("baseline", "patched"):
            function = libraries[label][1]
            length = function(input_buffer, size, output_buffer)
            actual = output_buffer.raw[:length]
            if actual != expected:
                evidence.add(f"identity-{size}-failure", "identity", {
                    "size": size, "label": label, "actual_sha256": digest(actual),
                    "expected_sha256": expected_digest, "actual_length": length})
                raise RuntimeError(f"{label} output differs at {size}")
        evidence.add(f"identity-{size}", "identity", {"size": size,
                 "input_sha256": digest(value), "output_sha256": expected_digest,
                 "output_length": len(expected), "arms": ["baseline", "patched", "binascii"]})
        count = (64 * 1024 * 1024 + size - 1) // size
        for round_number in range(metadata["rounds"]):
            order = ("baseline", "patched", "binascii")
            order = order[round_number % 3:] + order[:round_number % 3]
            if round_number % 2:
                order = order[::-1]
            for position, label in enumerate(order):
                before = usage()
                start = time.perf_counter_ns()
                if label == "binascii":
                    for _ in range(count):
                        result = binascii.b2a_base64(value, newline=False)
                else:
                    function = libraries[label][1]
                    for _ in range(count):
                        length = function(input_buffer, size, output_buffer)
                wall_ns = time.perf_counter_ns() - start
                after = usage()
                actual_digest = digest(result) if label == "binascii" else digest(output_buffer.raw[:length])
                failure = (actual_digest != expected_digest or
                           (label != "binascii" and length != len(expected)))
                record = {
                    "size": size, "round": round_number, "position": position,
                    "order": order, "label": label, "count": count,
                    "wall_ns": wall_ns, "user_s": after[0] - before[0],
                    "system_s": after[1] - before[1], "process_peak_rss_bytes": after[2],
                    "output_sha256": actual_digest, "swap_after": swap(),
                    "outcome": "output_mismatch" if failure else "ok",
                }
                if failure:
                    record["expected_sha256"] = expected_digest
                    record["output_length"] = len(result) if label == "binascii" else length
                evidence.add(f"sample-{size}-{round_number}-{position}", "sample", record)
                if failure:
                    raise RuntimeError(f"{label} output changed")
    evidence.add("finish", "finish", {"swap_after": swap(), "load_after": os.getloadavg(),
                                   "process_peak_rss_bytes": usage()[2]})
    os.close(lock_fd)
    print(f"{args.output}#{run_id}")


if __name__ == "__main__":
    main()
