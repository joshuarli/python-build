"""Hill-climbing verdicts and per-module goals over paired measurements.

An entity is either an application workload measured by
`benchmarks/bench.py` or a module kernel measured by `perf_modules.py`.
Each run yields, per metric, candidate/baseline ratios paired by round and a
bootstrap 95% interval for their median. (`bench.py`'s own `direction`
compares against a 3-sigma per-sample spread, which does not narrow with
more rounds, so a hill climb uses the interval of the paired median.) This
module turns runs into verdicts, one decision per attempt, and goal
statuses against the control. It performs no I/O.

A change counts only when it replicates: a metric is `improved` or
`regressed` when every independent run agrees beyond the practical floor,
and `unstable` when runs disagree in direction. Ratios are candidate over
baseline everywhere, so below 1 is faster or smaller.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Any

# The smallest change worth a commit on this host, applied on top of the
# confidence interval. A 1% floor keeps interval edges that barely clear 1.0
# from ratcheting noise into the incumbent.
PRACTICAL_FLOOR = 0.01
BOOTSTRAP_CONFIDENCE = 0.95
BENCH_MEMORY_METRICS = ("peak_rss", "peak_private", "peak_pss")
WORKLOAD_IMPROVABLE = ("wall", "cpu")
# Per-module goal band against the pristine control: at most 1.0x (with the
# practical floor as measurement slack), and climbing on a route stops once
# it is provably below 0.9x.
GOAL_CEILING = 1.0
GOAL_FLOOR = 0.9
# Module memory values below these sizes are indistinguishable from page
# and allocator granularity; both sides are raised to the floor before a
# ratio is taken, so two negligible values compare as equal.
MODULE_METRIC_FLOORS = {
    "cpu": 0.0,
    "load_footprint": 64 * 1024,
    "working_peak": 256 * 1024,
}
MODULE_SAMPLE_FIELDS = {
    "cpu": "cpu_seconds_per_iteration",
    "load_footprint": "load_footprint_bytes",
    "working_peak": "working_peak_bytes",
}

ACCEPT = "ACCEPT"
REJECT = "REJECT"
NEUTRAL = "NEUTRAL"
INCONCLUSIVE = "INCONCLUSIVE"


def _bootstrap(values: Sequence[float]) -> list[float] | None:
    # Imported lazily: perf.py puts the repository root on sys.path.
    from benchmarks.harness.statistics import bootstrap_median_interval

    return bootstrap_median_interval(values, confidence=BOOTSTRAP_CONFIDENCE)


def classify(interval: Sequence[float] | None, *, floor: float = PRACTICAL_FLOOR) -> str:
    """Classify one run's ratio interval as better, worse, or neutral."""
    if interval is None or len(interval) != 2:
        return "insufficient"
    low, high = float(interval[0]), float(interval[1])
    if high < 1.0 - floor:
        return "better"
    if low > 1.0 + floor:
        return "worse"
    return "neutral"


def replicate(run_classes: Sequence[str]) -> str:
    """Combine per-run classes: agreement is required for any claim."""
    if not run_classes or any(item == "insufficient" for item in run_classes):
        return "insufficient"
    if all(item == "better" for item in run_classes):
        return "improved"
    if all(item == "worse" for item in run_classes):
        return "regressed"
    if "better" in run_classes and "worse" in run_classes:
        return "unstable"
    return "neutral"


def _paired(baseline: Sequence[float], candidate: Sequence[float], floor: float = 0.0) -> list[float]:
    count = min(len(baseline), len(candidate))
    ratios = []
    for index in range(count):
        base, cand = max(float(baseline[index]), floor), max(float(candidate[index]), floor)
        if base > 0:
            ratios.append(cand / base)
    return ratios


def _metric(ratios: list[float], interval: Sequence[float] | None = None,
            values: tuple[Sequence[float], Sequence[float]] | None = None) -> dict[str, Any]:
    if interval is None and len(ratios) >= 2:
        interval = _bootstrap(ratios)
    metric = {"ratios": ratios, "ci95": interval, "class": classify(interval)}
    if values is not None:
        metric["values"] = {"baseline": list(values[0]), "candidate": list(values[1])}
    return metric


# ------------------------------------------------------- run observations


def _memory_class(metric: Mapping[str, Any], floor: float) -> str:
    # bench.py memory rounds are medians, not pairs: use its repeatability
    # bound and require the practical floor as well.
    ratio = metric.get("ratio_candidate_over_baseline")
    change = metric.get("absolute_change")
    allowance = metric.get("noise_allowance")
    if metric.get("status") == "inconclusive" or not isinstance(ratio, (int, float)):
        return "insufficient"
    if not isinstance(change, (int, float)) or not isinstance(allowance, (int, float)):
        return "insufficient"
    if ratio > 1.0 + floor and change > allowance:
        return "worse"
    if ratio < 1.0 - floor and -change > allowance:
        return "better"
    return "neutral"


