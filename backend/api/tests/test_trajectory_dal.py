#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Session-trajectory DAL functions, against a fake connector (no Neo4j)."""

from __future__ import annotations

import json

import pytest
from oxp.client.dal import get_session_trajectory, write_transition_context
from oxp.core.exceptions import DatabaseError
from oxp.interfaces.models import MetricResult
from oxp.providers import OXPMetricsProvider


def step_row(
    tid,
    kind,
    name,
    start,
    i="",
    o="",
    *,
    agent="specialist",
    desc=None,
    ok=True,
    parent="agentcall:a1",
):
    return {
        "transition_id": tid,
        "call_id": tid.replace("transition", kind + "call"),
        "kind": kind,
        "name": name,
        "description": desc,
        "agent": agent,
        "parent_id": None if kind == "agent" else parent,
        "success": ok,
        "start_time": start,
        "duration_ms": 1000.0,
        "input_text": i,
        "output_text": o,
    }


class FakeConnector:
    """Returns canned rows for the read query; records every call."""

    def __init__(self, steps=(), write_rows=({"ok": 1},)):
        self.steps = list(steps)
        self.write_rows = list(write_rows)
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "RETURN t.id AS transition_id" in query:
            return self.steps
        return self.write_rows  # any write query


@pytest.fixture
def connector():
    return FakeConnector(
        steps=[
            step_row(
                "transition:a1",
                "agent",
                "specialist",
                1.0,
                "ain",
                "(no content recorded)",
            ),
            step_row(
                "transition:t2", "llm", "gpt-4o", 2.0, "in2", "(no content recorded)"
            ),
            step_row(
                "transition:t3",
                "tool",
                "read_document",
                3.0,
                "{}",
                '"x"',
                desc="Reads a document",
            ),
            step_row(
                "transition:t2", "llm", "gpt-4o", 2.0, "dup", "dup"
            ),  # duplicate row ignored
            step_row("transition:t4", "llm", "gpt-4o", 5.0, "in4", "out4", agent=None),
        ]
    )


def test_get_session_trajectory_is_one_query(connector):
    get_session_trajectory(connector, "s1")

    assert len(connector.calls) == 1
    query, params = connector.calls[0]
    assert params == {"session_id": "s1"}
    assert "ORDER BY c.startTime" in query
    assert not any(w in query for w in ("MERGE", "SET ", "DELETE", "CREATE"))


def test_get_session_trajectory_steps(connector):
    trajectory = get_session_trajectory(connector, "s1")

    assert trajectory["session_id"] == "s1"
    assert [s["transition_id"] for s in trajectory["steps"]] == [
        "transition:a1",
        "transition:t2",
        "transition:t3",
        "transition:t4",
    ]
    agent, llm, tool, no_agent = trajectory["steps"]
    assert (
        agent["kind"] == "agent"
        and agent["agent_id"] == "specialist"
        and agent["parent_id"] == ""
    )
    assert llm["parent_id"] == "agentcall:a1"
    assert (
        llm["kind"] == "llm"
        and llm["agent_id"] == "specialist"
        and llm["description"] == ""
    )
    assert llm["input_text"] == "in2"  # first row of a duplicated transition wins
    assert (
        llm["output_text"] == "(no content recorded)"
    )  # State text is passed through untouched
    assert tool["kind"] == "tool" and tool["description"] == "Reads a document"
    assert tool["call_id"] == "toolcall:t3" and tool["duration_ms"] == 1000.0
    assert no_agent["agent_id"] == ""


def test_get_session_trajectory_without_data():
    assert get_session_trajectory(FakeConnector(), "s1") == {
        "session_id": "s1",
        "steps": [],
    }


def test_get_session_trajectory_rejects_empty_session_id(connector):
    with pytest.raises(ValueError):
        get_session_trajectory(connector, "  ")


def test_get_session_trajectory_wraps_database_errors():
    class Broken:
        def execute(self, *_a, **_k):
            raise RuntimeError("neo4j down")

    with pytest.raises(DatabaseError, match="neo4j down"):
        get_session_trajectory(Broken(), "s1")


