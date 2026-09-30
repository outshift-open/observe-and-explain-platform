#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from oxp.interfaces.models import (
    AggregateFacet,
    EdgeFacet,
    NodeFacet,
    RetrievalRequest,
    RetrievalScope,
)
from oxp.providers.kg import OXPKGProvider


class FakeConnector:
    def __init__(self) -> None:
        self.fetch_session_calls = 0

    def ensure_connected(self) -> None:
        return None

    def execute(self, query: str, params: dict):
        if "RETURN s.sessionId AS session_id, s.startTime AS timestamp" in query:
            return [
                {"session_id": "session-1", "timestamp": "2026-03-01T10:00:00"},
                {"session_id": "session-2", "timestamp": "2026-03-01T11:00:00"},
            ]

        if "UNWIND $call_ids AS call_id" in query:
            enrichment = {
                "t-1": {
                    "name": "planner",
                    "inputContent": "find documents",
                    "outputContent": "tool-result",
                },
                "1": {"name": "A"},
                "2": {"name": "B"},
                "3": {"name": "C"},
                "a-1": {"name": "planner"},
            }
            return [
                {"id": call_id, **enrichment[call_id]}
                for call_id in params.get("call_ids", [])
                if call_id in enrichment
            ]

        if (
            "RETURN n AS node" in query
            and "ToolCall" in query
            and params.get("session_id") == "session-1"
        ):
            return [
                {"node": {"id": "t-1", "startTime": 4}},
            ]

        session_id = params.get("session_id")
        if (
            "RETURN n AS node" in query
            and "AgentCall" in query
            and session_id == "session-1"
        ):
            return [
                {"node": {"id": "2", "startTime": 2}},
                {"node": {"id": "1", "startTime": 1}},
            ]
        if (
            "RETURN n AS node" in query
            and "AgentCall" in query
            and session_id == "session-2"
        ):
            return [
                {"node": {"id": "3", "startTime": 3}},
            ]

        if "collect(DISTINCT ac)" in query:
            self.fetch_session_calls += 1
            return [
                {
                    "s": {"sessionId": session_id},
                    "agent_calls": [{"id": "a-1"}],
                    "llm_calls": [{"id": "l-1", "success": False}],
                    "tool_calls": [{"id": "t-1"}],
                    "processing_calls": [],
                }
            ]

        if "hasInitialState]->(initial:State)" in query and "Session" in query:
            return [{"input": None, "output": None}]

        return []


class PartialConversationConnector:
    def ensure_connected(self) -> None:
        return None

    def execute(self, query: str, params: dict):
        session_id = params.get("session_id")

        if "collect(DISTINCT ac)" in query:
            return [
                {
                    "s": {"sessionId": session_id},
                    "agent_calls": [],
                    "llm_calls": [{"id": "l-1", "success": True}],
                    "tool_calls": [{"id": "t-1", "success": False}],
                    "processing_calls": [],
                }
            ]

        if "UNWIND $call_ids AS call_id" in query:
            enrichment = {
                "l-1": {"inputContent": "What is 2+2?", "outputContent": "4"},
                "t-1": {
                    "inputContent": '{"q": "math"}',
                    "outputContent": "calculator failed",
                },
            }
            return [
                {"id": call_id, **enrichment[call_id]}
                for call_id in params.get("call_ids", [])
                if call_id in enrichment
            ]

        if "hasInitialState]->(initial:State)" in query and "Session" in query:
            return [{"input": None, "output": None}]

        return []


def test_retrieve_supports_time_interval_and_count_aggregate() -> None:
    provider = OXPKGProvider(db=FakeConnector())

    request = RetrievalRequest(
        scope=RetrievalScope(
            start_time="2026-03-01T09:00:00",
            end_time="2026-03-01T12:00:00",
        ),
        nodes=[
            NodeFacet(
                entity_type="mas:AgentCall",
                alias="agent_calls",
                order_by=["startTime"],
            )
        ],
        edges=[
            EdgeFacet(
                "hasMASCall", source_entity="mas:Session", target_entity="mas:MASCall"
            ),
            EdgeFacet(
                "hasAgentCall",
                source_entity="mas:MASCall",
                target_entity="mas:AgentCall",
            ),
        ],
        aggregates=[
            AggregateFacet(
                function="count",
                entity_type="mas:AgentCall",
                alias="agent_call_count",
            )
        ],
    )

    result = provider.retrieve(request)

    assert result["session_ids"] == ["session-1", "session-2"]
    assert result["contexts"]["session-1"]["agent_calls"][0]["agentName"] == "A"
    assert result["contexts"]["session-1"]["agent_call_count"] == 2
    assert result["contexts"]["session-2"]["agent_call_count"] == 1


def test_fetch_uses_retrieval_request_for_single_session() -> None:
    provider = OXPKGProvider(db=FakeConnector())
    result = provider.fetch(
        "session-1",
        requirements=type(
            "Req",
            (),
            {
                "retrieval": RetrievalRequest(
                    nodes=[NodeFacet(entity_type="mas:AgentCall", alias="agent_calls")],
                    edges=[
                        EdgeFacet(
                            "hasMASCall",
                            source_entity="mas:Session",
                            target_entity="mas:MASCall",
                        ),
                        EdgeFacet(
                            "hasAgentCall",
                            source_entity="mas:MASCall",
                            target_entity="mas:AgentCall",
                        ),
                    ],
                )
            },
        )(),
    )

    assert result["session_id"] == "session-1"
    assert [call["agentName"] for call in result["agent_calls"]] == ["A", "B"]


