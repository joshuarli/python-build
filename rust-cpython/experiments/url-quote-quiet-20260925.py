"""Same-interpreter paired timing for the revised URL quote guard."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "rust-cpython/work/url-quote-quiet-20260925"
PYTHON = Path("/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16")
STAGE_PARSE = Path("/Users/josh/d/python-build/rust-cpython/stage/lib/python3.16/urllib/parse.py")
PATCH = ROOT / "rust-cpython/patches/0001-rust-url-quote.patch"
DATA = ROOT / "rust-cpython/experiments/data/url-quote-quiet-20260925.json"
EXPECTED = {
    "catalog_search_form": (500, "a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22"),
    "catalog_request_path": (1000, "52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff"),
}
INPUT_DIGEST = "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host() -> dict[str, object]:
    rows = subprocess.check_output(["ps", "-axo", "pid,pcpu,rss,comm"], text=True).splitlines()[1:]
    top = sorted((row.strip() for row in rows),
                 key=lambda row: float(row.split()[1]), reverse=True)[:3]
    swap = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True).strip()
    vm = subprocess.check_output(["vm_stat"], text=True).splitlines()[1:]
    pages = {line.split(":", 1)[0]: int(line.split(":", 1)[1].strip().rstrip("."))
             for line in vm if line.startswith(("Pages free:", "Pages active:",
                                                "Pages inactive:", "Pages wired down:",
                                                "Pages occupied by compressor:"))}
    return {"load_average": os.getloadavg(), "swap": swap, "top_processes": top,
            "vm_pages": pages}


def run(task: str, side: str, attempt_id: str) -> dict[str, object]:
    iterations, expected_digest = EXPECTED[task]
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join((str(WORK / side), str(WORK / "native"), str(ROOT))),
               PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="1")
    argv = [str(PYTHON), "-B", "-m", "benchmarks.workloads.catalog_url_breadth",
            task, "--iterations", str(iterations)]
    before = host()
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    time.sleep(0.08)
    during = host() if proc.poll() is None else None
    pid, status, usage = os.wait4(proc.pid, 0)
    wall = time.monotonic() - started
    assert pid == proc.pid
    stdout = proc.stdout.read().decode() if proc.stdout else ""
    stderr = proc.stderr.read().decode() if proc.stderr else ""
    code = os.waitstatus_to_exitcode(status)
    record: dict[str, object] = {
        "id": attempt_id, "task": task, "side": side, "returncode": code,
        "wall_seconds": wall, "user_seconds": usage.ru_utime,
        "system_seconds": usage.ru_stime, "peak_rss_bytes": usage.ru_maxrss,
        "swaps": usage.ru_nswap, "host_before": before, "host_during": during,
    }
    try:
        result = json.loads(stdout)
        record.update(output_digest=result["digest"], input_digest=result["input_digest"],
                      operation_count=result["operation_count"])
        record["valid"] = (code == 0 and result["digest"] == expected_digest
                           and result["input_digest"] == INPUT_DIGEST
                           and result["operation_count"] == iterations)
    except (ValueError, KeyError, TypeError):
        record.update(valid=False, stdout_excerpt=stdout[:400])
    if stderr:
        record["stderr_excerpt"] = stderr[:400]
    return record


def main() -> None:
    identities = {
        "patch_sha256": sha256(PATCH), "interpreter_sha256": sha256(PYTHON),
        "stage_parse_sha256": sha256(STAGE_PARSE),
        "control_parse_sha256": sha256(WORK / "control/urllib/parse.py"),
        "candidate_parse_sha256": sha256(WORK / "candidate/urllib/parse.py"),
        "patched_source_parse_sha256": sha256(WORK / "source/Lib/urllib/parse.py"),
        "module_c_sha256": sha256(WORK / "source/Modules/_rust_url_quote/module.c"),
        "quote_rs_sha256": sha256(WORK / "source/Modules/_rust_url_quote/quote.rs"),
        "extension_sha256": sha256(WORK / "native/_rust_url_quote.cpython-316-darwin.so"),
    }
    if identities["control_parse_sha256"] != identities["stage_parse_sha256"]:
        raise SystemExit("control parser differs from installed parser")
    if identities["candidate_parse_sha256"] != identities["patched_source_parse_sha256"]:
        raise SystemExit("candidate parser differs from current patch output")
    if any((WORK / side / "urllib/__pycache__").exists() for side in ("control", "candidate")):
        raise SystemExit("overlay bytecode cache exists")
    evidence: dict[str, object] = {
        "identities": identities,
        "command": "stage/bin/python3.16 -B -m benchmarks.workloads.catalog_url_breadth TASK --iterations N",
        "environment": "PYTHONPATH=SIDE:NATIVE:ROOT; PYTHONDONTWRITEBYTECODE=1; PYTHONHASHSEED=1",
        "cache_policy": "Both overlays have no __pycache__; source compiled on each import",
        "accounting": "os.wait4 direct workload child; monotonic wall includes a host sample during the run; no workload descendants; ru_maxrss is lifetime peak, ru_nswap is child swaps; host ps RSS is sampled, physical footprint unavailable",
        "host_initial": host(), "attempts": [], "groups": [],
    }
    DATA.write_text(json.dumps(evidence, indent=2) + "\n")
    groups = evidence["groups"]
    attempts = evidence["attempts"]
    assert isinstance(groups, list) and isinstance(attempts, list)
    for task in EXPECTED:
        for comparison, orders in (
            ("control_candidate", (("control", "candidate"), ("candidate", "control"),
                                   ("control", "candidate"), ("candidate", "control"))),
            ("control_control", (("control", "control"), ("control", "control"))),
            ("candidate_candidate", (("candidate", "candidate"), ("candidate", "candidate"))),
        ):
            for pair, order in enumerate(orders):
                group_id = f"{task}-{comparison}-{pair}"
                groups.append({"id": group_id, "order": order})
                for position, side in enumerate(order):
                    record = run(task, side, f"{group_id}-{position}")
                    attempts.append(record)
                    DATA.write_text(json.dumps(evidence, indent=2) + "\n")
                    if not record["valid"]:
                        raise SystemExit(f"invalid attempt {record['id']}")
    evidence["host_final"] = host()
    DATA.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
