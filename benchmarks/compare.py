"""Head-to-head pyperformance comparison: ours vs Astral PBS (musl x86-64).

Stdlib only, so it runs anywhere without extra installs. Methodology
follows the plot script from astral-sh/python-build-standalone PR #1192
(jjhelmus/cpython-benchmarks plot_pbs_314_comparison.py): per-benchmark
ratio of mean runtimes, verdict on the geometric mean.

Ratio direction: ratio = mean(ours) / mean(pbs). A ratio < 1 means our
build was faster on that benchmark; the geometric mean over the suite is
1.00 for identical performance. PASS requires the geometric mean within
[0.99, 1.01], i.e. +-1%.

bench_mp_pool is excluded from the verdict (as in the upstream figure: it
is timing-sensitive under shared/containerized hosts) but its ratio is
still printed so nothing is hidden. Benchmarks present in only one file
are listed and ignored.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

EXCLUDED_FROM_VERDICT = {"bench_mp_pool"}
TOLERANCE = 0.01


def load_means(path: Path) -> dict[str, float]:
    """Per-benchmark mean runtime over all recorded values in the file."""
    suite = json.loads(Path(path).read_text(encoding="utf-8"))
    top_name = suite.get("metadata", {}).get("name")
    means: dict[str, float] = {}
    for benchmark in suite["benchmarks"]:
        meta = benchmark.get("metadata") or {}
        name = meta.get("name") or top_name
        if not name:
            raise ValueError(f"benchmark without a name in {path}")
        if name in means:
            raise ValueError(f"duplicate benchmark {name!r} in {path}")
        values = [v for run in benchmark["runs"] for v in run.get("values", ())]
        if not values:
            continue
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError(f"invalid timing values for {name!r} in {path}")
        means[name] = sum(values) / len(values)
    if not means:
        raise ValueError(f"no benchmark timings in {path}")
    return means


def compare(pbs_path: Path, ours_path: Path) -> dict:
    """Compare one pair of pyperformance result files."""
    pbs = load_means(pbs_path)
    ours = load_means(ours_path)
    common = sorted(set(pbs) & set(ours))
    if not common:
        raise ValueError("no benchmarks in common")
    ratios = {name: ours[name] / pbs[name] for name in common}
    verdict_names = [n for n in common if n not in EXCLUDED_FROM_VERDICT]
    if not verdict_names:
        raise ValueError("no benchmarks left after exclusions")
    geomean = math.exp(
        sum(math.log(ratios[n]) for n in verdict_names) / len(verdict_names)
    )
    excluded = {n: ratios[n] for n in common if n in EXCLUDED_FROM_VERDICT}
    return {
        "pbs_file": str(pbs_path),
        "ours_file": str(ours_path),
        "benchmarks": len(common),
        "ratios": ratios,
        "excluded_from_verdict": excluded,
        "pbs_only": sorted(set(pbs) - set(ours)),
        "ours_only": sorted(set(ours) - set(pbs)),
        "geomean_ours_over_pbs": geomean,
        "delta_pct": (geomean - 1.0) * 100.0,
        "tolerance_pct": TOLERANCE * 100.0,
        "pass": abs(geomean - 1.0) <= TOLERANCE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbs_json", type=Path, help="pyperformance result (PBS)")
    parser.add_argument("ours_json", type=Path, help="pyperformance result (ours)")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        report = compare(args.pbs_json, args.ours_json)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for name in sorted(report["ratios"]):
        flag = " (excluded from verdict)" if name in report["excluded_from_verdict"] else ""
        print(f"{name:40s} {report['ratios'][name]:.4f}{flag}")
    if report["pbs_only"]:
        print(f"pbs-only (ignored): {', '.join(report['pbs_only'])}")
    if report["ours_only"]:
        print(f"ours-only (ignored): {', '.join(report['ours_only'])}")
    print(
        f"geomean ours/pbs: {report['geomean_ours_over_pbs']:.4f} "
        f"({report['delta_pct']:+.2f}%), n={report['benchmarks']}, "
        f"tolerance +-1.00%: {'PASS' if report['pass'] else 'FAIL'}"
    )
    if args.json_out is not None:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