def test_write_transition_context_splits_the_context_into_node_properties(connector):
    context = {
        "evidence": [{"index": 0, "fact_type": "tool_output"}],
        "claims": [{"index": 0}],
        "intents": [{"index": 2, "status": "unassessed"}],
        "work_units": [{"index": 1}],
        "provenance_links": [{"index": 3}],
        "coordination_events": [{"index": 0}],
        "flags": [{"index": 0}],
        "final_answer": {"span_index": 3, "text": "Yes, direct."},
    }
    assert write_transition_context(connector, "s1", "transition:t2", context)

    query, params = connector.calls[0]
    assert "MERGE (c:TrajectoryContext {id: $context_id})" in query
    assert "SET c = $properties" in query
    assert "MERGE (t)-[:hasContext]->(c)" in query
    assert "(t:Transition {id: $transition_id, sessionId: $session_id})" in query
    assert params["session_id"] == "s1" and params["transition_id"] == "transition:t2"
    properties = params["properties"]
    assert properties["id"] == params["context_id"]
    assert (properties["name"], properties["layer"]) == ("", "semantic")
    assert json.loads(properties["evidence"]) == context["evidence"]
    assert json.loads(properties["claims"]) == context["claims"]
    assert json.loads(properties["intents"]) == context["intents"]
    assert json.loads(properties["workUnits"]) == context["work_units"]
    assert json.loads(properties["provenanceLinks"]) == context["provenance_links"]
    assert (
        json.loads(properties["coordinationEvents"]) == context["coordination_events"]
    )
    assert json.loads(properties["flags"]) == context["flags"]
    assert properties["finalAnswer"] == "Yes, direct."


def test_write_transition_context_only_sets_what_the_transition_contributed(connector):
    write_transition_context(
        connector, "s1", "transition:t2", {"claims": [{"index": 0}]}
    )
    properties = connector.calls[0][1]["properties"]
    assert set(properties) == {"id", "name", "layer", "claims"}


def test_write_transition_context_ignores_unknown_entries(connector):
    write_transition_context(
        connector, "s1", "transition:t2", {"claims": [], "mystery": [1]}
    )
    assert "mystery" not in " ".join(connector.calls[0][1]["properties"])


def test_write_transition_context_is_idempotent_per_transition(connector):
    write_transition_context(connector, "s1", "transition:t2", {"a": 1})
    write_transition_context(connector, "s1", "transition:t2", {"a": 2})
    write_transition_context(connector, "s1", "transition:t3", {"a": 1})

    ids = [params["context_id"] for _, params in connector.calls]
    assert ids[0] == ids[1] != ids[2]
    assert ids[0].startswith("context:")


def test_write_transition_context_reports_a_missing_transition():
    assert write_transition_context(FakeConnector(write_rows=[]), "s", "t", {}) is False


class _CommandConnector:
    def __init__(self):
        self.commands = []

    def ensure_connected(self):
        return None

    def execute_command(self, query, params):
        self.commands.append((query, params))


def test_provider_saves_transition_metrics():
    db = _CommandConnector()
    metric = MetricResult(
        metric_id="mdt.Relevancy",
        resource_id="transition:t2",
        provider="stateful_evals",
        value=1.0,
        reasoning="ok",
        metadata={"metric_id": None, "source": "StatefulEval"},
    )

    assert (
        OXPMetricsProvider(db=db).save_transition_metrics(
            "s1", "transition:t2", [metric]
        )
        is True
    )

    ((query, params),) = db.commands
    assert "(t:Transition {id: $transition_id, sessionId: $session_id})" in query
    assert "Span" not in query
    assert params["transition_id"] == "transition:t2" and params["session_id"] == "s1"
    assert params["metric_name"] == "mdt.Relevancy" and params["metric_value"] == 1.0
    assert params["provider"] == "stateful_evals" and params["source"] == "StatefulEval"
    assert params["metric_id"] == "mdt.Relevancy" and params["reasoning"] == "ok"


def test_provider_skips_errored_or_valueless_transition_metrics():
    db = _CommandConnector()
    metrics = [
        MetricResult(metric_id="a", resource_id="t", provider="p", value=None),
        MetricResult(
            metric_id="b", resource_id="t", provider="p", value=1.0, error="boom"
        ),
    ]
    assert OXPMetricsProvider(db=db).save_transition_metrics("s", "t", metrics) is True
    assert db.commands == []


def test_provider_reports_transition_write_failures():
    class Failing(_CommandConnector):
        def execute_command(self, query, params):
            raise RuntimeError("neo4j down")

    metric = MetricResult(metric_id="a", resource_id="t", provider="p", value=1.0)
    assert (
        OXPMetricsProvider(db=Failing()).save_transition_metrics("s", "t", [metric])
        is False
    )