def run_observation(workload: Mapping[str, Any], *, floor: float = PRACTICAL_FLOOR) -> dict[str, Any]:
    """One bench.py run of one application workload."""
    timing = workload["comparison"]["timing"]
    metrics: dict[str, Any] = {
        "wall": _metric([float(value) for value in timing.get("paired_ratio_samples") or []],
                        timing.get("median_ratio_ci95")),
    }
    cpu = timing.get("cpu")
    cpu_metric = cpu.get("metrics", {}).get("total_seconds_per_operation") \
        if isinstance(cpu, Mapping) and cpu.get("status") == "compared" else None
    metrics["cpu"] = _metric(_paired(cpu_metric.get("baseline_samples") or [],
                                     cpu_metric.get("candidate_samples") or [])
                             if isinstance(cpu_metric, Mapping) else [])
    # The harness's 3-sigma timing failure is an independent regression
    # signal; keep it even when the interval stays inside the floor.
    if timing.get("status") == "fail" and metrics["wall"]["class"] == "neutral":
        metrics["wall"]["class"] = "worse"
    memory = workload["comparison"].get("memory", {})
    for name in BENCH_MEMORY_METRICS:
        metric = memory.get("metrics", {}).get(name) if isinstance(memory, Mapping) else None
        if isinstance(metric, Mapping):
            ratio = metric.get("ratio_candidate_over_baseline")
            metrics[name] = {"ratios": [ratio] if isinstance(ratio, (int, float)) else [],
                             "ci95": None, "class": _memory_class(metric, floor)}
    return {"kind": "workload", "metrics": metrics, "mismatch": False}


