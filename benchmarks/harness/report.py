"""Machine-readable and Markdown summaries for benchmark comparisons."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .models import RESULT_SCHEMA_VERSION, summary_to_json, validate_summary
from .statistics import compare_workload


def _display_name(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, Mapping):
        for key in ("label", "name", "kind", "version"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
    return default


def _percent_value(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _comparison_value(workload: Mapping[str, Any], *path: str) -> Any:
    value: Any = workload
    for component in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(component)
    return value


def _workload_status(workload: Mapping[str, Any]) -> str:
    verdict = workload.get("verdict")
    if isinstance(verdict, Mapping):
        status = verdict.get("overall")
        if isinstance(status, str):
            return status
    return "incomplete"


def _primary_memory_metric(workload: Mapping[str, Any]) -> str:
    metric = _comparison_value(workload, "comparison", "memory", "primary_metric")
    return metric if metric in {"peak_pss", "peak_rss"} else "peak_pss"


def _workload_metrics(workload: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "time_change_percent": _percent_value(
            _comparison_value(workload, "comparison", "timing", "change_percent")
        ),
        "peak_memory_change_percent": _percent_value(
            _comparison_value(workload, "comparison", "memory", "metrics", _primary_memory_metric(workload), "change_percent")
        ),
        "peak_pss_change_percent": _percent_value(
            _comparison_value(workload, "comparison", "memory", "metrics", "peak_pss", "change_percent")
        ),
        "bytes_per_operation_change_percent": _percent_value(
            _comparison_value(workload, "comparison", "allocations", "metrics", "bytes_per_operation", "change_percent")
        ),
    }


def _median_ratios(workloads: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    paths = {
        "time_candidate_over_baseline": ("comparison", "timing", "time_ratio"),
        "peak_memory_candidate_over_baseline": (
            "comparison", "memory", "metrics", "peak_pss", "ratio_candidate_over_baseline"
        ),
        "peak_pss_candidate_over_baseline": (
            "comparison", "memory", "metrics", "peak_pss", "ratio_candidate_over_baseline"
        ),
        "bytes_per_operation_candidate_over_baseline": (
            "comparison", "allocations", "metrics", "bytes_per_operation", "ratio_candidate_over_baseline"
        ),
    }
    ratios: dict[str, float | None] = {}
    for name, path in paths.items():
        values = [
            float(value)
            for workload in workloads
            if (value := _comparison_value(
                workload, *(path[:3] + (_primary_memory_metric(workload),) + path[4:])
                if name == "peak_memory_candidate_over_baseline" else path
            )) is not None
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ]
        ratios[name] = _median(values)
    return ratios


def build_summary(
    workloads: Sequence[Mapping[str, Any]],
    *,
    baseline: Any,
    candidate: Any,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the documented summary document from compared workloads."""
    summary: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "baseline": baseline,
        "candidate": candidate,
        "workloads": [dict(workload) for workload in workloads],
    }
    if provenance is not None:
        summary["provenance"] = dict(provenance)
    return _enrich_summary(summary)


