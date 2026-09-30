#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for workflow metric implementations."""

import pytest
from collections import Counter
from unittest.mock import MagicMock, patch
from mce.core.helpers import _query_response
from mce.engine.engine import MetricEngine
from mce.providers.deepeval.wrapper import DeepEvalMetricWrapper
from mce.providers.native.metrics.quality.goal_success_rate import GoalSuccessRate
from mce.providers.native.metrics.quality.groundedness import Groundedness
from mce.providers.native.metrics.quality.intent_recognition_accuracy import (
    IntentRecognitionAccuracy,
)
from mce.providers.native.metrics.quality.response_completeness_v1 import (
    ResponseCompleteness,
)
from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
    ToolUtilizationAccuracy,
)
from mce.providers.native.metrics.safety.llm_error_rate import LLMErrorRate
from mce.providers.native.metrics.workflow.agent_to_tool_interactions import (
    AgentToToolInteractions,
)
from mce.providers.native.metrics.workflow.cycles_count import CyclesCount
from mce.providers.native.metrics.workflow.workflow_cohesion_index import (
    WorkflowCohesionIndex,
)
from mce.providers.native.metrics.workflow.workflow_efficiency import WorkflowEfficiency


class TestAgentToToolInteractions:
    def test_metadata(self):
        m = AgentToToolInteractions()
        assert m.metadata.name is not None

    def test_input_requirements(self):
        m = AgentToToolInteractions()
        assert "mas:ToolCall" in m.input_requirements.required_entities

    def test_compute_with_dict_spans(self):
        m = AgentToToolInteractions()
        spans = [
            {"agent_id": "AgentA", "tool_name": "search"},
            {"agent_id": "AgentA", "tool_name": "search"},
            {"agent_id": "AgentB", "tool_name": "fetch"},
        ]
        result = m.compute("session1", {"tool_spans": spans})
        assert result.resource_id == "session1"
        # value is total tool call count (scalar)
        assert result.value == 3
        assert (
            result.metadata["interaction_counts"].get(
                "(Agent: AgentA) -> (Tool: search)"
            )
            == 2
        )

    def test_compute_with_object_spans(self):
        m = AgentToToolInteractions()
        span = MagicMock(spec=["agent_id", "tool_name"])
        span.agent_id = "AgentX"
        span.tool_name = "mytool"
        result = m.compute("s1", {"tool_spans": [span]})
        assert (
            "(Agent: AgentX) -> (Tool: mytool)" in result.metadata["interaction_counts"]
        )

    def test_compute_skips_spans_without_name(self):
        m = AgentToToolInteractions()
        spans = [{"agent_id": "A", "tool_name": None}]
        result = m.compute("s1", {"tool_spans": spans})
        assert result.value == 0
        assert result.metadata["unique_interactions"] == 0

    def test_compute_from_session_object(self):
        m = AgentToToolInteractions()
        session = MagicMock()
        session.tool_spans = [{"agent_id": "AgentC", "tool_name": "write"}]
        result = m.compute("s1", {"session": session})
        assert (
            "(Agent: AgentC) -> (Tool: write)" in result.metadata["interaction_counts"]
        )

    def test_compute_empty_context(self):
        m = AgentToToolInteractions()
        result = m.compute("s1", {})
        assert result.value == 0
        assert result.metadata["total_tool_calls"] == 0

    def test_compute_uses_workflow_name_fallback(self):
        m = AgentToToolInteractions()
        spans = [{"workflow.name": "WFlow", "tool_name": "run"}]
        result = m.compute("s1", {"tool_spans": spans})
        assert "(Agent: WFlow) -> (Tool: run)" in result.metadata["interaction_counts"]


