"""Measure whether lean URL quote RSS appears at import or during catalog work.

Run from the repository root. Generated trees and full sampler output stay in
the ignored rust-cpython/work/url-quote-memory-attribution-20260924 directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "rust-cpython/work/url-quote-memory-attribution-20260924"
SOURCE = Path("/Users/josh/d/python-build/rust-cpython/stage-no-rust")
EXPECTED_HASHES = {
    "python": "ecbc7340ff2ffce477c43ac8cf10465b896708c9599112f6adcbde105418da5f",
    "original_parse": "178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825",
    "guarded_parse": "8e29cff7399e7bae9e243bcc022afa43d73ad85912b9468b1e3cc73875079576",
    "extension": "74feaae8a1f52c735a61b94a4abe82daf2f65c4896434aca2b874200ce93a344",
}
EXPECTED_INPUT = "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f"
EXPECTED_OUTPUT = "a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941"
VARIANTS = ("control", "import_only", "candidate")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(prefix: Path) -> dict[str, Path]:
    return {
        "python": prefix / "bin/python3.16",
        "parse": prefix / "lib/python3.16/urllib/parse.py",
        "extension": prefix / "lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so",
    }


def _check_trees() -> dict[str, dict[str, str | None]]:
    hashes = {}
    for variant in VARIANTS:
        paths = _paths(WORK / variant)
        expected_parse = EXPECTED_HASHES["guarded_parse" if variant == "candidate" else "original_parse"]
        actual = {name: _sha256(path) if path.exists() else None for name, path in paths.items()}
        assert actual["python"] == EXPECTED_HASHES["python"], (variant, actual)
        assert actual["parse"] == expected_parse, (variant, actual)
        assert actual["extension"] == (None if variant == "control" else EXPECTED_HASHES["extension"]), (variant, actual)
        hashes[variant] = actual
    source = _paths(SOURCE)
    assert _sha256(source["python"]) == EXPECTED_HASHES["python"]
    assert _sha256(source["parse"]) == EXPECTED_HASHES["original_parse"]
    assert not source["extension"].exists()
    return hashes


def _child(phase: str) -> None:
    import urllib.parse

    prefix = Path(sys.prefix).resolve()
    variant = prefix.name
    assert variant in VARIANTS, prefix
    assert prefix == (WORK / variant).resolve(), prefix
    assert Path(urllib.parse.__file__).resolve() == _paths(prefix)["parse"].resolve()
    if variant == "import_only":
        import _rust_url_quote
    extension = sys.modules.get("_rust_url_quote")
    assert (extension is not None) == (variant != "control")
    if extension is not None:
        assert Path(extension.__file__).resolve() == _paths(prefix)["extension"].resolve()

    payload: dict[str, object] = {
        "phase": phase,
        "variant": variant,
        "prefix": str(prefix),
        "parse_file": str(Path(urllib.parse.__file__).resolve()),
        "extension_file": None if extension is None else str(Path(extension.__file__).resolve()),
    }
    if phase == "catalog":
        from benchmarks.workloads.catalog_url import catalog_url_normalize

        result = catalog_url_normalize(1500)
        assert result["operation_count"] == 1500
        assert result["urls_per_operation"] == result["keys_per_operation"] == 48
        assert result["input_digest"] == EXPECTED_INPUT
        assert result["digest"] == EXPECTED_OUTPUT
        payload.update({key: result[key] for key in (
            "operation_count", "urls_per_operation", "keys_per_operation",
            "input_digest", "digest")})
    elif phase == "import":
        # Keep the fresh process alive long enough for external footprint samples.
        time.sleep(0.12)
    else:
        raise ValueError(phase)
    print(json.dumps(payload, sort_keys=True))


def _memory_row(result: object, phase: str, variant: str, round_number: int) -> dict[str, object]:
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.cleanup_complete and not result.remaining_pids
    payload = json.loads(result.stdout)
    assert payload["phase"] == phase and payload["variant"] == variant
    assert payload["prefix"] == str((WORK / variant).resolve())
    assert payload["parse_file"] == str(_paths(WORK / variant)["parse"].resolve())
    assert payload["extension_file"] == (
        None if variant == "control" else str(_paths(WORK / variant)["extension"].resolve()))
    if phase == "catalog":
        assert payload["operation_count"] == 1500
        assert payload["urls_per_operation"] == payload["keys_per_operation"] == 48
        assert payload["input_digest"] == EXPECTED_INPUT
        assert payload["digest"] == EXPECTED_OUTPUT
    memory = result.memory.as_dict()
    assert memory["peak_process_count"] == 1, memory
    assert not memory["sampling_errors"], memory["sampling_errors"]
    assert memory["root_kernel_peak_rss_bytes"] is not None
    return {
        "phase": phase, "variant": variant, "round": round_number,
        "payload": payload,
        "root_user_seconds": result.cpu_user_seconds,
        "root_system_seconds": result.cpu_system_seconds,
        "cpu_coverage": result.cpu_coverage,
        "root_kernel_peak_rss_bytes": memory["root_kernel_peak_rss_bytes"],
        "root_kernel_peak_phys_footprint_bytes": memory["root_kernel_peak_phys_footprint_bytes"],
        "sampled_peak_phys_footprint_bytes": memory["peak_phys_footprint_bytes"],
        "sampled_peak_rss_bytes": memory["peak_rss_bytes"],
        "process_count": memory["peak_process_count"],
        "sampling_errors": memory["sampling_errors"],
    }


def _controller() -> None:
    sys.path.insert(0, str(ROOT))
    from benchmarks.harness.process import run_command
    from benchmarks.harness.runner import workload_environment

    hashes = _check_trees()
    env = workload_environment(None)
    command_tail = [str(Path(__file__).resolve()), "--child"]
    rows: list[dict[str, object]] = []
    raw: list[dict[str, object]] = []
    for phase in ("catalog", "import"):
        for round_number in range(4):
            order = VARIANTS[round_number % 3:] + VARIANTS[:round_number % 3]
            for variant in order:
                command = [str(_paths(WORK / variant)["python"]), *command_tail, phase]
                result = run_command(command, env=env, cwd=ROOT,
                                     timeout=30, sample_interval_seconds=0.01)
                rows.append(_memory_row(result, phase, variant, round_number))
                raw.append({"phase": phase, "variant": variant, "round": round_number,
                            "result": result.as_dict()})
    (WORK / "raw.json").write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
    summary = {}
    for phase in ("catalog", "import"):
        by_round = {row["round"]: row for row in rows if row["phase"] == phase and row["variant"] == "control"}
        summary[phase] = {}
        for variant in ("import_only", "candidate"):
            differences = [int(row["root_kernel_peak_rss_bytes"]) - int(by_round[row["round"]]["root_kernel_peak_rss_bytes"])
                           for row in rows if row["phase"] == phase and row["variant"] == variant]
            summary[phase][variant] = {"rss_differences_bytes": differences,
                                       "median_rss_difference_bytes": statistics.median(differences)}
    output = {
        "method": "benchmarks.harness.process.run_command, 10 ms external macOS sampler",
        "command_tail": command_tail,
        "environment": {key: env.get(key) for key in (
            "PYTHONPATH", "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "PYTHONMALLOC")},
        "hashes": hashes,
        "expected_input_digest": EXPECTED_INPUT,
        "expected_output_digest": EXPECTED_OUTPUT,
        "rows": rows,
        "paired_summary": summary,
        "raw_path": str(WORK / "raw.json"),
    }
    target = ROOT / "rust-cpython/experiments/data/url-quote-memory-attribution-20260924.json"
    target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        _child(sys.argv[2])
    elif len(sys.argv) == 1:
        _controller()
    else:
        raise SystemExit("usage: python3 url-quote-memory-attribution-20260924.py")