def _enrich_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(value)
    workloads = list(summary.get("workloads", ()))
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for workload in workloads:
        identity = workload.get("identity", {})
        category = identity.get("category", "uncategorized") if isinstance(identity, Mapping) else "uncategorized"
        grouped[str(category)].append(workload)

    categories: dict[str, Any] = {}
    for category, members in sorted(grouped.items()):
        metric_values: dict[str, list[float]] = {
            "time_change_percent": [],
            "peak_memory_change_percent": [],
            "peak_pss_change_percent": [],
            "bytes_per_operation_change_percent": [],
        }
        for workload in members:
            for name, metric in _workload_metrics(workload).items():
                if metric is not None and math.isfinite(metric):
                    metric_values[name].append(metric)
        categories[category] = {
            "workload_count": len(members),
            "verdicts": _verdict_counts(members),
            "median_changes_percent": {
                name: _median(values) for name, values in metric_values.items()
            },
        }

    summary["categories"] = categories
    all_metric_values: dict[str, list[float]] = {
        "time_change_percent": [],
        "peak_memory_change_percent": [],
        "peak_pss_change_percent": [],
        "bytes_per_operation_change_percent": [],
    }
    for workload in workloads:
        for name, metric in _workload_metrics(workload).items():
            if metric is not None and math.isfinite(metric):
                all_metric_values[name].append(metric)
    summary["aggregate"] = {
        "workload_count": len(workloads),
        "verdicts": _verdict_counts(workloads),
        "median_changes_percent": {
            name: _median(values) for name, values in all_metric_values.items()
        },
        "median_ratios_candidate_over_baseline": _median_ratios(workloads),
        "decision_authority": "per-workload verdicts; medians are descriptive",
    }
    macro_status = _aggregate_status(workloads) if workloads else "not_run"
    summary["verdict"] = {
        # Pyperformance remains a diagnostic layer. The top-level overall
        # status describes repository-owned macro verdicts only.
        "overall": macro_status,
        "macro": {
            "status": macro_status,
            "workload_count": len(workloads),
            "decision_authority": "repository-owned workload verdicts",
        },
        "pyperformance": _pyperformance_status(summary),
        "workloads": _verdict_counts(workloads),
    }
    return summary


