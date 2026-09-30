#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from stateful_evals_be import available_metrics, session_result_payload
from stateful_evals_be.evaluation.processor import CORE_METRICS
from stateful_evals_be.models.requests import SessionResult


def test_session_result_adds_metrics_without_changing_correctness_fields() -> None:
    result = session_result_payload(
        SessionResult(
            session_id="session-1",
            trajectory_score=1,
            trajectory_reasoning="Correctness passed.",
            trajectory_metric_set="trajectory_v1",
            trajectory_metrics=[
                {
                    "high_level_metric": "Groundedness",
                    "score": 0,
                    "reasoning": "An unsupported claim was found.",
                }
            ],
        )
    )

    assert result["trajectory_score"] == 1
    assert result["trajectory_reasoning"] == "Correctness passed."
    assert result["trajectory_metrics"][0]["score"] == 0
    assert result["fatal_failures"] == []


def test_default_session_payload_keeps_previous_shape() -> None:
    result = session_result_payload(
        SessionResult(
            session_id="session-1",
            trajectory_score=1,
            trajectory_reasoning="Correctness passed.",
        )
    )

    assert result["trajectory_score"] == 1
    assert "trajectory_metric_set" not in result
    assert "trajectory_metrics" not in result


def test_session_model_retains_additive_metric_fields_for_in_process_callers() -> None:
    result = SessionResult(
        session_id="session-1",
        trajectory_score=1,
        trajectory_reasoning="Correctness passed.",
        trajectory_metric_set="trajectory_v1",
        trajectory_metrics=[
            {
                "high_level_metric": "Groundedness",
                "score": 0,
                "reasoning": "An unsupported claim was found.",
            }
        ],
    ).model_dump()

    assert result["trajectory_metric_set"] == "trajectory_v1"
    assert result["trajectory_metrics"][0]["high_level_metric"] == "Groundedness"


def test_metric_registry_keeps_span_contract_and_adds_trajectory_registry() -> None:
    payload = available_metrics()

    assert payload["total_metrics"] == len(payload["metrics"])
    assert payload["metrics"] == CORE_METRICS
    assert payload["trajectory_metric_set"] == "trajectory_v1"
    assert len(payload["trajectory_metrics"]) == 13