class TestWorkflowEfficiency:
    def test_metadata(self):
        m = WorkflowEfficiency()
        assert m.metadata.name is not None

    def test_input_requirements(self):
        m = WorkflowEfficiency()
        reqs = m.input_requirements
        assert "mas:AgentCall" in reqs.required_entities
        assert reqs.retrieval is not None
        assert reqs.allowed_relations == ["hasMASCalls", "hasAgentCalls"]
        assert [edge.relation_type for edge in reqs.retrieval.edges] == [
            "hasMASCalls",
            "hasAgentCalls",
        ]

    def test_compute_with_agent_calls(self):
        m = WorkflowEfficiency()
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
        assert isinstance(result.value, float)
        assert result.value == 1.0

    def test_compute_collapses_duplicate_task_and_call_pairs_legacy_kg_workaround(self):
        m = WorkflowEfficiency()
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
                        "agentName": "itinerary_agent",
                        "executionId": "exec-agent-call-itinerary_agent_task_0_2",
                        "spanId": "span-2",
                    },
                    {
                        "agentName": "itinerary_agent",
                        "executionId": "exec-agent-call-itinerary_agent_call_0_2",
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
        assert result.metadata["agent_chain"] == [
            "moderator",
            "itinerary_agent",
            "moderator",
        ]
        assert result.metadata["total_transitions"] == 2
        assert result.value == 1.0

    def test_compute_empty_context(self):
        m = WorkflowEfficiency()
        result = m.compute("s1", {})
        assert result.value == 0.0
        assert result.metadata["total_transitions"] == 0
        assert result.reasoning == "No agent call sequence available for this session."

    def test_compute_from_session_object(self):
        m = WorkflowEfficiency()
        session = MagicMock()
        session.agent_calls = [
            {"agentName": "X"},
            {"agentName": "Y"},
            {"agentName": "Z"},
            {"agentName": "X"},
        ]
        result = m.compute("s1", {"session": session})
        assert result.value > 0

    def test_compute_ignores_calls_without_agent_name(self):
        m = WorkflowEfficiency()
        result = m.compute("s1", {"agent_calls": [{"foo": "bar"}, {"agentName": "A"}]})
        assert result.value == 0.0

    def test_compute_all_unique_transitions(self):
        m = WorkflowEfficiency()
        result = m.compute(
            "s1",
            {
                "agent_calls": [
                    {"agentName": "A"},
                    {"agentName": "B"},
                    {"agentName": "C"},
                    {"agentName": "D"},
                ]
            },
        )
        assert result.value == 1.0

    def test_compute_single_transition_repeated(self):
        m = WorkflowEfficiency()
        result = m.compute(
            "s1",
            {
                "agent_calls": [
                    {"agentName": "A"},
                    {"agentName": "B"},
                    {"agentName": "A"},
                    {"agentName": "B"},
                    {"agentName": "A"},
                    {"agentName": "B"},
                ]
            },
        )
        assert result.value == pytest.approx(0.4, abs=0.01)

    def test_engine_preserves_retrieval_requirements(self):
        class StubProvider:
            def fetch(self, resource_id, requirements):
                assert requirements.retrieval is not None
                assert requirements.retrieval.nodes[0].alias == "agent_calls"
                return {
                    "agent_calls": [
                        {"agentName": "A"},
                        {"agentName": "B"},
                        {"agentName": "A"},
                        {"agentName": "C"},
                    ]
                }

        engine = MetricEngine(max_workers=1, execution_strategy="thread")
        engine.set_data_provider(StubProvider())
        engine.register_metric(WorkflowEfficiency())

        results = engine.compute_session("s1")
        workflow = next(
            result for result in results if result.metric_id == "WorkflowEfficiency"
        )

        assert workflow.error is None
        assert workflow.value == 1.0

    def test_engine_merges_retrieval_requirements_for_session_metrics(self):
        class StubProvider:
            def fetch(self, resource_id, requirements):
                aliases = {node.alias for node in requirements.retrieval.nodes}

                assert requirements.retrieval is not None
                assert {"agent_calls", "tool_spans", "llm_spans"}.issubset(aliases)
                return {
                    "agent_calls": [
                        {"agentName": "A"},
                        {"agentName": "B"},
                        {"agentName": "A"},
                    ],
                    "tool_spans": [
                        {
                            "toolArguments": '{"query": "sales"}',
                            "outputContent": "Sales: $1M",
                            "toolName": "search_db",
                        }
                    ],
                    "llm_spans": [
                        {"executionId": "l1", "status": "ERROR"},
                        {"executionId": "l2", "status": "OK"},
                    ],
                }

        from unittest.mock import patch

        engine = MetricEngine(max_workers=1, execution_strategy="thread")
        engine.set_data_provider(StubProvider())
        engine.register_metric(WorkflowEfficiency())
        engine.register_metric(ToolUtilizationAccuracy())
        engine.register_metric(LLMErrorRate())

        with patch(
            "mce.providers.native.metrics.quality.tool_utilization_accuracy.llm_g_eval_score",
            return_value=(4.0, "looks good", "4"),
        ):
            results = engine.compute_session("s1", recursive=True)

        by_id = {result.metric_id: result for result in results}
        assert by_id["WorkflowEfficiency"].error is None
        assert by_id["ToolUtilizationAccuracy"].error is None
        assert by_id["LLMErrorRate"].error is None

    def test_engine_computes_added_metrics_from_raw_kg_context(self):
        class StubProvider:
            def fetch(self, resource_id, requirements):
                return {
                    "conversation_data": {
                        "query": "How many open incidents remain?",
                        "response": "There are 2 open incidents remaining.",
                        "conversation": "User asks for open incidents. Assistant reports there are 2 open incidents.",
                    },
                    "agent_calls": [
                        {"agentName": "triage"},
                        {"agentName": "incident_lookup"},
                        {"agentName": "triage"},
                    ],
                    "llm_spans": [
                        {
                            "executionId": "l1",
                            "inputContent": "How many open incidents remain?",
                            "outputContent": "Let me check the incident database.",
                            "status": "OK",
                        },
                        {
                            "executionId": "l2",
                            "inputContent": "Summarize the lookup result.",
                            "outputContent": "There are 2 open incidents remaining.",
                            "status": "ERROR",
                            "error": "transient provider timeout",
                        },
                    ],
                    "tool_spans": [
                        {
                            "executionId": "t1",
                            "toolName": "incident_lookup",
                            "inputParams": '{"status": "open"}',
                            "outputContent": "2 incidents found",
                            "status": "OK",
                        }
                    ],
                }

        engine = MetricEngine(max_workers=1, execution_strategy="thread")
        engine.set_data_provider(StubProvider())
        engine.register_metric(Groundedness())
        engine.register_metric(IntentRecognitionAccuracy())
        engine.register_metric(LLMErrorRate())
        engine.register_metric(ToolUtilizationAccuracy())
        engine.register_metric(WorkflowEfficiency())

        with (
            patch(
                "mce.providers.native.metrics._base.llm_g_eval_score",
                return_value=(0.75, "kg-backed context is sufficient", 4.0),
            ),
            patch(
                "mce.providers.native.metrics.quality.tool_utilization_accuracy.llm_g_eval_score",
                return_value=(0.75, "tool call matches the request", 4.0),
            ),
        ):
            results = engine.compute_session("s1", recursive=True)

        by_id = {result.metric_id: result for result in results}

        assert by_id["Groundedness"].error is None
        assert by_id["Groundedness"].value == pytest.approx(0.75, abs=0.01)
        assert "No conversation data" not in by_id["Groundedness"].reasoning

        assert by_id["IntentRecognitionAccuracy"].error is None
        assert by_id["IntentRecognitionAccuracy"].value == pytest.approx(0.75, abs=0.01)
        assert (
            "Missing query/response data"
            not in by_id["IntentRecognitionAccuracy"].reasoning
        )

        assert by_id["LLMErrorRate"].error is None
        assert by_id["LLMErrorRate"].value == pytest.approx(0.5, abs=0.01)

        assert by_id["ToolUtilizationAccuracy"].error is None
        assert by_id["ToolUtilizationAccuracy"].value == pytest.approx(0.75, abs=0.01)

        assert by_id["WorkflowEfficiency"].error is None
        assert by_id["WorkflowEfficiency"].value == pytest.approx(1.0, abs=0.01)

    def test_engine_supplements_retrieval_context_with_base_session_fetch(self):
        class StubProvider:
            def __init__(self):
                self.calls = []

            def fetch(self, resource_id, requirements):
                self.calls.append(requirements.retrieval is not None)

                if requirements.retrieval is not None:
                    return {
                        "agent_calls": [
                            {"agentName": "triage"},
                            {"agentName": "incident_lookup"},
                            {"agentName": "triage"},
                        ],
                        "llm_spans": [
                            {
                                "executionId": "l1",
                                "status": "OK",
                            },
                            {
                                "executionId": "l2",
                                "status": "ERROR",
                                "error": "provider timeout",
                            },
                        ],
                        "tool_spans": [
                            {
                                "executionId": "t1",
                                "toolName": "incident_lookup",
                                "toolArguments": '{"status": "open"}',
                                "outputContent": "2 incidents found",
                                "status": "OK",
                            }
                        ],
                    }

                return {
                    "conversation_data": {
                        "query": "How many open incidents remain?",
                        "response": "There are 2 open incidents remaining.",
                        "conversation": "User asks for open incidents. Assistant reports there are 2 open incidents remaining.",
                    },
                    "agent_spans": [
                        {"agentName": "triage"},
                        {"agentName": "incident_lookup"},
                    ],
                    "tool_spans": [
                        {
                            "executionId": "t1",
                            "toolName": "incident_lookup",
                            "toolArguments": '{"status": "open"}',
                            "outputContent": "2 incidents found",
                            "status": "OK",
                        },
                        {
                            "executionId": "t2",
                            "toolName": "calculator",
                            "toolArguments": '{"expression": "1+1"}',
                            "outputContent": "2",
                            "status": "OK",
                        },
                    ],
                }

        class StubDeepEvalProvider:
            def __init__(self):
                self.calls = []

            def set_model(self, model):
                return None

            def evaluate(self, metric_name, context):
                self.calls.append(metric_name)
                query, response = _query_response(context)

                assert query == "How many open incidents remain?"
                assert response == "There are 2 open incidents remaining."

                return {
                    "score": 0.8,
                    "reasoning": f"{metric_name} can use KG-native session text",
                }

        provider = StubProvider()
        deepeval_provider = StubDeepEvalProvider()
        deepeval_session_config = {
            "requirements": {
                "aggregation_level": "session",
                "attachment_point": "mas:Session",
                "required_input_parameters": [
                    "conversation_data",
                    "conversation_text",
                    "transcript",
                ],
            }
        }
        answer_relevancy = DeepEvalMetricWrapper(
            "AnswerRelevancy",
            deepeval_session_config,
            provider=deepeval_provider,
        )
        answer_relevancy._availability_status = True
        task_completion = DeepEvalMetricWrapper(
            "TaskCompletion",
            deepeval_session_config,
            provider=deepeval_provider,
        )
        task_completion._availability_status = True
        engine = MetricEngine(max_workers=1, execution_strategy="thread")
        engine.set_data_provider(provider)
        engine.register_metric(GoalSuccessRate())
        engine.register_metric(Groundedness())
        engine.register_metric(IntentRecognitionAccuracy())
        engine.register_metric(ResponseCompleteness())
        engine.register_metric(WorkflowCohesionIndex())
        engine.register_metric(answer_relevancy)
        engine.register_metric(task_completion)
        engine.register_metric(LLMErrorRate())
        engine.register_metric(ToolUtilizationAccuracy())
        engine.register_metric(WorkflowEfficiency())
        engine.register_metric(CyclesCount())

        with (
            patch(
                "mce.providers.native.metrics._base.llm_g_eval_score",
                return_value=(0.75, "kg session context is available", 4.0),
            ),
            patch(
                "mce.providers.native.metrics.quality.tool_utilization_accuracy.llm_g_eval_score",
                return_value=(0.75, "tool usage is aligned", 4.0),
            ),
        ):
            results = engine.compute_session("s1", recursive=True)

        by_id = {result.metric_id: result for result in results}

        assert provider.calls == [True, False]
        assert Counter(deepeval_provider.calls) == Counter(
            {"AnswerRelevancy": 1, "TaskCompletion": 1}
        )
        assert by_id["GoalSuccessRate"].error is None
        assert by_id["GoalSuccessRate"].value == pytest.approx(0.75, abs=0.01)
        assert by_id["Groundedness"].error is None
        assert by_id["Groundedness"].value == pytest.approx(0.75, abs=0.01)
        assert by_id["IntentRecognitionAccuracy"].error is None
        assert by_id["IntentRecognitionAccuracy"].value == pytest.approx(0.75, abs=0.01)
        assert by_id["ResponseCompleteness"].error is None
        assert by_id["ResponseCompleteness"].value == pytest.approx(0.75, abs=0.01)
        assert by_id["WorkflowCohesionIndex"].error is None
        assert by_id["WorkflowCohesionIndex"].value == pytest.approx(0.75, abs=0.01)
        assert by_id["AnswerRelevancy"].error is None
        assert by_id["AnswerRelevancy"].value == pytest.approx(0.8, abs=0.01)
        assert by_id["TaskCompletion"].error is None
        assert by_id["TaskCompletion"].value == pytest.approx(0.8, abs=0.01)
        assert by_id["LLMErrorRate"].error is None
        assert by_id["LLMErrorRate"].value == pytest.approx(0.5, abs=0.01)
        assert by_id["ToolUtilizationAccuracy"].error is None
        assert by_id["WorkflowEfficiency"].error is None
        assert by_id["CyclesCount"].error is None
        assert by_id["CyclesCount"].metadata["total_events"] >= 3
        assert "Missing query/response data" not in by_id["GoalSuccessRate"].reasoning
        assert "No conversation data" not in by_id["Groundedness"].reasoning
        assert "No conversation data" not in by_id["ResponseCompleteness"].reasoning
        assert "No conversation data" not in by_id["WorkflowCohesionIndex"].reasoning
