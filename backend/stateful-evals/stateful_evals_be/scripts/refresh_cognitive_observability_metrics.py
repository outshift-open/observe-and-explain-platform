#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Refresh selected paper metrics from persisted trajectory-context artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shlex
import shutil
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    LLMMetricJudge,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.metrics import (
    evaluate_high_level_metrics_batched,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.trajectory_metrics import (
    CommunicationEfficiencyMetric,
    UPDATED_METRIC_NAMES,
    build_updated_trajectory_metrics,
)


DEFAULT_MODEL = "vertex_ai/gemini-2.5-flash"
REFRESH_SUITE = "paper_v2_targeted_refresh"
METRIC_NAMES = (
    "Policy Safety",
    "Delegation Accuracy",
    "Goal Alignment",
    "Instruction Following",
    "Handoff Quality",
    "Semantic Consistency",
    "Context Preservation",
    "Confidence Calibration",
    "Verification Quality",
    "Communication Efficiency",
    "Groundedness",
    "Task Completion",
    "Constraint Satisfaction",
)
PRESERVED_METRIC_NAMES = tuple(
    name for name in METRIC_NAMES if name not in UPDATED_METRIC_NAMES
)
CHALLENGE_METRIC = {
    "CC-1": "Delegation Accuracy",
    "CC-3": "Verification Quality",
    "CE-1": "Verification Quality",
    "CR-1": "Goal Alignment",
    "DC-1": "Communication Efficiency",
    "DC-2": "Instruction Following",
    "DC-4": "Constraint Satisfaction",
    "DE-1": "Delegation Accuracy",
    "DR-1": "Semantic Consistency",
    "EM-1": "Confidence Calibration",
}
OLD_METRIC_NAME = {"Communication Efficiency": "Coordination Efficiency"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _load_env(path: Path | None) -> None:
    if path is None:
        return
    for raw_line in path.expanduser().read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed = shlex.split(value, comments=True, posix=True)
        if parsed:
            os.environ[key.strip()] = parsed[0]


def _score(metric: Mapping[str, Any]) -> int | None:
    value = metric.get("score")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and value in (0, 1):
        return int(value)
    return None


def _usage(metrics: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    totals = Counter()
    for metric in metrics:
        metadata = metric.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        usage = metadata.get("usage")
        if not isinstance(usage, Mapping):
            continue
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            totals[key] += int(usage.get(key) or 0)
    return {
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "total_tokens": totals["total_tokens"],
    }


def _cost(
    usage: Mapping[str, Any],
    *,
    input_per_million: float,
    output_per_million: float,
) -> float:
    return (
        int(usage.get("prompt_tokens") or 0) * input_per_million
        + int(usage.get("completion_tokens") or 0) * output_per_million
    ) / 1_000_000


def _source_records(source_results: Path) -> list[Path]:
    return sorted(source_results.expanduser().glob("runs/*/*/evaluation_record.json"))


def _combine_delegation_accuracy(
    routing_result: Mapping[str, Any],
    ownership_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine reused routing accuracy with the new ownership-coverage audit."""
    routing_score = _score(routing_result)
    ownership_score = _score(ownership_result)
    fatal_failures = [
        *list(routing_result.get("fatal_failures") or []),
        *list(ownership_result.get("fatal_failures") or []),
    ]
    minor_failures = [
        *list(routing_result.get("minor_failures") or []),
        *list(ownership_result.get("minor_failures") or []),
    ]
    evidence_by_key: dict[tuple[str, int, str], dict[str, Any]] = {}
    for item in [
        *list(routing_result.get("evidence") or []),
        *list(ownership_result.get("evidence") or []),
    ]:
        if not isinstance(item, Mapping):
            continue
        key = (
            str(item.get("artifact_id") or ""),
            int(item.get("span_index") or -1),
            str(item.get("content") or ""),
        )
        evidence_by_key.setdefault(key, dict(item))
    metadata = dict(ownership_result.get("metadata") or {})
    metadata.update(
        {
            "metric_code": "delegation_accuracy",
            "metric_layer": "execution",
            "definition_version": "paper_v2",
            "subscores": {
                "executed_routing_accuracy": routing_score,
                "ownership_completeness": ownership_score,
            },
            "executed_routing_result_reused": True,
            "executed_routing_definition_version": (
                (routing_result.get("metadata") or {}).get("definition_version")
            ),
        }
    )
    return {
        "high_level_metric": "Delegation Accuracy",
        "score": 0
        if routing_score == 0 or ownership_score == 0 or fatal_failures
        else 1,
        "reasoning": (
            "Executed routing: "
            f"{routing_result.get('reasoning') or 'no reasoning recorded'} "
            "Ownership completeness: "
            f"{ownership_result.get('reasoning') or 'no reasoning recorded'}"
        ),
        "fatal_failures": fatal_failures,
        "minor_failures": minor_failures,
        "evidence": list(evidence_by_key.values()),
        "total_fatal": len(fatal_failures),
        "total_minor": len(minor_failures),
        "metadata": metadata,
    }


def _merge_metrics(
    original_metrics: Sequence[Mapping[str, Any]],
    refreshed_metrics: Sequence[Mapping[str, Any]],
    *,
    paper_v1_metrics: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    original_by_name = {
        str(metric.get("high_level_metric") or ""): dict(metric)
        for metric in original_metrics
    }
    refreshed_by_name = {
        str(metric.get("high_level_metric") or ""): dict(metric)
        for metric in refreshed_metrics
    }
    paper_v1_by_name = {
        str(metric.get("high_level_metric") or ""): dict(metric)
        for metric in paper_v1_metrics or []
    }
    merged: list[dict[str, Any]] = []
    for name in METRIC_NAMES:
        if name in refreshed_by_name:
            if name == "Delegation Accuracy":
                routing_result = paper_v1_by_name.get(name) or original_by_name.get(
                    name
                )
                if routing_result is None:
                    raise ValueError(
                        "Delegation Accuracy requires a paper-v1 routing result"
                    )
                metric = _combine_delegation_accuracy(
                    routing_result,
                    refreshed_by_name[name],
                )
            else:
                metric = refreshed_by_name[name]
        else:
            metric = original_by_name.get(name) or original_by_name.get(
                OLD_METRIC_NAME.get(name, name)
            )
        if metric is None:
            raise ValueError(f"Missing metric result for {name}")
        merged.append(metric)
    return merged


def refresh_records(
    *,
    source_results: Path,
    output_dir: Path,
    model: str,
    shard_index: int,
    shard_count: int,
    input_per_million: float,
    output_per_million: float,
    force: bool,
    metric_names: Sequence[str],
    baseline_results: Path | None,
    selected_hashes: frozenset[str],
) -> None:
    source_results = source_results.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    in_place = source_results == output_dir
    records = [
        path
        for index, path in enumerate(_source_records(source_results))
        if index % shard_count == shard_index
        and (not selected_hashes or path.parent.name in selected_hashes)
    ]
    for index, source_record_path in enumerate(records, 1):
        relative_run = source_record_path.parent.relative_to(source_results / "runs")
        run_output = output_dir / "runs" / relative_run
        output_record_path = run_output / "evaluation_record.json"
        if output_record_path.is_file() and not force:
            existing = _read_json(output_record_path)
            if (
                existing.get("status") == "completed"
                and existing.get("model") == model
                and existing.get("metric_suite") == REFRESH_SUITE
                and set(existing.get("rerun_metrics_this_pass") or [])
                == set(metric_names)
            ):
                print(
                    f"[{index}/{len(records)}] {relative_run.name} resumed",
                    flush=True,
                )
                continue

        source_record = _read_json(source_record_path)
        source_run = source_record_path.parent
        started = time.time()
        run_output.mkdir(parents=True, exist_ok=True)
        try:
            context, _ = load_trajectory_context_artifact(
                source_run / "trajectory_context.json"
            )
            stateful_path = source_run / "stateful_eval_result.json"
            stateful_result = (
                _read_json(stateful_path) if stateful_path.is_file() else {}
            )
            judge = LLMMetricJudge(model_name=model)
            selected_metrics = tuple(
                metric
                for metric in build_updated_trajectory_metrics(judge=judge)
                if metric.name in metric_names
            )
            if len(selected_metrics) != len(set(metric_names)):
                found = {metric.name for metric in selected_metrics}
                raise ValueError(
                    f"Unknown updated metrics: {sorted(set(metric_names) - found)}"
                )
            refreshed_results = evaluate_high_level_metrics_batched(
                context,
                stateful_result=stateful_result,
                metrics=selected_metrics,
                judge=judge,
            )
            refreshed_payloads = [result.to_payload() for result in refreshed_results]
            baseline_metrics = None
            if baseline_results is not None:
                baseline_record_path = (
                    baseline_results.expanduser().resolve()
                    / "runs"
                    / relative_run
                    / "evaluation_record.json"
                )
                baseline_metrics = _read_json(baseline_record_path).get("metrics") or []
            merged = _merge_metrics(
                source_record.get("metrics") or [],
                refreshed_payloads,
                paper_v1_metrics=baseline_metrics,
            )
            pass_usage = _usage(refreshed_payloads)
            pass_cost = _cost(
                pass_usage,
                input_per_million=input_per_million,
                output_per_million=output_per_million,
            )
            prior_is_refresh = source_record.get("metric_suite") == REFRESH_SUITE
            prior_usage = (
                dict(source_record.get("usage") or {}) if prior_is_refresh else {}
            )
            refresh_usage = {
                key: int(prior_usage.get(key) or 0) + int(pass_usage.get(key) or 0)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            prior_cost = (
                float(source_record.get("estimated_cost_usd") or 0)
                if prior_is_refresh
                else 0.0
            )
            refresh_cost = prior_cost + pass_cost
            all_recomputed = sorted(
                set(source_record.get("recomputed_metrics") or []) | set(metric_names)
            )
            record = {
                **{
                    key: value
                    for key, value in source_record.items()
                    if key
                    not in {
                        "duration_seconds",
                        "estimated_cost_usd",
                        "metric_suite",
                        "metrics",
                        "model",
                        "status",
                        "usage",
                    }
                },
                "status": "completed",
                "model": model,
                "metric_suite": REFRESH_SUITE,
                "source_metric_suite": (
                    source_record.get("source_metric_suite")
                    or source_record.get("metric_suite")
                ),
                "duration_seconds": round(time.time() - started, 3),
                "span_processing_performed": False,
                "reused_trajectory_context": True,
                "recomputed_metrics": all_recomputed,
                "rerun_metrics_this_pass": sorted(metric_names),
                "preserved_metrics": [
                    name for name in METRIC_NAMES if name not in all_recomputed
                ],
                "usage": refresh_usage,
                "estimated_cost_usd": refresh_cost,
                "refresh_pass_usage": pass_usage,
                "refresh_pass_cost_usd": pass_cost,
                "source_full_pipeline_cost_usd": source_record.get(
                    "source_full_pipeline_cost_usd",
                    source_record.get("estimated_cost_usd"),
                ),
                "metrics": merged,
            }
            context_source = source_run / "trajectory_context.json"
            context_destination = run_output / "trajectory_context.json"
            if context_source.resolve() != context_destination.resolve():
                shutil.copy2(context_source, context_destination)
            if stateful_path.is_file():
                stateful_destination = run_output / "stateful_eval_result.json"
                if stateful_path.resolve() != stateful_destination.resolve():
                    shutil.copy2(stateful_path, stateful_destination)
            _write_json(
                run_output / "trajectory_context_metrics.paper_v2_refresh.json",
                merged,
            )
            _write_json(
                run_output / "refreshed_metric_results.json",
                refreshed_payloads,
            )
            _write_json(output_record_path, record)
            print(
                f"[{index}/{len(records)}] {relative_run.name} completed "
                f"${pass_cost:.4f} pass (${refresh_cost:.4f} cumulative)",
                flush=True,
            )
        except Exception as exc:
            record = {
                **{
                    key: value
                    for key, value in source_record.items()
                    if key not in {"metrics", "status"}
                },
                "status": "error",
                "metric_suite": REFRESH_SUITE,
                "model": model,
                "span_processing_performed": False,
                "duration_seconds": round(time.time() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
            if not in_place:
                _write_json(output_record_path, record)
            print(
                f"[{index}/{len(records)}] {relative_run.name} ERROR {record['error']}",
                flush=True,
            )


def assemble_saved_refresh(
    *,
    source_results: Path,
    baseline_results: Path,
    output_dir: Path,
) -> None:
    """Assemble the revised suite from saved metric results without judge calls."""
    source_results = source_results.expanduser().resolve()
    baseline_results = baseline_results.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    records = _source_records(source_results)
    for index, source_record_path in enumerate(records, 1):
        relative_run = source_record_path.parent.relative_to(source_results / "runs")
        source_run = source_record_path.parent
        output_run = output_dir / "runs" / relative_run
        source_record = _read_json(source_record_path)
        raw_refresh_path = source_run / "refreshed_metric_results.json"
        raw_refresh = _read_json(raw_refresh_path)
        ownership_result = next(
            (
                metric
                for metric in raw_refresh
                if metric.get("high_level_metric") == "Delegation Accuracy"
            ),
            None,
        )
        if ownership_result is None:
            raise ValueError(
                f"{relative_run}: missing saved Delegation Accuracy ownership audit"
            )

        baseline_record_path = (
            baseline_results / "runs" / relative_run / "evaluation_record.json"
        )
        baseline_record = _read_json(baseline_record_path)
        routing_result = next(
            (
                metric
                for metric in baseline_record.get("metrics") or []
                if metric.get("high_level_metric") == "Delegation Accuracy"
            ),
            None,
        )
        if routing_result is None:
            raise ValueError(
                f"{relative_run}: missing paper-v1 Delegation Accuracy result"
            )

        combined_delegation = _combine_delegation_accuracy(
            routing_result,
            ownership_result,
        )
        assembled_metrics = [
            (
                combined_delegation
                if metric.get("high_level_metric") == "Delegation Accuracy"
                else metric
            )
            for metric in source_record.get("metrics") or []
        ]
        if len(assembled_metrics) != len(METRIC_NAMES):
            raise ValueError(
                f"{relative_run}: expected {len(METRIC_NAMES)} metrics, "
                f"found {len(assembled_metrics)}"
            )

        record = {
            **source_record,
            "status": "completed",
            "metric_suite": REFRESH_SUITE,
            "span_processing_performed": False,
            "reused_trajectory_context": True,
            "assembled_from_saved_results": True,
            "judge_calls_this_pass": 0,
            "assembly_cost_usd": 0.0,
            "rerun_metrics_this_pass": [],
            "metrics": assembled_metrics,
        }
        output_run.mkdir(parents=True, exist_ok=True)
        for filename in (
            "trajectory_context.json",
            "stateful_eval_result.json",
            "refreshed_metric_results.json",
        ):
            source_path = source_run / filename
            if source_path.is_file():
                shutil.copy2(source_path, output_run / filename)
        _write_json(
            output_run / "trajectory_context_metrics.paper_v2_refresh.json",
            assembled_metrics,
        )
        _write_json(output_run / "evaluation_record.json", record)
        print(f"[{index}/{len(records)}] {relative_run.name} assembled", flush=True)


def restore_communication_results(
    *,
    output_dir: Path,
    communication_results: Path,
) -> None:
    """Copy saved Communication Efficiency results into an existing run."""
    output_dir = output_dir.expanduser().resolve()
    communication_results = communication_results.expanduser().resolve()
    records = _source_records(output_dir)
    metric_name = CommunicationEfficiencyMetric.name
    for record_path in records:
        run_dir = record_path.parent
        relative_run = run_dir.relative_to(output_dir / "runs")
        record = _read_json(record_path)
        communication_record = _read_json(
            communication_results / "runs" / relative_run / "evaluation_record.json"
        )
        result = next(
            (
                dict(item)
                for item in communication_record.get("metrics") or []
                if item.get("high_level_metric") == metric_name
            ),
            None,
        )
        if result is None:
            raise ValueError(
                f"{relative_run}: missing saved Communication Efficiency result"
            )
        result["metadata"] = dict(result.get("metadata") or {})
        result["metadata"]["result_reused_from"] = "paper_v2_initial_refresh"
        metrics = [
            result if item.get("high_level_metric") == metric_name else item
            for item in record.get("metrics") or []
        ]
        record["metrics"] = metrics
        _write_json(record_path, record)
        _write_json(
            run_dir / "trajectory_context_metrics.paper_v2_refresh.json",
            metrics,
        )
        raw_path = run_dir / "refreshed_metric_results.json"
        if raw_path.is_file():
            raw_results = _read_json(raw_path)
            raw_results = [
                result if item.get("high_level_metric") == metric_name else item
                for item in raw_results
            ]
            _write_json(raw_path, raw_results)
    print(f"Restored Communication Efficiency in {len(records)} records")


def _wilson(failures: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (math.nan, math.nan)
    rate = failures / n
    denominator = 1 + z * z / n
    centre = (rate + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _challenge_code(record: Mapping[str, Any]) -> str:
    code = str(record.get("playbook_code") or "")
    if code:
        return code
    scenario = str(record.get("scenario") or "unknown")
    parts = scenario.split("-", 2)
    return "-".join(parts[:2]) if len(parts) >= 2 else scenario


def _trajectory_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row.get("dataset") or ""), str(row.get("hash") or ""))


def _metric_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        for metric in record.get("metrics") or []:
            metadata = metric.get("metadata")
            evidence = metric.get("evidence")
            rows.append(
                {
                    "hash": record.get("hash"),
                    "domain": record.get("domain"),
                    "dataset": record.get("dataset"),
                    "scenario": record.get("scenario"),
                    "playbook_code": _challenge_code(record),
                    "checker_present": record.get("checker_present"),
                    "metric": metric.get("high_level_metric"),
                    "score": _score(metric),
                    "reasoning": metric.get("reasoning") or "",
                    "fatal_failures": len(metric.get("fatal_failures") or []),
                    "minor_failures": len(metric.get("minor_failures") or []),
                    "evidence_count": len(evidence or []),
                    "definition_version": (
                        metadata.get("definition_version")
                        if isinstance(metadata, Mapping)
                        else ""
                    ),
                    "recomputed": (
                        metric.get("high_level_metric") in UPDATED_METRIC_NAMES
                    ),
                }
            )
    return rows


def _rate(
    rows: Sequence[Mapping[str, Any]],
    *,
    failure: bool,
) -> tuple[int, int, float | None, float | None, float | None]:
    valid = [row for row in rows if row.get("score") in (0, 1)]
    count = sum((row["score"] == 0) is failure for row in valid)
    n = len(valid)
    if not n:
        return (count, n, None, None, None)
    low, high = _wilson(count, n)
    return (count, n, count / n, low, high)


def summarize(*, output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve()
    records = [
        _read_json(path)
        for path in sorted(output_dir.glob("runs/*/*/evaluation_record.json"))
    ]
    completed = [record for record in records if record.get("status") == "completed"]
    errors = [record for record in records if record.get("status") == "error"]
    metric_rows = _metric_rows(completed)
    _write_csv(output_dir / "metrics_long.csv", metric_rows)

    metric_lookup = {
        (*_trajectory_key(row), str(row["metric"])): row for row in metric_rows
    }
    trajectory_rows: list[dict[str, Any]] = []
    for record in completed:
        code = _challenge_code(record)
        target = CHALLENGE_METRIC.get(code)
        target_row = metric_lookup.get((*_trajectory_key(record), str(target)))
        trajectory_rows.append(
            {
                "hash": record.get("hash"),
                "domain": record.get("domain"),
                "dataset": record.get("dataset"),
                "scenario": record.get("scenario"),
                "playbook_code": code,
                "checker_present": record.get("checker_present"),
                "target_metric": target,
                "target_metric_score": (
                    target_row.get("score") if target_row is not None else None
                ),
                "failed_metric_count": sum(
                    row.get("score") == 0
                    for row in metric_rows
                    if _trajectory_key(row) == _trajectory_key(record)
                ),
                "prompt_tokens": (record.get("usage") or {}).get("prompt_tokens"),
                "completion_tokens": (record.get("usage") or {}).get(
                    "completion_tokens"
                ),
                "estimated_cost_usd": record.get("estimated_cost_usd"),
            }
        )
    _write_csv(output_dir / "trajectory_summary.csv", trajectory_rows)

    metric_summary: list[dict[str, Any]] = []
    failures_by_metric: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for name in METRIC_NAMES:
        rows = [row for row in metric_rows if row["metric"] == name]
        failures, n, rate, low, high = _rate(rows, failure=True)
        for row in rows:
            if row.get("score") == 0:
                failures_by_metric[name].add(_trajectory_key(row))
        metric_summary.append(
            {
                "metric": name,
                "n": n,
                "failures": failures,
                "passes": n - failures,
                "invalid": len(rows) - n,
                "failure_rate": rate,
                "wilson_95_low": low,
                "wilson_95_high": high,
                "definition_version": (
                    "paper_v2" if name in UPDATED_METRIC_NAMES else "paper_v1"
                ),
            }
        )
    _write_csv(output_dir / "metric_summary.csv", metric_summary)

    challenge_rows: list[dict[str, Any]] = []
    signature_rows: list[dict[str, Any]] = []
    stability_rows: list[dict[str, Any]] = []
    for code, target in CHALLENGE_METRIC.items():
        code_trajectories = [
            row for row in trajectory_rows if row["playbook_code"] == code
        ]
        target_rows = [
            metric_lookup[(*_trajectory_key(row), target)]
            for row in code_trajectories
            if (*_trajectory_key(row), target) in metric_lookup
        ]
        target_failures, target_n, target_rate, target_low, target_high = _rate(
            target_rows,
            failure=True,
        )
        domains = {
            str(row["domain"]) for row in metric_rows if row["playbook_code"] == code
        }
        target_baseline_rows = [
            row
            for row in metric_rows
            if row["metric"] == target
            and row["playbook_code"] == "baseline"
            and str(row["domain"]) in domains
        ]
        (
            target_baseline_failures,
            target_baseline_n,
            target_baseline_rate,
            _,
            _,
        ) = _rate(
            target_baseline_rows,
            failure=True,
        )
        challenge_rows.append(
            {
                "challenge": code,
                "target_metric": target,
                "n": len(code_trajectories),
                "target_failures": target_failures,
                "target_evaluated": target_n,
                "target_failure_rate": target_rate,
                "target_failure_rate_wilson_low": target_low,
                "target_failure_rate_wilson_high": target_high,
                "domain_baseline_n": target_baseline_n,
                "domain_baseline_failures": target_baseline_failures,
                "domain_baseline_rate": target_baseline_rate,
                "lift_above_domain_baseline": (
                    target_rate - target_baseline_rate
                    if target_rate is not None and target_baseline_rate is not None
                    else None
                ),
            }
        )

        for metric in METRIC_NAMES:
            challenge_metric_rows = [
                metric_lookup[(*_trajectory_key(row), metric)]
                for row in code_trajectories
                if (*_trajectory_key(row), metric) in metric_lookup
            ]
            failures, challenge_n, rate, low, high = _rate(
                challenge_metric_rows,
                failure=True,
            )
            baseline_rows = [
                row
                for row in metric_rows
                if row["metric"] == metric
                and row["playbook_code"] == "baseline"
                and str(row["domain"]) in domains
            ]
            baseline_failures, baseline_n, baseline_rate, _, _ = _rate(
                baseline_rows,
                failure=True,
            )
            signature_rows.append(
                {
                    "challenge": code,
                    "metric": metric,
                    "is_target_metric": metric == target,
                    "challenge_n": challenge_n,
                    "failures": failures,
                    "failure_rate": rate,
                    "wilson_95_low": low,
                    "wilson_95_high": high,
                    "domain_baseline_n": baseline_n,
                    "domain_baseline_failures": baseline_failures,
                    "domain_baseline_rate": baseline_rate,
                    "lift_above_domain_baseline": (
                        rate - baseline_rate
                        if rate is not None and baseline_rate is not None
                        else None
                    ),
                }
            )

        for dataset in sorted(
            {str(row["dataset"]) for row in code_trajectories if row.get("dataset")}
        ):
            dataset_rows = [
                row for row in code_trajectories if row["dataset"] == dataset
            ]
            dataset_target_rows = [
                metric_lookup[(*_trajectory_key(row), target)]
                for row in dataset_rows
                if (*_trajectory_key(row), target) in metric_lookup
            ]
            failures, evaluated_n, rate, low, high = _rate(
                dataset_target_rows,
                failure=True,
            )
            dataset_baseline_rows = [
                row
                for row in metric_rows
                if row["metric"] == target
                and row["playbook_code"] == "baseline"
                and row["dataset"] == dataset
            ]
            (
                baseline_failures,
                baseline_n,
                baseline_rate,
                _,
                _,
            ) = _rate(dataset_baseline_rows, failure=True)
            stability_rows.append(
                {
                    "challenge": code,
                    "dataset": dataset,
                    "n": len(dataset_rows),
                    "target_metric": target,
                    "target_failures": failures,
                    "target_evaluated": evaluated_n,
                    "target_failure_rate": rate,
                    "target_failure_rate_wilson_low": low,
                    "target_failure_rate_wilson_high": high,
                    "dataset_baseline_n": baseline_n,
                    "dataset_baseline_failures": baseline_failures,
                    "dataset_baseline_rate": baseline_rate,
                    "lift_above_dataset_baseline": (
                        rate - baseline_rate
                        if rate is not None and baseline_rate is not None
                        else None
                    ),
                }
            )

    _write_csv(output_dir / "challenge_observability.csv", challenge_rows)
    _write_csv(output_dir / "metric_signatures.csv", signature_rows)
    _write_csv(output_dir / "cross_context_stability.csv", stability_rows)

    overlap_rows: list[dict[str, Any]] = []
    for left_index, left in enumerate(METRIC_NAMES):
        for right in METRIC_NAMES[left_index + 1 :]:
            union = failures_by_metric[left] | failures_by_metric[right]
            overlap_rows.append(
                {
                    "metric_a": left,
                    "metric_b": right,
                    "jaccard_cofailure": (
                        len(failures_by_metric[left] & failures_by_metric[right])
                        / len(union)
                        if union
                        else 0.0
                    ),
                }
            )
    _write_csv(output_dir / "metric_overlap.csv", overlap_rows)

    total_usage = {
        key: sum(int((record.get("usage") or {}).get(key) or 0) for record in completed)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    summary = {
        "metric_suite": REFRESH_SUITE,
        "model": completed[0].get("model") if completed else None,
        "completed": len(completed),
        "errors": len(errors),
        "span_processing_performed": False,
        "recomputed_metrics": sorted(UPDATED_METRIC_NAMES),
        "preserved_metrics": list(PRESERVED_METRIC_NAMES),
        "dc4_target_metric": CHALLENGE_METRIC["DC-4"],
        "usage": total_usage,
        "estimated_refresh_cost_usd": sum(
            float(record.get("estimated_cost_usd") or 0) for record in completed
        ),
        "datasets": dict(Counter(str(record.get("dataset")) for record in completed)),
        "metric_summary": metric_summary,
        "challenge_summary": challenge_rows,
        "errors_detail": [
            {
                "hash": record.get("hash"),
                "dataset": record.get("dataset"),
                "error": record.get("error"),
            }
            for record in errors
        ],
    }
    _write_json(output_dir / "study_summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument("--source-results", type=Path, required=True)
    refresh_parser.add_argument("--output-dir", type=Path, required=True)
    refresh_parser.add_argument("--env-file", type=Path)
    refresh_parser.add_argument("--model", default=DEFAULT_MODEL)
    refresh_parser.add_argument("--shard-index", type=int, default=0)
    refresh_parser.add_argument("--shard-count", type=int, default=1)
    refresh_parser.add_argument("--input-cost-per-million", type=float, default=0.3)
    refresh_parser.add_argument("--output-cost-per-million", type=float, default=2.5)
    refresh_parser.add_argument(
        "--metric",
        action="append",
        choices=sorted(UPDATED_METRIC_NAMES),
        help="Refresh only this revised metric; repeat for multiple metrics.",
    )
    refresh_parser.add_argument(
        "--baseline-results",
        type=Path,
        help="Paper-v1 results used for the executed-routing subscore.",
    )
    refresh_parser.add_argument(
        "--hash",
        action="append",
        default=[],
        help="Refresh only the selected trajectory hash; repeat as needed.",
    )
    refresh_parser.add_argument("--force", action="store_true")

    summary_parser = subparsers.add_parser("summarize")
    summary_parser.add_argument("--output-dir", type=Path, required=True)

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--source-results", type=Path, required=True)
    assemble_parser.add_argument("--baseline-results", type=Path, required=True)
    assemble_parser.add_argument("--output-dir", type=Path, required=True)

    restore_parser = subparsers.add_parser("restore-communication")
    restore_parser.add_argument("--output-dir", type=Path, required=True)
    restore_parser.add_argument(
        "--communication-results",
        type=Path,
        required=True,
        help="Run directory with valid Communication Efficiency results to reuse.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "refresh":
        _load_env(args.env_file)
        refresh_records(
            source_results=args.source_results,
            output_dir=args.output_dir,
            model=args.model,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            input_per_million=args.input_cost_per_million,
            output_per_million=args.output_cost_per_million,
            force=args.force,
            metric_names=args.metric or sorted(UPDATED_METRIC_NAMES),
            baseline_results=args.baseline_results,
            selected_hashes=frozenset(args.hash),
        )
        return 0

    if args.command == "assemble":
        assemble_saved_refresh(
            source_results=args.source_results,
            baseline_results=args.baseline_results,
            output_dir=args.output_dir,
        )
        return 0

    if args.command == "restore-communication":
        restore_communication_results(
            output_dir=args.output_dir,
            communication_results=args.communication_results,
        )
        return 0

    print(json.dumps(summarize(output_dir=args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
