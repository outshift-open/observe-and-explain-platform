#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext
from stateful_evals_be.evaluation.trajectory_context_metrics import (
    TRAJECTORY_METRIC_CODES,
    TRAJECTORY_METRIC_SET,
    available_trajectory_metrics,
    build_trajectory_metrics,
    evaluate_trajectory_metrics_batched,
    resolve_trajectory_metric_codes,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import JudgeUsage
from stateful_evals_be.models.requests import TemporalMetricOptions


class PassingJudge:
    def __init__(self) -> None:
        self.last_usage = JudgeUsage(
            prompt_tokens=20,
            completion_tokens=5,
            total_tokens=25,
        )

    def judge_batch(
        self,
        *,
        metrics_payload: Sequence[Mapping[str, Any]],
        shared_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del shared_context
        return {
            "metrics": [
                {
                    "high_level_metric": item["high_level_metric"],
                    "score": 1,
                    "reasoning": "The metric passes.",
                    "fatal_failures": [],
                    "minor_failures": [],
                }
                for item in metrics_payload
            ]
        }

    def judge(
        self,
        *,
        metric_name: str,
        rubric: str,
        context_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del rubric, context_payload
        return {
            "high_level_metric": metric_name,
            "score": 1,
            "reasoning": "The metric passes.",
            "fatal_failures": [],
            "minor_failures": [],
        }


def test_registry_exposes_official_metric_set() -> None:
    definitions = available_trajectory_metrics()

    assert len(definitions) == 13
    assert tuple(item["code"] for item in definitions) == TRAJECTORY_METRIC_CODES
    assert {item["metric_set"] for item in definitions} == {TRAJECTORY_METRIC_SET}
    assert "paper" not in str(definitions).casefold()


def test_metric_selection_accepts_all_codes_and_display_names() -> None:
    assert resolve_trajectory_metric_codes(["all"]) == TRAJECTORY_METRIC_CODES
    assert resolve_trajectory_metric_codes(
        ["Delegation Accuracy", "groundedness", "delegation_accuracy"]
    ) == ("delegation_accuracy", "groundedness")
    assert [
        metric.name for metric in build_trajectory_metrics(["task_completion"])
    ] == ["Task Completion"]


def test_metric_selection_rejects_unknown_or_ambiguous_all() -> None:
    with pytest.raises(ValueError, match="Unknown trajectory metric"):
        resolve_trajectory_metric_codes(["made_up_metric"])
    with pytest.raises(ValueError, match="must be the only"):
        resolve_trajectory_metric_codes(["all", "groundedness"])


def test_temporal_options_normalize_selected_metrics_and_default_to_opt_out() -> None:
    assert TemporalMetricOptions().trajectory_metrics is None
    assert TemporalMetricOptions(trajectory_metrics=["all"]).trajectory_metrics == list(
        TRAJECTORY_METRIC_CODES
    )
    assert TemporalMetricOptions(
        trajectory_metrics=["Groundedness", "task_completion"]
    ).trajectory_metrics == ["groundedness", "task_completion"]


def test_selected_results_use_official_metadata_and_never_affect_score() -> None:
    context = TrajectoryContext("Verify material claims.")
    context.latest_root_answer = "The requested work is complete."
    context.latest_root_answer_span_index = 2
    results = evaluate_trajectory_metrics_batched(
        context,
        ["instruction_following", "task_completion"],
        stateful_result={"trajectory_score": 1},
        judge=PassingJudge(),
    )

    assert [result.high_level_metric for result in results] == [
        "Instruction Following",
        "Task Completion",
    ]
    assert all(
        result.metadata["metric_set"] == TRAJECTORY_METRIC_SET for result in results
    )
    assert all(
        result.metadata["definition_version"] == TRAJECTORY_METRIC_SET
        for result in results
    )
    assert [result.metadata["metric_layer"] for result in results] == [
        "execution",
        "outcome",
    ]
    assert all(
        result.metadata["affects_trajectory_score"] is False for result in results
    )


def test_all_selector_returns_every_registered_metric() -> None:
    context = TrajectoryContext("Complete the requested task.")
    context.latest_root_answer = "The requested task is complete."
    context.latest_root_answer_span_index = 2

    results = evaluate_trajectory_metrics_batched(
        context,
        ["all"],
        stateful_result={"trajectory_score": 1},
        judge=PassingJudge(),
    )

    assert len(results) == 13
    assert [result.metadata["metric_code"] for result in results] == list(
        TRAJECTORY_METRIC_CODES
    )
    assert all(
        result.metadata["affects_trajectory_score"] is False for result in results
    )
