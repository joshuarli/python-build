"""Bounded same-extension diagnostic for the quote cache priming cost."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "rust-cpython/work/url-quote-cache-cost-20260925"
PYTHON = Path("/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16")
EXTENSION = WORK / "native/_rust_url_quote.cpython-316-darwin.so"
EXPECTED = {
    "catalog_search_form": (500, "a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22"),
    "catalog_request_path": (1000, "52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff"),
}
INPUT_DIGEST = "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host() -> dict[str, object]:
    swap = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True).strip()
    top = subprocess.check_output(["ps", "-axo", "pid,pcpu,rss,comm"], text=True).splitlines()
    busy = sorted((line.strip() for line in top[1:]),
                  key=lambda line: float(line.split()[1]), reverse=True)[:3]
    return {"load_average": os.getloadavg(), "swap": swap, "top_processes": busy}


def run(task: str, side: str, pair: int, position: int) -> dict[str, object]:
    iterations, expected_digest = EXPECTED[task]
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join((str(WORK / side), str(WORK / "native"), str(ROOT))),
               PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="1")
    argv = [str(PYTHON), "-B", "-m", "benchmarks.workloads.catalog_url_breadth",
            task, "--iterations", str(iterations)]
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    pid, status, usage = os.wait4(proc.pid, 0)
    wall = time.monotonic() - started
    assert pid == proc.pid
    stdout = proc.stdout.read().decode() if proc.stdout else ""
    stderr = proc.stderr.read().decode() if proc.stderr else ""
    code = os.waitstatus_to_exitcode(status)
    record: dict[str, object] = {
        "id": f"{task}-{pair}-{position}", "task": task, "side": side,
        "pair": pair, "position": position, "returncode": code,
        "wall_seconds": wall, "user_seconds": usage.ru_utime,
        "system_seconds": usage.ru_stime, "peak_rss_bytes": usage.ru_maxrss,
        "swap_count": usage.ru_nswap,
    }
    try:
        result = json.loads(stdout)
        record["output_digest"] = result["digest"]
        record["input_digest"] = result["input_digest"]
        record["operation_count"] = result["operation_count"]
        record["valid"] = (code == 0 and result["digest"] == expected_digest
                           and result["input_digest"] == INPUT_DIGEST
                           and result["operation_count"] == iterations)
    except (ValueError, KeyError, TypeError):
        record["valid"] = False
        record["stdout_excerpt"] = stdout[:400]
    if stderr:
        record["stderr_excerpt"] = stderr[:400]
    return record


def native_hit_count(task: str, side: str) -> dict[str, object]:
    code = (
        "import json, statistics, _rust_url_quote, urllib.parse; "
        "from benchmarks.workloads import catalog_url_breadth as work; "
        "counts={}; lengths=[]; original=_rust_url_quote.quote_bytes; "
        "def_text='def spy(bs, safe):\\n"
        "    counts[safe.hex()] = counts.get(safe.hex(), 0) + 1\\n"
        "    lengths.append(len(bs))\\n"
        "    return original(bs, safe)'; "
        "exec(def_text); _rust_url_quote.quote_bytes=spy; "
        "urllib.parse._byte_quoter_factory.cache_clear(); "
        f"result=work.{task}(1); "
        "print(json.dumps({'side':" + repr(side) + ", 'task':" + repr(task)
        + ", 'native_calls_by_safe_hex':counts, 'digest':result['digest'],"
        " 'input_digest':result['input_digest'],"
        " 'native_length_summary':{'min':min(lengths) if lengths else None,"
        " 'median':statistics.median(lengths) if lengths else None,"
        " 'max':max(lengths) if lengths else None,"
        " 'bins':{'lt16':sum(n<16 for n in lengths),"
        " '16to63':sum(16<=n<64 for n in lengths),"
        " '64to255':sum(64<=n<256 for n in lengths),"
        " 'ge256':sum(n>=256 for n in lengths)}}}, sort_keys=True))"
    )
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join((str(WORK / side), str(WORK / "native"), str(ROOT))),
               PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="1")
    result = subprocess.run([str(PYTHON), "-B", "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=True)
    parsed = json.loads(result.stdout)
    if parsed["digest"] != EXPECTED[task][1] or parsed["input_digest"] != INPUT_DIGEST:
        raise SystemExit("native hit count workload output changed")
    return parsed


def cache_edit_observation(side: str) -> dict[str, object]:
    code = """
