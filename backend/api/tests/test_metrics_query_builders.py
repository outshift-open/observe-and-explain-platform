#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Metric readers query the ontology Metric + MetricResult model (no DB needed)."""

from datetime import datetime, timezone

import pytest

from oxp.query_builders import metrics as qb

FORBIDDEN = (
    "hasMetric",
    ":Span",
    "hasSpan",
    "measuresCall",
    "m.metricResult",
    "m.metricName",
    "m.value",
    "m.provider",
    "(m:Metric",
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)

QUERIES = {
    "session_h0": lambda: qb.session_metrics_query("s1", hops=0),
    "session_h2": lambda: qb.session_metrics_query("s1", hops=2),
    "span_h0": lambda: qb.span_metrics_query("sp1", hops=0),
    "span_session_h2": lambda: qb.span_metrics_query("sp1", session_id="s1", hops=2),
    "metrics": lambda: qb.metrics_query("app", ["Cost"], start_time="0", end_time="10"),
    "metrics_agent": lambda: qb.metrics_query("app", ["Cost"], agent_id="planner"),
    "over_time": lambda: qb.metrics_over_time_query(
        "Cost", START, START, "day", "app", "planner"
    ),
    "timeline": lambda: qb.get_application_metrics_timeline("app", ["Cost"]),
    "reliability": lambda: qb.reliability_metrics("app"),
}


@pytest.mark.parametrize("name", QUERIES)
def test_readers_use_the_ontology_model(name):
    query, _ = QUERIES[name]()
    assert "MetricResult" in query
    assert "[:measures]" in query or "measures]" in query
    assert ":ofMetricType" in query
    for legacy in FORBIDDEN:
        assert legacy not in query, legacy


def test_session_query_params_and_projection():
    query, params = qb.session_metrics_query("s1", hops=0)
    assert params == {"session_id": "s1"}
    assert "(r:MetricResult)-[:measures]->(session)" in query
    for projected in ("d.name", "r.result", "d.metricProvider", "r.reasoning"):
        assert projected in query


def test_hops_subgraph_does_not_traverse_definitions():
    query, _ = qb.session_metrics_query("s1", hops=3)
    assert "[*1..3]" in query
    assert "n:Metric" in query


def test_span_query_targets_execution_elements():
    query, params = qb.span_metrics_query("sp1", session_id="s1", hops=0)
    assert params == {"span_id": "sp1", "session_id": "s1"}
    assert "LLMCall|ToolCall|AgentCall" in query
    assert "span.sessionId = $session_id" in query
    _, params = qb.span_metrics_query("sp1")
    assert params == {"span_id": "sp1"}


def test_metrics_query_rows_keep_their_keys_and_time_filter():
    query, params = qb.metrics_query("app", ["Cost"], start_time="0")
    for key in (
        "metricName",
        "metricResult",
        "value",
        "provider",
        "source",
        "timestamp",
    ):
        assert f"AS {key}" in query
    assert "r.timestamp >= datetime($start_time)" in query
    assert params["metric_names"] == ["Cost"]
    assert "UNION" not in query


def test_agent_filter_includes_the_agent_calls_and_their_llm_tool_calls():
    query, params = qb.metrics_query("app", ["Cost"], agent_id="planner")
    assert params["agent_id"] == "planner"
    assert "UNION" in query
    assert "AgentCall" in query and "hasLLMCall|hasToolCall*0..1" in query


def test_over_time_and_timeline_filters():
    query, params = qb.metrics_over_time_query("Cost", START, START, "day", "app", "p")
    assert "d.name = $metric_id" in query and "s.appName = $app_name" in query
    assert params["agent_id"] == "p"
    query, _ = qb.get_application_metrics_timeline("app", ["Cost"])
    assert "-[:executesSession]->(:MAS" in query
