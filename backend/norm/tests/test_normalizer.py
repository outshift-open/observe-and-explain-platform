#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for the top-level normalize()/Normalizer API."""

from __future__ import annotations

import json

from norm import Normalizer, normalize


def _agent_span(session_id: str = "sess-1") -> dict:
    return {
        "Timestamp": "2026-07-09 12:00:00.000000000",
        "SpanId": "span-1",
        "ParentSpanId": "",
        "SpanName": "concierge.agent",
        "Duration": 1_000_000_000,
        "SpanAttributes": {
            "application_id": "app",
            "session.id": f"app_{session_id}",
            "agent_id": "concierge",
        },
    }


def test_normalize_returns_nodes_and_edges() -> None:
    nodes, edges = normalize([_agent_span()])
    assert any(node.get("node_type") == "AgentCall" for node in nodes)
    assert edges


def test_success_propagates_from_execution_success_attribute() -> None:
    span = _agent_span()
    span["SpanAttributes"]["execution.success"] = "true"
    nodes, _edges = normalize([span])
    agent_call = next(n for n in nodes if n["node_type"] == "AgentCall")
    assert agent_call["success"] is True


def test_success_defaults_true_when_span_carries_no_signal() -> None:
    nodes, _edges = normalize([_agent_span()])
    agent_call = next(n for n in nodes if n["node_type"] == "AgentCall")
    assert agent_call["success"] is True


def test_success_is_false_on_explicit_error_status_code() -> None:
    span = _agent_span()
    span["StatusCode"] = "Error"
    nodes, _edges = normalize([span])
    agent_call = next(n for n in nodes if n["node_type"] == "AgentCall")
    assert agent_call["success"] is False


def test_normalizer_process_file_matches_normalize(tmp_path) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text(json.dumps(_agent_span()) + "\n", encoding="utf-8")

    nodes, edges = Normalizer().process_file(path)
    expected_nodes, expected_edges = normalize([_agent_span()])
    assert len(nodes) == len(expected_nodes)
    assert len(edges) == len(expected_edges)


def test_normalizer_process_file_json_returns_flat_list(tmp_path) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text(json.dumps(_agent_span()) + "\n", encoding="utf-8")

    flat = Normalizer().process_file_json(path)
    nodes, edges = normalize([_agent_span()])
    assert len(flat) == len(nodes) + len(edges)