import json
import sys
import urllib.parse as parse
import _rust_url_quote

hits = []
original = _rust_url_quote.quote_bytes
def spy(value, safe):
    hits.append((len(value), safe.hex()))
    return original(value, safe)
_rust_url_quote.quote_bytes = spy

def reset():
    parse._byte_quoter_factory.cache_clear()
    hits.clear()

reset()
fresh = parse.quote_from_bytes(b'x y', safe=b'/')
fresh_keys = list(parse._byte_quoter_factory(b'/').__self__)
fresh_hits = len(hits)

reset()
parse._byte_quoter_factory(b'/').__self__[32] = '<edited>'
edited = parse.quote_from_bytes(b'x y', safe=b'/')
edited_hits = len(hits)

reset()
parse._byte_quoter_factory(b'/').__self__[32] = object()
try:
    parse.quote_from_bytes(b'x y', safe=b'/')
except Exception as error:
    exception = [type(error).__name__, str(error)]
else:
    exception = None
exception_hits = len(hits)

reset()
one_byte = parse.quote_from_bytes(b' ', safe=b'/')
one_byte_hits = len(hits)

reset()
sys.settrace(lambda *args: None)
try:
    traced = parse.quote_from_bytes(b'x y', safe=b'/')
finally:
    sys.settrace(None)
trace_hits = len(hits)

reset()
sys.setprofile(lambda *args: None)
try:
    profiled = parse.quote_from_bytes(b'x y', safe=b'/')
finally:
    sys.setprofile(None)
profile_hits = len(hits)

print(json.dumps(dict(fresh=fresh, fresh_private_cache_keys=fresh_keys,
    fresh_native_hits=fresh_hits, edited=edited, edited_native_hits=edited_hits,
    exception=exception, exception_native_hits=exception_hits,
    one_byte=one_byte, one_byte_native_hits=one_byte_hits,
    traced=traced, trace_native_hits=trace_hits,
    profiled=profiled, profile_native_hits=profile_hits), sort_keys=True))
