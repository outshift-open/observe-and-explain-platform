#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from stateful_evals_be.evaluation.replay_scoring import (
    get_profile,
    rescore_session_result,
)


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


