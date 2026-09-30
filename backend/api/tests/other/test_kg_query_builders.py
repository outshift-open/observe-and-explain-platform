#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from oxp.interfaces.models import EdgeFacet
from oxp.query_builders.kg import (
    fetch_agent_call_sequence_query,
    fetch_call_content_and_names_query,
    fetch_session_query,
    fetch_traversed_nodes_query,
    list_sessions_in_interval_query,
)


def test_fetch_agent_call_sequence_query_uses_current_edge_names() -> None:
    query, params = fetch_agent_call_sequence_query("sess-123")

    assert params == {"session_id": "sess-123"}
    assert "[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)" in query
    assert "RETURN ac AS agent_call" in query
    assert "ORDER BY ac.startTime" in query


def test_list_sessions_in_interval_query_supports_optional_bounds() -> None:
    query, params = list_sessions_in_interval_query(
        "2026-03-01T00:00:00", "2026-03-02T00:00:00"
    )

    assert params["start_time"] == "2026-03-01T00:00:00"
    assert params["end_time"] == "2026-03-02T00:00:00"
    assert "($start_time IS NULL OR s.startTime >= $start_time)" in query
    assert "($end_time IS NULL OR s.startTime <= $end_time)" in query


def test_fetch_traversed_nodes_query_builds_generic_edge_chain() -> None:
    query, params = fetch_traversed_nodes_query(
        "sess-123",
        "mas:ToolCall",
        edges=[
            EdgeFacet(
                "hasMASCall", source_entity="mas:Session", target_entity="mas:MASCall"
            ),
            EdgeFacet(
                "hasAgentCall",
                source_entity="mas:MASCall",
                target_entity="mas:AgentCall",
            ),
            EdgeFacet(
                "hasToolCall",
                source_entity="mas:AgentCall",
                target_entity="mas:ToolCall",
            ),
        ],
        order_by=["timestamp"],
    )

    assert params == {"session_id": "sess-123"}
    assert "MATCH (s:Session {sessionId: $session_id})" in query
    assert "MATCH (s)-[:hasMASCall]->(v0:MASCall)" in query
    assert "MATCH (v0)-[:hasAgentCall]->(v1:AgentCall)" in query
    assert "MATCH (v1)-[:hasToolCall]->(n:ToolCall)" in query
    assert "RETURN n AS node" in query


def test_fetch_traversed_nodes_query_uses_only_edges_needed_for_target() -> None:
    query, params = fetch_traversed_nodes_query(
        "sess-123",
        "mas:LLMCall",
        edges=[
            EdgeFacet(
                "hasMASCall", source_entity="mas:Session", target_entity="mas:MASCall"
            ),
            EdgeFacet(
                "hasAgentCall",
                source_entity="mas:MASCall",
                target_entity="mas:AgentCall",
            ),
            EdgeFacet(
                "hasToolCall",
                source_entity="mas:AgentCall",
                target_entity="mas:ToolCall",
            ),
            EdgeFacet(
                "hasLLMCall", source_entity="mas:AgentCall", target_entity="mas:LLMCall"
            ),
        ],
        order_by=["timestamp"],
    )

    assert params == {"session_id": "sess-123"}
    assert "MATCH (s)-[:hasMASCall]->(v0:MASCall)" in query
    assert "MATCH (v0)-[:hasAgentCall]->(v1:AgentCall)" in query
    assert "MATCH (v1)-[:hasLLMCall]->(n:LLMCall)" in query
    assert "hasToolCall" not in query


def test_fetch_session_query_uses_current_edge_names() -> None:
    query, params = fetch_session_query("sess-123")

    assert params == {"session_id": "sess-123"}
    assert "MATCH (s:Session {sessionId: $session_id})" in query
    assert "[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)" in query
    assert "OPTIONAL MATCH (ac)-[:hasLLMCall]->(lc:LLMCall)" in query
    assert "OPTIONAL MATCH (ac)-[:hasToolCall]->(tc:ToolCall)" in query
    assert "OPTIONAL MATCH (ac)-[:hasProcessingCall]->(pc:ProcessingCall)" in query
    assert "HAS_OPERATION" not in query


def test_fetch_call_content_and_names_query_batches_by_id() -> None:
    query, params = fetch_call_content_and_names_query(["a-1", "l-1", "t-1"])

    assert params == {"call_ids": ["a-1", "l-1", "t-1"]}
    assert "UNWIND $call_ids AS call_id" in query
    assert "executesAgent|executesTool|executesLLM|executesProcessing" in query
    assert "hasInitialState" in query
    assert "hasFinalState" in query