def test_retrieve_compiles_generic_toolcall_chain() -> None:
    provider = OXPKGProvider(db=FakeConnector())
    result = provider.retrieve(
        RetrievalRequest(
            scope=RetrievalScope(session_ids=["session-1"]),
            nodes=[NodeFacet(entity_type="mas:ToolCall", alias="tool_calls")],
            edges=[
                EdgeFacet(
                    "hasMASCall",
                    source_entity="mas:Session",
                    target_entity="mas:MASCall",
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
        )
    )

    assert result["contexts"]["session-1"]["tool_calls"][0]["toolName"] == "planner"


def test_retrieve_enriches_toolcall_output_from_state_content() -> None:
    provider = OXPKGProvider(db=FakeConnector())
    result = provider.retrieve(
        RetrievalRequest(
            scope=RetrievalScope(session_ids=["session-1"]),
            nodes=[
                NodeFacet(
                    entity_type="mas:ToolCall",
                    alias="tool_calls",
                    fields=["id", "toolName", "outputContent", "toolOutput"],
                )
            ],
            edges=[
                EdgeFacet(
                    "hasMASCall",
                    source_entity="mas:Session",
                    target_entity="mas:MASCall",
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
        )
    )

    assert result["contexts"]["session-1"]["tool_calls"] == [
        {
            "id": "t-1",
            "toolName": "planner",
            "outputContent": "tool-result",
            "toolOutput": "tool-result",
        }
    ]


def test_normalize_tool_call_aliases_output_content_and_error_flag() -> None:
    node = OXPKGProvider._normalize_tool_call(
        {"id": "tool-1", "success": False},
        enrichment={
            "name": "search",
            "inputContent": '{"q": "x"}',
            "outputContent": "done",
        },
    )

    assert node["toolArguments"] == '{"q": "x"}'
    assert node["toolOutput"] == "done"
    assert node["outputContent"] == "done"
    assert node["contains_error"] is True


def test_normalize_llm_call_aliases_prompt_completion_and_error_flag() -> None:
    node = OXPKGProvider._normalize_llm_call(
        {"id": "llm-1", "success": False},
        enrichment={"inputContent": "prompt", "outputContent": "completion"},
    )

    assert node["prompt"] == "prompt"
    assert node["completion"] == "completion"
    assert node["contains_error"] is True


def test_normalize_calls_leave_contains_error_false_when_success_unset() -> None:
    """success is None (no signal recorded) must not read as an error."""
    node = OXPKGProvider._normalize_llm_call({"id": "llm-1"}, enrichment=None)
    assert node["contains_error"] is False


def test_fetch_returns_llm_and_tool_spans_with_enriched_content() -> None:
    provider = OXPKGProvider(db=FakeConnector())

    result = provider.fetch(
        "session-1",
        requirements=type("Req", (), {"retrieval": None})(),
    )

    assert result["session_id"] == "session-1"
    assert [call["id"] for call in result["llm_spans"]] == ["l-1"]
    assert [call["id"] for call in result["tool_spans"]] == ["t-1"]
    assert result["tool_spans"][0]["toolName"] == "planner"
    assert result["tool_spans"][0]["inputContent"] == "find documents"
    assert result["tool_spans"][0]["outputContent"] == "tool-result"
    assert result["llm_spans"][0]["contains_error"] is True


def test_derive_session_query_response_prefers_agent_spans_then_llm_spans() -> None:
    query, response = OXPKGProvider._derive_session_query_response(
        [{"inputContent": "session question", "outputContent": "session answer"}],
        [{"prompt": "llm question", "completion": "llm answer"}],
    )

    assert query == "session question"
    assert response == "session answer"

    fallback_query, fallback_response = OXPKGProvider._derive_session_query_response(
        [],
        [
            {"prompt": "first question", "completion": "first answer"},
            {"prompt": "second question", "completion": "final answer"},
        ],
    )

    assert fallback_query == "first question"
    assert fallback_response == "final answer"


def test_fetch_fills_partial_conversation_from_llm_spans_and_normalizes_tool_spans() -> (
    None
):
    provider = OXPKGProvider(db=PartialConversationConnector())

    result = provider.fetch(
        "session-1",
        requirements=type("Req", (), {"retrieval": None})(),
    )

    assert result["conversation_data"]["query"] == "What is 2+2?"
    assert result["conversation_data"]["response"] == "4"
    assert result["input_text"] == "What is 2+2?"
    assert result["output_text"] == "4"
    assert result["llm_spans"][0]["prompt"] == "What is 2+2?"
    assert result["llm_spans"][0]["completion"] == "4"
    assert result["tool_spans"][0]["toolArguments"] == '{"q": "math"}'
    assert result["tool_spans"][0]["toolOutput"] == "calculator failed"
    assert result["tool_spans"][0]["contains_error"] is True