def module_observation(baseline: Sequence[Mapping[str, Any]],
                       candidate: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One run of one module kernel: samples paired by round."""
    digests = {sample["digest"] for sample in [*baseline, *candidate]}
    metrics = {}
    for name, field in MODULE_SAMPLE_FIELDS.items():
        base = [float(sample[field]) for sample in baseline]
        cand = [float(sample[field]) for sample in candidate]
        metrics[name] = _metric(_paired(base, cand, MODULE_METRIC_FLOORS[name]), values=(base, cand))
    return {"kind": "module", "metrics": metrics, "mismatch": len(digests) != 1}


def mismatch_observation(kind: str) -> dict[str, Any]:
    """The two interpreters produced different outputs; nothing was timed."""
    return {"kind": kind, "metrics": {}, "mismatch": True}


# ---------------------------------------------------------------- verdicts


def entity_verdict(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Replicate one entity's per-run observations into metric verdicts."""
    kind = runs[0]["kind"] if runs else "workload"
    names = list(dict.fromkeys(name for run in runs for name in run["metrics"]))
    metrics = {}
    for name in names:
        classes = [run["metrics"].get(name, {}).get("class", "insufficient") for run in runs]
        ratios = [value for run in runs for value in run["metrics"].get(name, {}).get("ratios", [])]
        values = {side: [value for run in runs
                         for value in run["metrics"].get(name, {}).get("values", {}).get(side, [])]
                  for side in ("baseline", "candidate")}
        metrics[name] = {
            "verdict": replicate(classes),
            "per_run": classes,
            "per_run_ci95": [run["metrics"].get(name, {}).get("ci95") for run in runs],
            "pooled": {
                "median": float(statistics.median(ratios)) if ratios else None,
                "ci95": _bootstrap(ratios) if len(ratios) >= 2 else None,
                "samples": len(ratios),
                **({f"{side}_median": float(statistics.median(found)) for side, found in values.items()}
                   if all(values.values()) else {}),
            },
        }
    return {
        "kind": kind,
        "runs": len(runs),
        "mismatch": any(run["mismatch"] for run in runs),
        "improvable": list(MODULE_SAMPLE_FIELDS if kind == "module" else WORKLOAD_IMPROVABLE),
        "metrics": metrics,
    }


def goal_status(verdict: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a module verdict (candidate over control) against the band.

    Per metric: OVER when every run's interval sits above the ceiling plus
    the floor; BEYOND when every run's interval sits below 0.9x; MET when
    the pooled median is at or under the ceiling plus the floor; otherwise
    UNCLEAR. The module is OVER if any metric is, UNCLEAR if any is, BEYOND
    only if all are, and MET otherwise.
    """
    if verdict.get("mismatch"):
        return {"status": "MISMATCH", "metrics": {}}
    metrics = {}
    for name, detail in verdict["metrics"].items():
        intervals = detail["per_run_ci95"]
        median = detail["pooled"]["median"]
        if intervals and all(ci and ci[0] > GOAL_CEILING + PRACTICAL_FLOOR for ci in intervals):
            status = "OVER"
        elif intervals and all(ci and ci[1] < GOAL_FLOOR for ci in intervals):
            status = "BEYOND"
        elif median is not None and median <= GOAL_CEILING + PRACTICAL_FLOOR:
            status = "MET"
        else:
            status = "UNCLEAR"
        metrics[name] = status
    values = set(metrics.values())
    overall = ("OVER" if "OVER" in values else "UNCLEAR" if "UNCLEAR" in values or not values
               else "BEYOND" if values == {"BEYOND"} else "MET")
    return {"status": overall, "metrics": metrics}


def _every(runs: int) -> str:
    return "the only run" if runs == 1 else f"all {runs} runs"


def decide(entities: Mapping[str, Mapping[str, Any]], *, targets: Sequence[str],
           runs: int, quiet: bool, gate: bool,
           known_mismatches: Sequence[str] = ()) -> dict[str, Any]:
    """Decide one attempt from replicated entity verdicts.

    REJECT: any evaluated entity regresses a metric in every run, or its
    outputs differ from the baseline (outside `known_mismatches`).
    INCONCLUSIVE: the host was not quiet, a metric is unstable across runs,
    a target lacks samples, or a gate decision has fewer than two runs.
    ACCEPT: a target improves an improvable metric with no rejection.
    Otherwise NEUTRAL.
    """
    reasons: list[str] = []
    regressions, unstable, mismatches = [], [], []
    for name, verdict in sorted(entities.items()):
        if verdict["mismatch"]:
            if name not in known_mismatches:
                mismatches.append(name)
            continue
        for metric, detail in verdict["metrics"].items():
            if detail["verdict"] == "regressed":
                regressions.append(f"{name} {metric}")
            elif detail["verdict"] == "unstable":
                unstable.append(f"{name} {metric}")
    missing = sorted(set(targets) - set(entities))
    insufficient = sorted(
        name for name in targets if name in entities and not entities[name]["mismatch"]
        and all(entities[name]["metrics"].get(metric, {}).get("verdict", "insufficient") == "insufficient"
                for metric in entities[name]["improvable"])
    )
    improved = sorted(
        f"{name} {metric}" for name in targets if name in entities
        for metric in entities[name]["improvable"]
        if entities[name]["metrics"].get(metric, {}).get("verdict") == "improved"
    )
    if mismatches:
        decision = REJECT
        reasons.append("outputs differ from the baseline: " + ", ".join(mismatches))
    elif regressions:
        decision = REJECT
        reasons.append(f"regressed in {_every(runs)}: " + ", ".join(regressions))
    elif not quiet:
        decision = INCONCLUSIVE
        reasons.append("host was not quiet during measurement")
    elif gate and runs < 2:
        decision = INCONCLUSIVE
        reasons.append("a gate decision needs at least two independent runs")
    elif missing or insufficient:
        decision = INCONCLUSIVE
        reasons.append("targets lack samples: " + ", ".join([*missing, *insufficient]))
    elif unstable:
        decision = INCONCLUSIVE
        reasons.append("runs disagree in direction: " + ", ".join(unstable))
    elif improved:
        decision = ACCEPT
        reasons.append(f"improved in {_every(runs)}: " + ", ".join(improved))
    else:
        decision = NEUTRAL
        reasons.append("no target improved beyond the interval and practical floor")
    known = sorted(name for name in known_mismatches if entities.get(name, {}).get("mismatch"))
    if known:
        reasons.append("documented output differences, not timed: " + ", ".join(known))
    if not gate:
        reasons.append("exploratory: not acceptance evidence")
    return {
        "decision": decision,
        "gate": gate,
        "runs": runs,
        "quiet": quiet,
        "practical_floor": PRACTICAL_FLOOR,
        "targets": list(targets),
        "improved": improved,
        "regressions": regressions,
        "unstable": unstable,
        "mismatches": mismatches,
        "reasons": reasons,
    }


def calibration(entities: Mapping[str, Mapping[str, Any]], *, runs: int, quiet: bool,
                gate: bool) -> dict[str, Any]:
    """Judge a self-comparison: identical interpreters must read neutral.

    Any improvement, regression, unstable metric, or output mismatch means
    the harness can report a difference that does not exist at this floor
    and run count.
    """
    differences = sorted(
        [f"{name}: outputs differ" for name, verdict in entities.items() if verdict["mismatch"]]
        + [f"{name} {metric}: {detail['verdict']}"
           for name, verdict in entities.items()
           for metric, detail in verdict["metrics"].items()
           if detail["verdict"] in {"improved", "regressed", "unstable"}]
    )
    if not quiet:
        outcome, reasons = "CALIBRATION-INCONCLUSIVE", ["host was not quiet during measurement"]
    elif differences:
        outcome, reasons = "CALIBRATION-FAILED", ["identical interpreters read different: "
                                                  + ", ".join(differences)]
    else:
        outcome, reasons = "CALIBRATION-OK", ["identical interpreters read neutral everywhere"]
    return {
        "decision": outcome,
        "gate": gate,
        "runs": runs,
        "quiet": quiet,
        "practical_floor": PRACTICAL_FLOOR,
        "targets": [],
        "improved": [],
        "regressions": [],
        "unstable": [],
        "mismatches": [],
        "differences": differences,
        "reasons": reasons,
    }


# --------------------------------------------------------------- rendering


def _format_metric(name: str, detail: Mapping[str, Any]) -> str:
    median = detail["pooled"]["median"]
    interval = detail["pooled"]["ci95"]
    if median is None:
        value = "n/a"
    elif interval:
        value = f"{median:.3f}[{interval[0]:.3f},{interval[1]:.3f}]"
    else:
        value = f"{median:.3f}"
    return f"{name} {value} {detail['verdict']}"


def render(entities: Mapping[str, Mapping[str, Any]], decision: Mapping[str, Any],
           goals: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    """One line per entity, then the decision and commit-message-ready reasons."""
    lines = []
    width = max([len(name) for name in entities] + [12]) + 1
    for name, verdict in sorted(entities.items(), key=lambda item: (item[1]["kind"], item[0])):
        marker = "*" if name in decision["targets"] else " "
        goal = f"  GOAL {goals[name]['status']}" if goals and name in goals else ""
        if verdict["mismatch"]:
            body = "outputs differ from the baseline; not timed"
        else:
            body = " | ".join(_format_metric(metric, detail) for metric, detail in verdict["metrics"].items())
        lines.append(f"{marker}{name:<{width}} {body}{goal}")
    lines.append("")
    lines.append(f"DECISION: {decision['decision']} ({'gate' if decision['gate'] else 'explore'}, "
                 f"{decision['runs']} run(s), floor {decision['practical_floor']:.0%}, "
                 f"quiet={'yes' if decision['quiet'] else 'no'}; * = target; ratios candidate/baseline)")
    lines.extend(f"  - {reason}" for reason in decision["reasons"])
    return "\n".join(lines)


def render_goals(goals: Mapping[str, Mapping[str, Any]],
                 entities: Mapping[str, Mapping[str, Any]]) -> str:
    """Goal table against the control, worst first, with status counts."""
    order = {"MISMATCH": 0, "OVER": 1, "UNCLEAR": 2, "MET": 3, "BEYOND": 4}

    def worst(name: str) -> float:
        medians = [detail["pooled"]["median"] or 0.0 for detail in entities[name]["metrics"].values()]
        return -max(medians, default=0.0)

    def absolute(metric: str, pooled: Mapping[str, Any]) -> str:
        if "candidate_median" not in pooled:
            return ""
        base, cand = pooled["baseline_median"], pooled["candidate_median"]
        if metric == "cpu":
            return f" ({cand * 1e3:.3g}/{base * 1e3:.3g} ms)"
        return f" ({cand / 1024:.0f}/{base / 1024:.0f} KiB)"

    lines = []
    for name in sorted(goals, key=lambda item: (order[goals[item]["status"]], worst(item))):
        metrics = entities[name]["metrics"]
        body = " | ".join(
            f"{metric} {(metrics[metric]['pooled']['median'] or 0):.2f}x{absolute(metric, metrics[metric]['pooled'])}"
            f" {status}"
            for metric, status in goals[name]["metrics"].items()
        ) or "outputs differ from the control"
        lines.append(f"{goals[name]['status']:<8} {name:<24} {body}")
    counts = {status: sum(goal["status"] == status for goal in goals.values()) for status in order}
    lines.append("")
    lines.append("GOALS (candidate/control; ceiling 1.0x, target floor 0.9x): "
                 + ", ".join(f"{status} {count}" for status, count in counts.items() if count))
    return "\n".join(lines)
