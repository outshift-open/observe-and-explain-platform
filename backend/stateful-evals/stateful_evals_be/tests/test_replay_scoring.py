#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from stateful_evals_be.evaluation.replay_scoring import (
    get_profile,
    is_procedural_tool_precondition_fatal,
    rescore_session_result,
)


def test_procedural_tool_precondition_detector() -> None:
    procedural = {
        "span_type": "tool",
        "observed_impact": "wrong_action",
        "reasoning": (
            "The agent executed a database-updating tool call without first "
            "authenticating the user."
        ),
        "explanation": "Required precondition: explicit confirmation before update.",
    }
    hard_wrong_target = {
        "span_type": "tool",
        "observed_impact": "wrong_action",
        "reasoning": (
            "Executed update without confirmation and targeted the wrong order id."
        ),
        "explanation": "",
    }

    assert is_procedural_tool_precondition_fatal(procedural)
    assert not is_procedural_tool_precondition_fatal(hard_wrong_target)


def test_response_drift_relaxed_profile() -> None:
    result = {
        "unsatisfied_intents": 0,
        "fatal_failures": [],
        "minor_failures": [
            {"observed_impact": "none"},
            {"observed_impact": "none"},
        ],
        "intent_states": [
            {
                "name": "query_graph_database",
                "state": "fulfilled",
                "timeline": [{"span_index": 10, "span_type": "tool"}],
            },
            {"name": "response_span_20", "state": "drifting", "timeline": []},
            {"name": "response_span_30", "state": "drifting", "timeline": []},
        ],
        "total_spans": 50,
    }

    current = rescore_session_result(result, get_profile("legacy_current"))
    relaxed = rescore_session_result(result, get_profile("response_drift_relaxed"))

    assert current.predicted_label == 0
    assert "response_span_drifting" in current.quality_gate_failures
    assert relaxed.predicted_label == 1
    assert "response_span_drifting" not in relaxed.quality_gate_failures


def test_procedural_fatal_relaxation_clears_unsatisfied() -> None:
    result = {
        "unsatisfied_intents": 1,
        "fatal_failures": [
            {
                "metric": "IntentRecognitionAccuracy",
                "span_type": "tool",
                "span_index": 12,
                "observed_impact": "wrong_action",
                "reasoning": (
                    "The agent executed modify_pending_order_address without first "
                    "authenticating the user."
                ),
                "explanation": "Required precondition not met before update.",
            }
        ],
        "minor_failures": [],
        "intent_states": [
            {
                "name": "modify_pending_order_address",
                "state": "failed",
                "timeline": [{"span_index": 12, "span_type": "tool"}],
            }
        ],
        "total_spans": 20,
    }

    current = rescore_session_result(result, get_profile("legacy_current"))
    relaxed = rescore_session_result(result, get_profile("procedural_fatal_relaxed"))

    assert current.predicted_label == 0
    assert len(current.adjusted_fatal_failures) == 1
    assert current.adjusted_unsatisfied_intents == 1

    assert relaxed.predicted_label == 1
    assert len(relaxed.adjusted_fatal_failures) == 0
    assert relaxed.adjusted_unsatisfied_intents == 0
    assert len(relaxed.downgraded_fatal_failures) == 1