"""
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join((str(WORK / side), str(WORK / "native"), str(ROOT))),
               PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="1")
    result = subprocess.run([str(PYTHON), "-B", "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=True)
    return {"side": side, **json.loads(result.stdout)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", choices=("pre-primed", "baseline-primed", "pre-baseline", "native-hits", "native-lengths", "cache-edits"),
                        default="pre-primed")
    args = parser.parse_args()
    pre = (WORK / "pre/urllib/parse.py").read_text()
    primed = (WORK / "primed/urllib/parse.py").read_text()
    loop = "        for byte in _rust_url_dict_fromkeys(bs):\n            quoter(byte)\n"
    if primed.count(loop) != 1 or primed.replace(loop, "", 1) != pre:
        raise SystemExit("parser overlays differ beyond cache priming")
    identities = {
        "interpreter_sha256": sha256(PYTHON), "extension_sha256": sha256(EXTENSION),
        "pre_parse_sha256": sha256(WORK / "pre/urllib/parse.py"),
        "primed_parse_sha256": sha256(WORK / "primed/urllib/parse.py"),
    }
    evidence_path = ROOT / "rust-cpython/experiments/data/url-quote-cache-cost-20260925.json"
    if args.comparison == "cache-edits":
        prior = json.loads(evidence_path.read_text())
        if prior["identities"] != identities or "cache_edit_observations" in prior:
            raise SystemExit("prior identities changed or cache edit observations exist")
        revised = WORK / "revised/urllib/parse.py"
        expected = (WORK / "revised-source/Lib/urllib/parse.py").read_bytes()
        if revised.read_bytes() != expected:
            raise SystemExit("revised overlay differs from revised patch source")
        observations = [cache_edit_observation(side) for side in ("baseline", "revised")]
        public_fields = ("fresh", "edited", "exception", "one_byte", "traced", "profiled")
        if any(observations[0][field] != observations[1][field] for field in public_fields):
            raise SystemExit("revised public output or exception differs from pure parser")
        if any(observations[1][field] for field in ("edited_native_hits",
                                                     "exception_native_hits",
                                                     "one_byte_native_hits",
                                                     "trace_native_hits",
                                                     "profile_native_hits")):
            raise SystemExit("revised guard reached native code after fallback condition")
        prior["revised_patch_sha256"] = sha256(ROOT / "rust-cpython/patches/0001-rust-url-quote.patch")
        prior["revised_parse_sha256"] = sha256(revised)
        prior["cache_edit_observations"] = observations
        evidence_path.write_text(json.dumps(prior, indent=2) + "\n")
        return
    if args.comparison == "native-hits":
        prior = json.loads(evidence_path.read_text())
        if prior["identities"] != identities or "native_hit_counts" in prior:
            raise SystemExit("prior identities changed or hit counts exist")
        prior["native_hit_counts"] = [native_hit_count(task, side)
                                      for task in EXPECTED for side in ("pre", "primed")]
        evidence_path.write_text(json.dumps(prior, indent=2) + "\n")
        return
    if args.comparison == "native-lengths":
        prior = json.loads(evidence_path.read_text())
        if prior["identities"] != identities or "native_length_observations" in prior:
            raise SystemExit("prior identities changed or lengths exist")
        prior["native_length_observations"] = [native_hit_count(task, side)
                                               for task in EXPECTED for side in ("pre", "primed")]
        evidence_path.write_text(json.dumps(prior, indent=2) + "\n")
        return
    baseline_comparison = args.comparison in ("baseline-primed", "pre-baseline")
    data_key = ("baseline_comparison" if args.comparison == "baseline-primed"
                else "pre_baseline_comparison")
    if baseline_comparison:
        if sha256(WORK / "baseline/urllib/parse.py") != sha256(
                Path("/Users/josh/d/python-build/rust-cpython/stage/lib/python3.16/urllib/parse.py")):
            raise SystemExit("baseline overlay differs from pinned installed source")
        evidence = json.loads(evidence_path.read_text())
        if evidence["identities"] != identities or data_key in evidence:
            raise SystemExit("prior identities changed or baseline comparison exists")
        evidence = {
            "identities": identities | {"baseline_parse_sha256": sha256(WORK / "baseline/urllib/parse.py")},
            "command": "stage/bin/python3.16 -B -m benchmarks.workloads.catalog_url_breadth TASK --iterations N",
            "environment": "PYTHONPATH=SIDE:NATIVE:ROOT; PYTHONDONTWRITEBYTECODE=1; PYTHONHASHSEED=1",
            "cache_policy": "Both parser overlays have no __pycache__; -B and DONTWRITEBYTECODE=1; source compiled at each import",
            "accounting": "os.wait4 direct workload child; no workload descendants; host sampled outside workload runs",
            "host_before": host(), "attempts": [], "pair_host": [],
        }
    else:
        evidence = {
            "identities": identities,
            "command": "stage/bin/python3.16 -B -m benchmarks.workloads.catalog_url_breadth TASK --iterations N",
            "environment": "PYTHONPATH=SIDE:NATIVE:ROOT; PYTHONDONTWRITEBYTECODE=1; PYTHONHASHSEED=1",
            "cache_policy": "Both parser overlays have no __pycache__; -B and DONTWRITEBYTECODE=1; source compiled at each import",
            "accounting": "os.wait4 direct workload child; no workload descendants; host sampled outside workload runs",
            "host_before": host(), "attempts": [], "pair_host": [],
        }
    attempts = evidence["attempts"]
    pair_host = evidence["pair_host"]
    assert isinstance(attempts, list) and isinstance(pair_host, list)
    for task in EXPECTED:
        for pair in range(3):
            pair_host.append({"task": task, "pair": pair, "before": host()})
            sides = (("baseline", "primed") if args.comparison == "baseline-primed"
                     else ("baseline", "pre") if args.comparison == "pre-baseline"
                     else ("pre", "primed"))
            order = sides if pair % 2 == 0 else tuple(reversed(sides))
            for position, side in enumerate(order):
                record = run(task, side, pair, position)
                attempts.append(record)
                if not record["valid"]:
                    evidence["host_after"] = host()
                    if baseline_comparison:
                        prior = json.loads(evidence_path.read_text())
                        prior[data_key] = evidence
                        evidence_path.write_text(json.dumps(prior, indent=2) + "\n")
                    else:
                        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
                    raise SystemExit(f"invalid attempt: {record['id']}")
    evidence["host_after"] = host()
    if baseline_comparison:
        prior = json.loads(evidence_path.read_text())
        prior[data_key] = evidence
        evidence_path.write_text(json.dumps(prior, indent=2) + "\n")
    else:
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
