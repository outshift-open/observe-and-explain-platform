#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.native.metrics.workflow.agent_to_agent_interactions."""

from unittest.mock import MagicMock
from mce.providers.native.metrics.workflow.agent_to_agent_interactions import (
    AgentToAgentInteractions,
)


class TestAgentToAgentInteractions:
    def test_metadata(self):
        m = AgentToAgentInteractions()
        assert m.metadata.name is not None

    def test_input_requirements(self):
        m = AgentToAgentInteractions()
        reqs = m.input_requirements
        assert "mas:AgentCall" in reqs.required_entities
        assert reqs.retrieval is not None
        assert reqs.allowed_relations == ["hasMASCalls", "hasAgentCalls"]
        assert [edge.relation_type for edge in reqs.retrieval.edges] == [
            "hasMASCalls",
            "hasAgentCalls",
        ]

    def test_compute_with_agent_calls(self):
        m = AgentToAgentInteractions()
        result = m.compute(
            "s1",
            {
                "agent_calls": [
                    {"agentName": "A"},
                    {"agentName": "B"},
                    {"agentName": "A"},
                    {"agentName": "C"},
                ]
            },
        )
        assert result.resource_id == "s1"
        assert result.value == 3
        assert result.metadata["total_transitions"] == 3
        assert result.metadata["transition_counts"] == {"A->B": 1, "B->A": 1, "A->C": 1}

    def test_compute_collapses_duplicate_task_and_call_pairs_legacy_kg_workaround(self):
        m = AgentToAgentInteractions()
        result = m.compute(
            "s1",
            {
                "agent_calls": [
                    {
                        "agentName": "moderator",
                        "executionId": "exec-agent-call-moderator_task_0_1",
                        "spanId": "span-1",
                    },
                    {
                        "agentName": "moderator",
                        "executionId": "exec-agent-call-moderator_call_0_1",
                        "spanId": "span-1",
                    },
                    {
                        "agentName": "schedule_agent",
                        "executionId": "exec-agent-call-schedule_agent_task_0_2",
                        "spanId": "span-2",
                    },
                    {
                        "agentName": "schedule_agent",
                        "executionId": "exec-agent-call-schedule_agent_call_0_2",
                        "spanId": "span-2",
                    },
                    {
                        "agentName": "moderator",
                        "executionId": "exec-agent-call-moderator_task_0_3",
                        "spanId": "span-3",
                    },
                    {
                        "agentName": "moderator",
                        "executionId": "exec-agent-call-moderator_call_0_3",
                        "spanId": "span-3",
                    },
                ]
            },
        )
        assert result.value == 2
        assert result.metadata["transition_counts"] == {
            "moderator->schedule_agent": 1,
            "schedule_agent->moderator": 1,
        }

    def test_compute_empty_context(self):
        m = AgentToAgentInteractions()
        result = m.compute("s1", {})
        assert result.value == 0
        assert result.metadata["total_transitions"] == 0

    def test_compute_from_session_object(self):
        m = AgentToAgentInteractions()
        session = MagicMock()
        session.agent_calls = [{"agentName": "P"}, {"agentName": "Q"}]
        result = m.compute("s1", {"session": session})
        assert "P->Q" in result.metadata["transition_counts"]
