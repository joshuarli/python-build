"""Serial resource follow-up for the installed guarded URL quote patch.

Run phases separately from the worktree root. Cloned stages and controller
time logs live under ignored rust-cpython/work/url-quote-memory-followup-20260924.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "rust-cpython/work/url-quote-memory-followup-20260924"
HASHES = {
    "control": {
        "python": "6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd",
        "parse": "178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825",
        "extension": None,
    },
    "candidate": {
        "python": "622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6",
        "parse": "85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee",
        "extension": "5f00a07bbcc282659e1258d0509c1e117f9db185cf94f867aeb809736f616916",
    },
}
EXPECTED_INPUT = "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f"
EXPECTED_PATH = "52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff"
SIDES = ("control", "candidate")


def paths(side: str) -> dict[str, Path]:
    prefix = WORK / side
    return {
        "python": prefix / "bin/python3.16",
        "parse": prefix / "lib/python3.16/urllib/parse.py",
        "cache": prefix / "lib/python3.16/urllib/__pycache__/parse.cpython-316.pyc",
        "extension": prefix / "lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so",
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight() -> dict[str, object]:
    identity = {}
    for side in SIDES:
        files = paths(side)
        digests = {name: sha256(path) if path.exists() else None
                   for name, path in files.items()}
        for name in ("python", "parse", "extension"):
            assert digests[name] == HASHES[side][name], (side, name, digests[name])
        header = files["cache"].read_bytes()[:16]
        assert len(header) == 16 and int.from_bytes(header[4:8], "little") == 3
        # The controller's host Python can use a different source-hash key.
        source_hash = subprocess.check_output([
            str(files["python"]), "-B", "-c",
            "import importlib.util, pathlib, sys; "
            "print(importlib.util.source_hash(pathlib.Path(sys.argv[1]).read_bytes()).hex())",
            str(files["parse"]),
        ], text=True).strip()
        assert header[8:16].hex() == source_hash, (side, source_hash)
        identity[side] = {"prefix": str((WORK / side).resolve()), "sha256": digests,
                          "cache_magic": header[:4].hex(), "cache_flags": 3,
                          "cache_source_hash": header[8:16].hex()}
    return identity


def identity_code() -> str:
    control = str((WORK / "control").resolve())
    candidate = str((WORK / "candidate").resolve())
    return (
        "import sys, urllib.parse; "
        "p = sys.prefix; "
        f"assert p in ({control!r}, {candidate!r}); "
        "assert urllib.parse.__file__ == p + '/lib/python3.16/urllib/parse.py'; "
        "m = sys.modules.get('_rust_url_quote'); "
        f"e = None if p == {control!r} else p + '/lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so'; "
        "assert (None if m is None else m.__file__) == e; "
    )


def path_code() -> str:
    return (
        identity_code()
        + "from benchmarks.workloads.catalog_url_breadth import catalog_request_path; "
        "r = catalog_request_path(4000); "
        f"assert r['operation_count'] == 4000 and r['input_digest'] == {EXPECTED_INPUT!r}; "
        f"assert r['digest'] == {EXPECTED_PATH!r}; "
        "print(r['digest'])"
    )


def import_code() -> str:
    # sys is already loaded by interpreter startup. Identity checks use only
    # module attributes; no hashing, filesystem reads, or extra imports.
    return identity_code() + "print('ok')"


def result_row(result: object, phase: str, side: str, round_number: int,
               pair: int, position: int) -> dict[str, object]:
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.cleanup_complete and not result.remaining_pids
    output = result.stdout.decode().strip()
    assert output == (EXPECTED_PATH if phase == "path-memory" else "ok"), output
    memory = None if result.memory is None else result.memory.as_dict()
    if memory is not None:
        assert memory["peak_process_count"] == 1, memory
        assert not memory["sampling_errors"], memory
        assert memory["root_kernel_peak_rss_bytes"] is not None, memory
    return {
        "phase": phase, "side": side, "round": round_number,
        "pair": pair, "position": position,
        "wall_seconds": result.duration_seconds,
        "user_seconds": result.cpu_user_seconds,
        "system_seconds": result.cpu_system_seconds,
        "cpu_coverage": result.cpu_coverage,
        "root_peak_rss_bytes": None if memory is None else memory["root_kernel_peak_rss_bytes"],
        "sampled_peak_footprint_bytes": None if memory is None else memory["peak_phys_footprint_bytes"],
        "sample_count": None if memory is None else len(memory["samples"]),
        "process_count": None if memory is None else memory["peak_process_count"],
        "sampling_errors": None if memory is None else memory["sampling_errors"],
        "output": output,
    }


def run_phase(phase: str, output: Path, previous: Path | None) -> None:
    data = json.loads(previous.read_text()) if previous is not None else {}
    if phase in data:
        raise SystemExit(f"phase already recorded in {previous}: {phase}")
    reserve_evidence(output)
    sys.path.insert(0, str(ROOT))
    from benchmarks.harness.process import run_command
    from benchmarks.harness.runner import workload_environment

    identity = preflight()
    env = workload_environment(None)
    if phase.startswith("import"):
        env.pop("PYTHONPATH", None)
    data["identity"] = identity
    data["environment"] = {key: env.get(key) for key in (
        "PYTHONPATH", "PYTHONHASHSEED", "PYTHONNOUSERSITE",
        "PYTHONDONTWRITEBYTECODE", "PYTHONMALLOC")}
    rows = []
    if phase == "path-memory":
        layouts = (("control", "candidate", 10),
                   ("control", "control", 10),
                   ("candidate", "candidate", 10))
    elif phase == "import-time":
        layouts = (("control", "candidate", 100),
                   ("control", "control", 100),
                   ("candidate", "candidate", 100))
    elif phase == "import-memory":
        layouts = (("control", "candidate", 10),
                   ("control", "control", 10),
                   ("candidate", "candidate", 10))
    else:
        raise ValueError(phase)
    for first, second, count in layouts:
        comparison = first + "-" + second
        # Twenty fresh processes per side in each of five import rounds.
        rounds = 5 if phase == "import-time" else 1
        pairs_per_round = count // rounds
        for round_number in range(rounds):
            for pair in range(pairs_per_round):
                order = (first, second) if (round_number + pair) % 2 == 0 else (second, first)
                for position, side in enumerate(order):
                    command = ([str(paths(side)["python"]), "-B", "-s", "-c", import_code()]
                               if phase.startswith("import") else
                               [str(paths(side)["python"]), "-B", "-s", "-c", path_code()])
                    result = run_command(
                        command, env=env, cwd=ROOT, timeout=30,
                        sample_interval_seconds=None if phase == "import-time" else 0.01)
                    row = result_row(result, phase, side, round_number, pair, position)
                    row["comparison"] = comparison
                    rows.append(row)
                    data[phase] = {"rows": rows}
                    checkpoint_evidence(output, data, sort_keys=True, separators=(",", ":"))
        print(f"{phase} {comparison}: {len(rows)} cumulative children", flush=True)
    data[phase] = {"rows": rows, "pairs_per_comparison": {first + "-" + second: count
                         for first, second, count in layouts},
                   "rounds": 5 if phase == "import-time" else 1}
    checkpoint_evidence(output, data, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--preflight":
        print(json.dumps(preflight(), sort_keys=True))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("phase", choices=("path-memory", "import-time", "import-memory"))
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--previous", type=Path)
        args = parser.parse_args()
        run_phase(args.phase, args.output, args.previous)
