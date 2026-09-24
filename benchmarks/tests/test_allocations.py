"""Behavior tests for the Memray allocation profiling pass."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from benchmarks.harness import allocations


def _process_result(
    command,
    *,
    returncode=0,
    stdout="",
    stderr="",
    timed_out=False,
    cleanup_complete=True,
    remaining_pids=(),
):
    return allocations.ProcessResult(
        command=tuple(str(part) for part in command),
        returncode=returncode,
        stdout=stdout.encode() if isinstance(stdout, str) else stdout,
        stderr=stderr.encode() if isinstance(stderr, str) else stderr,
        timed_out=timed_out,
        duration_seconds=0,
        memory=None,
        cleanup_complete=cleanup_complete,
        remaining_pids=tuple(remaining_pids),
    )


class AllocationPassTests(unittest.TestCase):
    def test_python_switches_stay_before_memray_and_script_switches_after(self) -> None:
        options, target = allocations._split_python_invocation(
            ["-X", "dev", "-Wignore", "-OO", "-m", "sample.workload", "--rows", "4"]
        )
        self.assertEqual(options, ["-X", "dev", "-Wignore", "-OO"])
        self.assertEqual(target, ["-m", "sample.workload", "--rows", "4"])

    def test_unknown_python_switch_is_not_reinterpreted_as_script(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Python interpreter option"):
            allocations._split_python_invocation(["--unknown", "script.py"])

    def test_python_end_of_options_marker_is_preserved_for_memray(self) -> None:
        options, target = allocations._split_python_invocation(["--", "-script.py", "arg"])
        self.assertEqual(options, [])
        self.assertEqual(target, ["--", "-script.py", "arg"])

    def test_profile_uses_external_pythonpath_and_writes_normalized_json(self) -> None:
        stats = {
            "total_num_allocations": 120,
            "total_bytes_allocated": 9600,
            "allocator_type_distribution": {"PYMALLOC_MALLOC": 100, "MALLOC": 20},
            "top_allocations_by_size": [{"location": "work:app.py:4", "size": 7000}],
            "top_allocations_by_count": [{"location": "work:app.py:4", "count": 90}],
            "top_modules_by_allocation_size": [
                {"module": "work", "num_allocations": 110, "total_bytes": 9000}
            ],
            "top_modules_by_allocation_count": [],
            "metadata": {"peak_memory": 4096, "has_native_traces": True},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            memray_prefix = root / "memray site"
            repo_prefix = root / "repo"
            output_path = root / "result" / "allocations.json"
            calls: list[tuple[list[str], dict[str, str]]] = []
            from contextlib import redirect_stdout
            from io import StringIO

            visible_stdout = StringIO()

            def run(command, **kwargs):
                calls.append((command, kwargs["env"]))
                if "-c" in command:
                    code = command[command.index("-c") + 1]
                    if code == allocations._NATIVE_ORIGINS_SCRIPT:
                        return _process_result(
                            command,
                            stdout=json.dumps(
                                {
                                    "status": "available",
                                    "origins": [
                                        {"origin": "native_alloc:extension.c:2", "allocations": 4, "bytes": 512}
                                    ],
                                }
                            ),
                        )
                    return _process_result(
                        command,
                        stdout='{"version":"1.20.0"}\n',
                    )
                if "run" in command:
                    capture_path = Path(command[command.index("--output") + 1])
                    capture_path.write_bytes(b"capture")
                    return _process_result(command, stdout='{"digest":"target-result"}\n')
                stats_path = Path(command[command.index("--output") + 1])
                stats_path.write_text(json.dumps(stats), encoding="utf-8")
                return _process_result(command)

            with patch.object(allocations, "run_command", side_effect=run):
                with redirect_stdout(visible_stdout):
                    report = allocations.run_allocation_pass(
                        ["/opt/python/bin/python3.14", "-m", "workload", "--rows", "40"],
                        memray_pythonpath=memray_prefix,
                        output_json=output_path,
                        operations=40,
                        env={"PYTHONPATH": str(repo_prefix)},
                    )

            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["profiler_version"], "1.20.0")
            self.assertEqual(report["total_num_allocations"], 120)
            self.assertEqual(report["total_bytes_allocated"], 9600)
            self.assertEqual(report["heap_peak_bytes"], 4096)
            self.assertEqual(report["allocations_per_operation"], 3)
            self.assertEqual(report["bytes_allocated_per_operation"], 240)
            self.assertEqual(report["native_origins_status"], "available")
            self.assertEqual(report["native_origins"][0]["bytes"], 512)
            self.assertFalse(report["elapsed_time_comparable"])
            self.assertEqual(visible_stdout.getvalue(), "")
            self.assertTrue(output_path.is_file())
            self.assertEqual(json.loads(output_path.read_text())["status"], "complete")
            for _, child_env in calls:
                self.assertEqual(
                    child_env["PYTHONPATH"],
                    str(memray_prefix) + ":" + str(repo_prefix),
                )
            profile_call = calls[1][0]
            self.assertIn("--native", profile_call)
            self.assertIn("--trace-python-allocators", profile_call)
            self.assertEqual(profile_call[-4:], ["-m", "workload", "--rows", "40"])

    def test_missing_memray_is_written_as_unavailable_with_null_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "allocations.json"
            probe_error = subprocess.CompletedProcess(
                ["python", "-c", "import memray"],
                1,
                stdout="",
                stderr="ModuleNotFoundError: No module named 'memray'",
            )
            with patch.object(
                allocations,
                "run_command",
                return_value=_process_result(
                    probe_error.args[0],
                    returncode=probe_error.returncode,
                    stdout=probe_error.stdout,
                    stderr=probe_error.stderr,
                ),
            ):
                report = allocations.run_allocation_pass(
                    ["python", "-c", "pass"],
                    memray_pythonpath=Path(temporary) / "external",
                    output_json=output_path,
                )

            self.assertEqual(report["status"], "unavailable")
            self.assertIn("No module named 'memray'", report["reason"])
            self.assertIsNone(report["total_num_allocations"])
            self.assertIsNone(report["total_bytes_allocated"])
            self.assertIsNone(report["heap_peak_bytes"])
            self.assertEqual(json.loads(output_path.read_text())["status"], "unavailable")

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "allocations.json"
            output_path.write_text("prior result", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                allocations.run_allocation_pass(
                    ["python", "-c", "pass"],
                    memray_pythonpath=temporary,
                    output_json=output_path,
                )

    def test_invalid_operation_count_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "positive integer"):
                allocations.run_allocation_pass(
                    ["python", "-c", "pass"],
                    memray_pythonpath=temporary,
                    output_json=Path(temporary) / "allocations.json",
                    operations=0,
                )

    def test_target_failure_is_not_published_as_a_completed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "allocations.json"

            def run(command, **kwargs):
                if command[1:2] == ["-c"]:
                    return _process_result(command, stdout='{"version":"1.20.0"}\n')
                return _process_result(command, returncode=3, stderr="target failed")

            with patch.object(allocations, "run_command", side_effect=run):
                with self.assertRaises(subprocess.CalledProcessError):
                    allocations.run_allocation_pass(
                        ["python", "-m", "workload"],
                        memray_pythonpath=temporary,
                        output_json=output_path,
                    )
            self.assertFalse(output_path.exists())

    def test_fork_following_keeps_process_peaks_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def run(command, **kwargs):
                if command[1:2] == ["-c"]:
                    return _process_result(command, stdout='{"version":"1.20.0"}\n')
                if "run" in command:
                    capture_path = Path(command[command.index("--output") + 1])
                    capture_path.write_bytes(b"parent")
                    Path(str(capture_path) + ".123").write_bytes(b"child")
                    return _process_result(command)
                capture_path = Path(command[-1])
                is_child = capture_path.name.endswith(".123")
                stats_path = Path(command[command.index("--output") + 1])
                stats_path.write_text(
                    json.dumps({
                        "total_num_allocations": 20 if is_child else 10,
                        "total_bytes_allocated": 200 if is_child else 100,
                        "allocator_type_distribution": {"MALLOC": 20 if is_child else 10},
                        "metadata": {
                            "pid": 123 if is_child else 42,
                            "peak_memory": 2500 if is_child else 1500,
                            "has_native_traces": False,
                        },
                    }),
                    encoding="utf-8",
                )
                return _process_result(command)

            with patch.object(allocations, "run_command", side_effect=run):
                allocations.run_allocation_pass(
                    ["python", "-c", "pass"],
                    memray_pythonpath=temporary,
                    output_json=root / "allocations.json",
                    operations=5,
                    follow_fork=True,
                    native=False,
                )
            report = json.loads((root / "allocations.json").read_text(encoding="utf-8"))
            self.assertEqual(report["total_num_allocations"], 30)
            self.assertEqual(report["total_bytes_allocated"], 300)
            self.assertEqual(report["allocations_per_operation"], 6)
            self.assertIsNone(report["heap_peak_bytes"])
            self.assertEqual(report["heap_peak_status"], "per_process_only")
            self.assertEqual(
                report["process_heap_peaks"],
                [
                    {"pid": 42, "heap_peak_bytes": 1500},
                    {"pid": 123, "heap_peak_bytes": 2500},
                ],
            )

    @unittest.skipUnless(Path("/proc").is_dir(), "process group cleanup requires Linux procfs")
    def test_timeout_cleans_up_spawned_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pid_path = Path(temporary) / "child.pid"
            code = (
                "import subprocess, sys, time; "
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
                f"open({str(pid_path)!r}, 'w').write(str(child.pid)); "
                "time.sleep(60)"
            )

            with self.assertRaises(allocations.AllocationCommandTimeout) as caught:
                allocations._run_child_command(
                    [sys.executable, "-c", code],
                    env=os.environ,
                    timeout_seconds=0.2,
                )

            self.assertTrue(caught.exception.cleanup_complete)
            self.assertEqual(caught.exception.remaining_pids, ())
            child_pid = int(pid_path.read_text(encoding="ascii"))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                stat_path = Path(f"/proc/{child_pid}/stat")
                if not stat_path.exists():
                    break
                fields = stat_path.read_text(encoding="ascii").split()
                if fields[2] == "Z":
                    break
                time.sleep(0.02)
            else:
                self.fail(f"timed-out allocation descendant {child_pid} is still running")


if __name__ == "__main__":
    unittest.main()
