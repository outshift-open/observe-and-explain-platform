#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Evaluate persisted trajectory state with legacy and revised metric suites."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from stateful_evals_be.evaluation.trajectory_context_metrics import (
    LEGACY_METRIC_SUITE,
    PAPER_METRIC_SUITE,
    evaluate_metric_suite_batched,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    LLMMetricJudge,
)


def _load_env(path: Path | None) -> None:
    if path is None:
        return
    for raw_line in path.expanduser().read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key.strip()] = value


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "trajectory_score": None,
            "fatal_failures": [],
            "minor_failures": [],
        }
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Stateful result must contain a JSON object")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _suite_summary(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [
        item
        for item in payloads
        if bool((item.get("metadata") or {}).get("affects_trajectory_score", True))
    ]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for item in payloads:
        metric_usage = (item.get("metadata") or {}).get("usage") or {}
        for key in usage:
            usage[key] += int(metric_usage.get(key, 0) or 0)
    return {
        "metric_count": len(payloads),
        "failed_metrics": [
            item["high_level_metric"] for item in payloads if item.get("score") == 0
        ],
        "score_affecting_metrics": [item["high_level_metric"] for item in scored],
        "trajectory_score": 0 if any(item.get("score") == 0 for item in scored) else 1,
        "usage": usage,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the current and/or revised high-level metrics against an existing "
            "trajectory_context.json artifact."
        )
    )
    parser.add_argument("--trajectory-context", type=Path, required=True)
    parser.add_argument("--stateful-result", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--suite",
        choices=(LEGACY_METRIC_SUITE, PAPER_METRIC_SUITE, "both"),
        default="both",
    )
    parser.add_argument("--model", help="Optional judge model override")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env(args.env_file)
    context, source_payload = load_trajectory_context_artifact(args.trajectory_context)
    stateful_result = _read_json(args.stateful_result)
    selected = (
        (LEGACY_METRIC_SUITE, PAPER_METRIC_SUITE)
        if args.suite == "both"
        else (args.suite,)
    )
    output_dir = args.output_dir.expanduser()
    judge = LLMMetricJudge(model_name=args.model)

    comparison: dict[str, Any] = {
        "source": {
            "trajectory_context": str(args.trajectory_context),
            "stateful_result": str(args.stateful_result or ""),
            "session_id": source_payload.get("session_id"),
        },
        "suites": {},
    }
    for suite_name in selected:
        results = evaluate_metric_suite_batched(
            context,
            metric_suite=suite_name,
            stateful_result=stateful_result,
            judge=judge,
        )
        payloads = [result.to_payload() for result in results]
        suite_path = output_dir / f"trajectory_context_metrics.{suite_name}.json"
        _write_json(suite_path, payloads)
        comparison["suites"][suite_name] = {
            **_suite_summary(payloads),
            "artifact": str(suite_path),
        }

    comparison_path = output_dir / "trajectory_context_metric_comparison.json"
    _write_json(comparison_path, comparison)
    print(json.dumps(comparison, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