def _verdict_counts(workloads: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for workload in workloads:
        counts[_workload_status(workload)] += 1
    return dict(sorted(counts.items()))


def _aggregate_status(workloads: Sequence[Mapping[str, Any]]) -> str:
    statuses = [_workload_status(workload) for workload in workloads]
    if not statuses:
        return "incomplete"
    if "fail" in statuses:
        return "fail"
    if any(status not in ("pass",) for status in statuses):
        return "incomplete"
    return "pass"


def _pyperformance_status(summary: Mapping[str, Any]) -> dict[str, Any]:
    pyperformance = summary.get("pyperformance")
    if not isinstance(pyperformance, Mapping):
        return {
            "status": "not_run",
            "coverage_status": "not_run",
            "benchmark_count": 0,
            "timing_compared": 0,
            "memory_compared": 0,
            "failure_counts": {"baseline": 0, "candidate": 0},
            "significant_timing_regressions": 0,
            "decision_authority": "diagnostic_only",
        }

    counts = _pyperformance_counts(summary)
    total = counts["benchmarks"]
    failures = counts["baseline_failures"] + counts["candidate_failures"]
    if total == 0:
        coverage_status = "no_results"
    elif (
        counts["timing_compared"] == total
        and counts["memory_compared"] == total
        and failures == 0
    ):
        coverage_status = "complete"
    elif counts["timing_compared"] == 0 and counts["memory_compared"] == 0:
        coverage_status = "no_comparable_results"
    else:
        coverage_status = "partial"
    return {
        "status": "informational",
        "coverage_status": coverage_status,
        "benchmark_count": total,
        "timing_compared": counts["timing_compared"],
        "memory_compared": counts["memory_compared"],
        "failure_counts": {
            "baseline": counts["baseline_failures"],
            "candidate": counts["candidate_failures"],
        },
        "significant_timing_regressions": counts[
            "significant_timing_regressions"
        ],
        "decision_authority": "diagnostic_only; does not determine the macro verdict",
    }


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def _format_absolute(metric: str, value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "n/a"
    if metric.endswith("process_count"):
        unit = "processes"
    elif metric.startswith("memory.") or metric.endswith(("heap_peak", "total_bytes_allocated")):
        unit = "B"
    elif metric.endswith("bytes_per_operation"):
        unit = "B/op"
    elif metric.endswith("allocations_per_operation"):
        unit = "alloc/op"
    elif metric.endswith("total_num_allocations") or metric.endswith("total_allocations"):
        unit = "allocations"
    else:
        unit = "units"
    return f"{float(value):+.4g} {unit}"


def _formatted_verdict(workload: Mapping[str, Any]) -> str:
    verdict = workload.get("verdict")
    overall = _workload_status(workload).upper()
    if not isinstance(verdict, Mapping):
        return overall
    failed = [
        name
        for name in ("timing", "memory", "allocations")
        if verdict.get(name) == "fail"
    ]
    if failed:
        return f"FAIL ({', '.join(failed)})"
    if overall == "INCOMPLETE":
        pending = [
            name
            for name in ("timing", "memory", "allocations")
            if verdict.get(name) in ("incomplete", "inconclusive", "not_measured")
        ]
        return f"INCOMPLETE ({', '.join(pending)})" if pending else overall
    return overall


def _iter_metric_details(workload: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    comparison = workload.get("comparison")
    if not isinstance(comparison, Mapping):
        return []
    output: list[tuple[str, Mapping[str, Any]]] = []
    for section in ("memory", "allocations"):
        section_result = comparison.get(section)
        if not isinstance(section_result, Mapping):
            continue
        metrics = section_result.get("metrics")
        if isinstance(metrics, Mapping):
            output.extend(
                (f"{section}.{name}", result)
                for name, result in metrics.items()
                if isinstance(result, Mapping)
            )
    return output


def _pyperformance_records(summary: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    pyperformance = summary.get("pyperformance")
    if not isinstance(pyperformance, Mapping):
        return []
    records = pyperformance.get("benchmarks", ())
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        return []
    return [record for record in records if isinstance(record, Mapping)]


def _pyperformance_counts(summary: Mapping[str, Any]) -> dict[str, int]:
    records = _pyperformance_records(summary)
    pyperformance = summary.get("pyperformance", {})
    pyperformance = pyperformance if isinstance(pyperformance, Mapping) else {}

    def failure_count(side: str) -> int:
        failures = pyperformance.get(f"{side}_failures", ())
        return (
            len(failures)
            if isinstance(failures, Sequence) and not isinstance(failures, (str, bytes))
            else 0
        )

    return {
        "benchmarks": len(records),
        "timing_compared": sum(
            1
            for record in records
            if isinstance(record.get("timing"), Mapping)
            and record["timing"].get("status") == "compared"
        ),
        "memory_compared": sum(
            1
            for record in records
            if isinstance(record.get("memory"), Mapping)
            and record["memory"].get("status") == "compared"
        ),
        "significant_timing_regressions": sum(
            1
            for record in records
            if isinstance(record.get("timing"), Mapping)
            and record["timing"].get("status") == "compared"
            and record["timing"].get("significant") is True
            and isinstance(record["timing"].get("change_pct"), (int, float))
            and record["timing"]["change_pct"] > 0
        ),
        "baseline_failures": failure_count("baseline"),
        "candidate_failures": failure_count("candidate"),
    }


def _pyperformance_change(record: Mapping[str, Any], section: str, field: str) -> float | None:
    value = record.get(section)
    if not isinstance(value, Mapping):
        return None
    if field == "mem_max_rss":
        rss = value.get("mem_max_rss")
        return None if not isinstance(rss, Mapping) else _percent_value(rss.get("change_pct"))
    if field == "command_max_rss":
        rss = value.get("command_max_rss")
        return None if not isinstance(rss, Mapping) else _percent_value(rss.get("change_pct"))
    return _percent_value(value.get("change_pct"))


def _render_pyperformance(summary: Mapping[str, Any]) -> list[str]:
    pyperformance = summary.get("pyperformance")
    if not isinstance(pyperformance, Mapping):
        return []
    records = _pyperformance_records(summary)
    counts = _pyperformance_counts(summary)
    verdict = summary.get("verdict", {})
    verdict = verdict if isinstance(verdict, Mapping) else {}
    status = verdict.get("pyperformance", {})
    status = status if isinstance(status, Mapping) else {}
    lines = [
        "## Pyperformance",
        "",
        "Timing and memory were collected in separate passes. Negative time change means the candidate was faster; positive RSS change means it used more resident memory.",
        "",
        (
            f"Status: **{status.get('status', 'informational')}**; "
            f"coverage **{status.get('coverage_status', 'unknown')}**. "
            "Pyperformance is diagnostic and does not determine the macro verdict."
        ),
        "",
        (
            f"Coverage: {counts['timing_compared']}/{counts['benchmarks']} benchmarks compared for timing; "
            f"{counts['memory_compared']}/{counts['benchmarks']} for memory. "
            f"Significant timing regressions: {counts['significant_timing_regressions']}. "
            f"Execution failures: baseline {counts['baseline_failures']}, candidate {counts['candidate_failures']}."
        ),
        "",
    ]
    group_summaries = pyperformance.get("groups", {})
    group_summaries = group_summaries if isinstance(group_summaries, Mapping) else {}
    visible_groups = [
        (name, result)
        for name, result in group_summaries.items()
        if isinstance(result, Mapping)
        and isinstance(result.get("selected_count"), int)
        and result.get("selected_count", 0) > 0
    ]
    if visible_groups:
        lines.extend(
            [
                "Group summaries are descriptive; benchmarks may appear in multiple groups, and group medians do not affect verdicts.",
                "",
                "| Group | Timing coverage | Median time Δ (faster if −) | Memory coverage | Median pyperf max RSS Δ (growth +) | Median command max RSS Δ (growth +) |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, result in visible_groups:
            timing_coverage = result.get("timing_coverage", {})
            memory_coverage = result.get("memory_coverage", {})
            timing_coverage = timing_coverage if isinstance(timing_coverage, Mapping) else {}
            memory_coverage = memory_coverage if isinstance(memory_coverage, Mapping) else {}
            selected_count = result.get("selected_count", 0)
            lines.append(
                (
                    "| {group} | {timing_compared}/{timing_selected} | {time} | "
                    "{memory_compared}/{memory_selected} | {rss} | {command_rss} |"
                ).format(
                    group=name,
                    timing_compared=timing_coverage.get("compared", 0),
                    timing_selected=timing_coverage.get("selected", selected_count),
                    time=_format_percent(
                        _percent_value(result.get("median_time_change_pct"))
                    ),
                    memory_compared=memory_coverage.get("compared", 0),
                    memory_selected=memory_coverage.get("selected", selected_count),
                    rss=_format_percent(
                        _percent_value(result.get("median_mem_max_rss_change_pct"))
                    ),
                    command_rss=_format_percent(
                        _percent_value(result.get("median_command_max_rss_change_pct"))
                    ),
                )
            )
        lines.append("")
    if records:
        lines.extend(
            [
                "| Benchmark | Group(s) | Time Δ (faster if −) | Pyperf max RSS Δ (growth +) | Command max RSS Δ (growth +) | Timing result | Coverage |",
                "| --- | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for record in records:
            timing = record.get("timing", {})
            memory = record.get("memory", {})
            timing = timing if isinstance(timing, Mapping) else {}
            memory = memory if isinstance(memory, Mapping) else {}
            significant = timing.get("significant")
            timing_result = (
                "significant"
                if significant is True
                else "not significant"
                if significant is False
                else "n/a"
            )
            coverage = f"time {timing.get('status', 'missing')}; memory {memory.get('status', 'missing')}"
            group_labels = record.get("groups", ())
            group_names = (
                ", ".join(str(group) for group in group_labels)
                if isinstance(group_labels, Sequence)
                and not isinstance(group_labels, (str, bytes))
                else ""
            )
            lines.append(
                (
                    "| {name} | {groups} | {time} | {rss} | {command_rss} | "
                    "{significance} | {coverage} |"
                ).format(
                    name=record.get("name", "unnamed"),
                    groups=group_names or "unassigned",
                    time=_format_percent(
                        _pyperformance_change(record, "timing", "change_pct")
                    ),
                    rss=_format_percent(
                        _pyperformance_change(record, "memory", "mem_max_rss")
                    ),
                    command_rss=_format_percent(
                        _pyperformance_change(record, "memory", "command_max_rss")
                    ),
                    significance=timing_result,
                    coverage=coverage,
                )
            )
    else:
        lines.append("No pyperformance benchmark results were recorded.")

    for side in ("baseline", "candidate"):
        failures = pyperformance.get(f"{side}_failures", ())
        if not isinstance(failures, Sequence) or isinstance(failures, (str, bytes)):
            continue
        if not failures:
            continue
        lines.extend(["", f"{side.title()} failures:"])
        for failure in failures:
            if isinstance(failure, Mapping):
                name = failure.get("name", "unnamed")
                stage = failure.get("stage", "unknown stage")
                reason = failure.get(
                    "detail", failure.get("reason", failure.get("error", "no detail"))
                )
                lines.append(f"- {name} ({stage}): {reason}")
            else:
                lines.append(f"- {failure}")
    lines.append("")
    return lines


def render_summary(value: Mapping[str, Any]) -> str:
    """Render an immediately scannable Markdown result report."""
    summary = _enrich_summary(validate_summary(value))
    baseline_name = _display_name(summary.get("baseline"), "baseline")
    candidate_name = _display_name(summary.get("candidate"), "candidate")
    overall = summary["verdict"]["overall"].upper()
    has_workloads = bool(summary["workloads"])
    has_pyperformance = isinstance(summary.get("pyperformance"), Mapping)
    cross_version_notice = (
        "Cross-version research comparison: interpreter major.minor versions differ; "
        "interpret build-quality and resource changes with that difference in mind."
        if summary.get("cross_version") else None
    )
    if not has_workloads and has_pyperformance:
        opening = [
            f"# Benchmark summary: {candidate_name} vs {baseline_name}",
            "",
        ]
        if cross_version_notice:
            opening.extend([cross_version_notice, ""])
        opening.extend([
            "Repository-owned workload verdict: **NOT RUN**. This run contains pyperformance results only.",
            "",
        ])
        opening.extend(_render_pyperformance(summary))
        provenance = summary.get("provenance")
        if provenance:
            opening.extend(["## Provenance", "", "```json", json.dumps(provenance, indent=2, sort_keys=True), "```", ""])
        return "\n".join(opening).rstrip() + "\n"
    memory_metric = "RSS" if any(
        _primary_memory_metric(workload) == "peak_rss"
        for workload in summary["workloads"]
    ) else "PSS"
    lines = [
        f"# Benchmark summary: {candidate_name} vs {baseline_name}",
        "",
    ]
    if cross_version_notice:
        lines.extend([cross_version_notice, ""])
    lines.extend([
        f"Macro verdict: **{overall}** across {len(summary['workloads'])} repository-owned workload(s).",
        "",
        f"Every change is candidate over baseline. For timing, a negative percentage means the candidate took less time; for {memory_metric} and allocation bytes, a positive percentage means the candidate used more.",
        "",
        "## Repository-owned workload results",
        "",
        f"| Workload | Category | Time Δ (faster if −) | CPU seconds/op Δ (growth +) | Peak {memory_metric} Δ (growth +) | Bytes/op Δ (growth +) | Verdict |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ])
    for workload in summary["workloads"]:
        identity = workload.get("identity", {})
        identity = identity if isinstance(identity, Mapping) else {}
        name = str(identity.get("name", "unnamed"))
        category = str(identity.get("category", "uncategorized"))
        metrics = _workload_metrics(workload)
        lines.append(
            "| {name} | {category} | {time} | {cpu} | {pss} | {alloc} | {verdict} |".format(
                name=name,
                category=category,
                time=_format_percent(metrics["time_change_percent"]),
                cpu=_format_percent(_percent_value(_comparison_value(
                    workload, "comparison", "timing", "cpu", "metrics",
                    "total_seconds_per_operation", "change_percent"
                ))) if _comparison_value(
                    workload, "comparison", "timing", "cpu", "status"
                ) == "compared" else "n/a",
                pss=_format_percent(metrics["peak_memory_change_percent"]),
                alloc=_format_percent(metrics["bytes_per_operation_change_percent"]),
                verdict=_formatted_verdict(workload),
            )
        )

    if has_workloads:
        lines.extend(
            [
                "",
                "## Category summaries",
                "",
                "Category medians are descriptive; each workload verdict remains authoritative.",
                "",
                f"| Category | Workloads | Median time Δ | Median peak {memory_metric} Δ | Median bytes/op Δ | Verdict counts |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for category, result in summary["categories"].items():
            changes = result["median_changes_percent"]
            counts = ", ".join(
                f"{status.upper()} {count}" for status, count in result["verdicts"].items()
            ) or "none"
            lines.append(
                "| {category} | {count} | {time} | {pss} | {alloc} | {verdicts} |".format(
                    category=category,
                    count=result["workload_count"],
                    time=_format_percent(changes["time_change_percent"]),
                    pss=_format_percent(changes["peak_memory_change_percent"]),
                    alloc=_format_percent(changes["bytes_per_operation_change_percent"]),
                    verdicts=counts,
                )
            )

    if has_workloads:
        aggregate = summary["aggregate"]
        aggregate_changes = aggregate["median_changes_percent"]
        lines.extend(
            [
                "",
                "## Suite median changes",
                "",
                "These medians describe the suite and never replace per-workload gates.",
                "",
                f"| Workloads | Median time Δ | Median peak {memory_metric} Δ | Median bytes/op Δ |",
                "| ---: | ---: | ---: | ---: |",
                "| {count} | {time} | {pss} | {alloc} |".format(
                    count=aggregate["workload_count"],
                    time=_format_percent(aggregate_changes["time_change_percent"]),
                    pss=_format_percent(aggregate_changes["peak_memory_change_percent"]),
                    alloc=_format_percent(
                        aggregate_changes["bytes_per_operation_change_percent"]
                    ),
                ),
            ]
        )

    if has_pyperformance:
        lines.extend([""] + _render_pyperformance(summary))

    if has_workloads:
        lines.extend(["", "## Verdict details", ""])
    for workload in summary["workloads"]:
        identity = workload.get("identity", {})
        identity = identity if isinstance(identity, Mapping) else {}
        name = str(identity.get("name", "unnamed"))
        verdict = workload.get("verdict", {})
        comparison = workload.get("comparison", {})
        timing = comparison.get("timing", {}) if isinstance(comparison, Mapping) else {}
        lines.append(f"### {name}")
        lines.append("")
        lines.append(
            f"Timing: **{verdict.get('timing', 'unknown')}**; paired candidate/baseline ratio "
            f"{timing.get('time_ratio', 'n/a')}; measured noise limit "
            f"{timing.get('noise_threshold_percent', 'n/a')}%."
        )
        reasons = verdict.get("reasons", ()) if isinstance(verdict, Mapping) else ()
        if reasons:
            lines.append("")
            lines.append("Reasons:")
            lines.extend(f"- {reason}" for reason in reasons)
        details = _iter_metric_details(workload)
        if details:
            lines.append("")
            lines.append("| Metric | Relative Δ | Absolute Δ | Noise allowance | Status | Gated |")
            lines.append("| --- | ---: | ---: | ---: | --- | --- |")
            for metric, result in details:
                lines.append(
                    "| {metric} | {change} | {absolute} | {noise} | {status} | {gated} |".format(
                        metric=metric,
                        change=_format_percent(_percent_value(result.get("change_percent"))),
                        absolute=_format_absolute(metric, result.get("absolute_change")),
                        noise=result.get("noise_allowance", "n/a"),
                        status=result.get("status", "unknown"),
                        gated="yes" if result.get("gated") else "no",
                    )
                )
        lines.append("")

    provenance = summary.get("provenance")
    if provenance:
        lines.extend(["## Provenance", "", "```json", json.dumps(provenance, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def save_summary(
    summary: Mapping[str, Any],
    output: str | Path,
    provenance: Mapping[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write `summary.json` and `summary.md` into the run output directory."""
    document = dict(summary)
    if provenance is not None:
        document["provenance"] = dict(provenance)
    enriched = _enrich_summary(validate_summary(document))
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "summary.json"
    markdown_path = directory / "summary.md"
    json_path.write_text(summary_to_json(enriched), encoding="utf-8")
    markdown_path.write_text(render_summary(enriched), encoding="utf-8")
    return json_path, markdown_path


__all__ = ["build_summary", "compare_workload", "render_summary", "save_summary"]
