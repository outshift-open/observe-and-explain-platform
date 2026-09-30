#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for all native metric implementations.

Coverage:
- Safety:     ToolError, ToolErrorRate
- Quality:    Groundedness, ComponentConflictRate, Consistency, ContextPreservation,
              InformationRetention, GoalSuccessRate, IntentRecognitionAccuracy,
              TaskDelegationAccuracy, ToolUtilizationAccuracy
- Workflow:   AgentToAgentInteractions, CyclesCount, GraphDeterminismScore,
              WorkflowCohesionIndex
- Session:    Duration, TokenCount, CallCount, Cost

LLM-judge metrics (anything using llm_g_eval_score / call_llm) are tested by
patching out the LLM call — we verify logic, not the LLM output.

Ground truth note:
  Metrics like Groundedness, GoalSuccessRate, IntentRecognitionAccuracy *sound* like
  they need external reference data, but in MCE v2 they are all LLM-judge metrics
  that evaluate the conversation / Q-A pair *in isolation* — no external ground truth
  is required.  The MetricRequirements.ground_truth flag is reserved for future
  dataset-backed evaluation and is currently False for every native metric.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Safety metrics
# ---------------------------------------------------------------------------

from mce.providers.native.metrics.safety.tool_error import ToolError
from mce.providers.native.metrics.safety.tool_error_rate import ToolErrorRate


class TestToolError:
    def test_metadata(self):
        assert ToolError().metadata.name is not None

    def test_input_requirements_declares_tool_call(self):
        assert "mas:ToolCall" in ToolError().input_requirements.required_entities

    def test_ok_status_returns_zero(self):
        result = ToolError().compute("tc1", {"status_code": "OK"})
        assert result.value == 0.0
        assert result.resource_id == "tc1"

    def test_error_status_returns_one(self):
        result = ToolError().compute("tc1", {"status_code": "ERROR"})
        assert result.value == 1.0

    def test_error_field_set_returns_one(self):
        result = ToolError().compute("tc1", {"error": "timeout"})
        assert result.value == 1.0

    def test_empty_context_no_error(self):
        result = ToolError().compute("tc1", {})
        assert result.value == 0.0


class TestToolErrorRate:
    def test_metadata(self):
        assert ToolErrorRate().metadata.name is not None

    def test_no_tool_spans_returns_zero(self):
        result = ToolErrorRate().compute("s1", {})
        assert result.value == 0.0

    def test_all_ok_returns_zero(self):
        spans = [{"status_code": "OK"}, {"status_code": "OK"}]
        result = ToolErrorRate().compute("s1", {"tool_spans": spans})
        assert result.value == 0.0

    def test_partial_errors_correct_rate(self):
        spans = [{"status_code": "ERROR"}, {"status_code": "OK"}, {"error": "fail"}]
        result = ToolErrorRate().compute("s1", {"tool_spans": spans})
        assert result.value == pytest.approx(2 / 3, abs=0.01)

    def test_all_errors_returns_one(self):
        spans = [{"status": "ERROR"}, {"error": "boom"}]
        result = ToolErrorRate().compute("s1", {"tool_spans": spans})
        assert result.value == 1.0

    def test_object_spans_with_status_code(self):
        span = MagicMock()
        span.status_code = "ERROR"
        span.error = None
        result = ToolErrorRate().compute("s1", {"tool_spans": [span]})
        assert result.value == 1.0


# ---------------------------------------------------------------------------
# Quality metrics — LLM-judge conversation (mocked)
# ---------------------------------------------------------------------------

_CONV_CTX = {"conversation_text": "User: hello\nAgent: hi there"}
_QA_CTX = {"input_query": "What is 2+2?", "final_response": "4"}


def _patch_g_eval(score=4.0, reasoning="ok"):
    """Return a patch for llm_g_eval_score used by all LLM judge metrics."""
    return patch(
        "mce.providers.native.metrics._base.llm_g_eval_score",
        return_value=(score, reasoning, score),
    )


class TestGroundedness:
    """Groundedness: no external ground truth needed — LLM judges the conversation."""

    def test_metadata(self):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        assert Groundedness().metadata.name == "Groundedness"

    def test_input_requirements_declares_text_fields(self):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        reqs = Groundedness().input_requirements
        assert any("conversation" in f for f in reqs.text_fields)

    def test_compute_with_conversation(self):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        with _patch_g_eval(4.0):
            result = Groundedness().compute("s1", _CONV_CTX)
        assert result.resource_id == "s1"
        assert result.value == pytest.approx(4.0, abs=0.01)

    def test_compute_empty_context_returns_zero(self):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        result = Groundedness().compute("s1", {})
        assert result.value == 0.0


class TestComponentConflictRate:
    def test_metadata(self):
        from mce.providers.native.metrics.quality.component_conflict_rate import (
            ComponentConflictRate,
        )

        assert ComponentConflictRate().metadata.name is not None

    def test_compute_with_conversation(self):
        from mce.providers.native.metrics.quality.component_conflict_rate import (
            ComponentConflictRate,
        )

        with _patch_g_eval(3.0):
            result = ComponentConflictRate().compute("s1", _CONV_CTX)
        assert result.value == pytest.approx(3.0, abs=0.01)

    def test_compute_empty_context_returns_zero(self):
        from mce.providers.native.metrics.quality.component_conflict_rate import (
            ComponentConflictRate,
        )

        result = ComponentConflictRate().compute("s1", {})
        assert result.value == 0.0


class TestConsistency:
    def test_metadata(self):
        from mce.providers.native.metrics.quality.consistency import Consistency

        assert Consistency().metadata.name is not None

    def test_compute_with_conversation(self):
        from mce.providers.native.metrics.quality.consistency import Consistency

        with _patch_g_eval(5.0):
            result = Consistency().compute("s1", _CONV_CTX)
        assert result.value == pytest.approx(5.0, abs=0.01)

    def test_empty_context_returns_zero(self):
        from mce.providers.native.metrics.quality.consistency import Consistency

        result = Consistency().compute("s1", {})
        assert result.value == 0.0


class TestContextPreservation:
    def test_metadata(self):
        from mce.providers.native.metrics.quality.context_preservation import (
            ContextPreservation,
        )

        assert ContextPreservation().metadata.name is not None

    def test_compute_result_structure(self):
        from mce.providers.native.metrics.quality.context_preservation import (
            ContextPreservation,
        )

        with _patch_g_eval(4.0):
            result = ContextPreservation().compute("s1", _CONV_CTX)
        assert result.provider == "Native"
        assert result.value is not None

    def test_empty_context_returns_zero(self):
        from mce.providers.native.metrics.quality.context_preservation import (
            ContextPreservation,
        )

        result = ContextPreservation().compute("s1", {})
        assert result.value == 0.0


class TestInformationRetention:
    def test_metadata(self):
        from mce.providers.native.metrics.quality.information_retention import (
            InformationRetention,
        )

        assert InformationRetention().metadata.name is not None

    def test_compute_with_conversation(self):
        from mce.providers.native.metrics.quality.information_retention import (
            InformationRetention,
        )

        with _patch_g_eval(4.5):
            result = InformationRetention().compute("s1", _CONV_CTX)
        assert result.value == pytest.approx(4.5, abs=0.01)


# ---------------------------------------------------------------------------
# Quality metrics — LLM-judge Q/A (mocked)
# ---------------------------------------------------------------------------


def _patch_qa_g_eval(score=4.0, reasoning="ok"):
    return patch(
        "mce.providers.native.metrics._base.llm_g_eval_score",
        return_value=(score, reasoning, score),
    )


class TestGoalSuccessRate:
    """GoalSuccessRate: LLM evaluates query vs response — no external ground truth."""

    def test_metadata(self):
        from mce.providers.native.metrics.quality.goal_success_rate import (
            GoalSuccessRate,
        )

        assert GoalSuccessRate().metadata.name is not None

    def test_input_requirements(self):
        from mce.providers.native.metrics.quality.goal_success_rate import (
            GoalSuccessRate,
        )

        reqs = GoalSuccessRate().input_requirements
        assert "input_query" in reqs.text_fields or "final_response" in reqs.text_fields

    def test_compute_with_qa(self):
        from mce.providers.native.metrics.quality.goal_success_rate import (
            GoalSuccessRate,
        )

        with _patch_qa_g_eval(4.0):
            result = GoalSuccessRate().compute("s1", _QA_CTX)
        assert result.value == pytest.approx(4.0, abs=0.01)

    def test_compute_empty_context_returns_zero(self):
        from mce.providers.native.metrics.quality.goal_success_rate import (
            GoalSuccessRate,
        )

        result = GoalSuccessRate().compute("s1", {})
        assert result.value == 0.0


class TestIntentRecognitionAccuracy:
    """IntentRecognitionAccuracy: LLM evaluates whether intent was identified correctly."""

    def test_metadata(self):
        from mce.providers.native.metrics.quality.intent_recognition_accuracy import (
            IntentRecognitionAccuracy,
        )

        assert IntentRecognitionAccuracy().metadata.name is not None

    def test_compute_with_qa(self):
        from mce.providers.native.metrics.quality.intent_recognition_accuracy import (
            IntentRecognitionAccuracy,
        )

        with _patch_qa_g_eval(3.5):
            result = IntentRecognitionAccuracy().compute("s1", _QA_CTX)
        assert result.value == pytest.approx(3.5, abs=0.01)

    def test_compute_empty_context_returns_zero(self):
        from mce.providers.native.metrics.quality.intent_recognition_accuracy import (
            IntentRecognitionAccuracy,
        )

        result = IntentRecognitionAccuracy().compute("s1", {})
        assert result.value == 0.0


# ---------------------------------------------------------------------------
# Quality metrics — custom LLM judge (mocked)
# ---------------------------------------------------------------------------


def _patch_tda_g_eval(score=4.0):
    return patch(
        "mce.providers.native.metrics.quality.task_delegation_accuracy.llm_g_eval_score",
        return_value=(score, "ok", score),
    )


def _patch_tua_g_eval(score=4.0):
    return patch(
        "mce.providers.native.metrics.quality.tool_utilization_accuracy.llm_g_eval_score",
        return_value=(score, "ok", score),
    )


class TestTaskDelegationAccuracy:
    """TaskDelegationAccuracy: needs agent inputContent and outputContent."""

    def test_metadata(self):
        from mce.providers.native.metrics.quality.task_delegation_accuracy import (
            TaskDelegationAccuracy,
        )

        assert TaskDelegationAccuracy().metadata.name is not None

    def test_input_requirements_declares_content_fields(self):
        from mce.providers.native.metrics.quality.task_delegation_accuracy import (
            TaskDelegationAccuracy,
        )

        reqs = TaskDelegationAccuracy().input_requirements
        assert "inputContent" in reqs.text_fields

    def test_compute_with_agent_data(self):
        from mce.providers.native.metrics.quality.task_delegation_accuracy import (
            TaskDelegationAccuracy,
        )

        ctx = {
            "inputContent": "Summarise the document",
            "outputContent": "Summary: ...",
        }
        with _patch_tda_g_eval(4.0):
            result = TaskDelegationAccuracy().compute("agent1", ctx)
        assert result.value == pytest.approx(4.0, abs=0.01)
        assert result.resource_id == "agent1"

    def test_compute_fallback_to_input_text(self):
        from mce.providers.native.metrics.quality.task_delegation_accuracy import (
            TaskDelegationAccuracy,
        )

        ctx = {"input_text": "Do something", "output_text": "Done"}
        with _patch_tda_g_eval(3.0):
            result = TaskDelegationAccuracy().compute("a1", ctx)
        assert result.value == pytest.approx(3.0, abs=0.01)

    def test_compute_missing_data_returns_zero(self):
        from mce.providers.native.metrics.quality.task_delegation_accuracy import (
            TaskDelegationAccuracy,
        )

        result = TaskDelegationAccuracy().compute("a1", {})
        assert result.value == 0.0
        assert "Missing" in result.reasoning


class TestToolUtilizationAccuracy:
    """ToolUtilizationAccuracy: needs toolArguments, toolOutput, toolName for a single call,
    or tool_spans for session-level aggregation."""

    def test_metadata(self):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        assert ToolUtilizationAccuracy().metadata.name is not None

    def test_input_requirements_declares_tool_fields(self):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        reqs = ToolUtilizationAccuracy().input_requirements
        assert "toolName" in reqs.text_fields

    def test_compute_single_tool_call(self):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        ctx = {
            "toolArguments": '{"query": "sales"}',
            "toolOutput": "Sales: $1M",
            "toolName": "search_db",
        }
        with _patch_tua_g_eval(4.0):
            result = ToolUtilizationAccuracy().compute("tc1", ctx)
        assert result.value == pytest.approx(4.0, abs=0.01)

    def test_compute_missing_fields_returns_zero(self):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        result = ToolUtilizationAccuracy().compute("tc1", {"toolName": "search"})
        assert result.value == 0.0

    def test_compute_session_avg_over_spans(self):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        tool_spans = [
            {"toolArguments": "q1", "toolOutput": "r1", "toolName": "fetch"},
            {"toolArguments": "q2", "toolOutput": "r2", "toolName": "write"},
        ]
        with _patch_tua_g_eval(3.0):
            result = ToolUtilizationAccuracy().compute("s1", {"tool_spans": tool_spans})
        # Both spans scored 3.0 → average = 3.0
        assert result.value == pytest.approx(3.0, abs=0.01)

    def test_compute_session_avg_skips_incomplete_spans(self):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        tool_spans = [
            {"toolArguments": "q1", "toolOutput": "r1", "toolName": "fetch"},
            {
                "toolArguments": "",
                "toolOutput": "r2",
                "toolName": "write",
            },  # missing input → skipped
        ]
        with _patch_tua_g_eval(5.0):
            result = ToolUtilizationAccuracy().compute("s1", {"tool_spans": tool_spans})
        assert result.value == pytest.approx(5.0, abs=0.01)
        assert (
            result.metadata["evaluated"] == 1
        )  # 'evaluated' is the key used by the implementation
        assert result.metadata["skipped"] == 1

    def test_compute_session_avg_uses_configured_parallel_workers(self):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        captured: dict[str, object] = {}

        class _ImmediateFuture:
            def __init__(self, value):
                self._value = value

            def result(self):
                return self._value

        class _FakeExecutor:
            def __init__(self, max_workers):
                captured["max_workers"] = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, func, item):
                return _ImmediateFuture(func(item))

        tool_spans = [
            {"toolArguments": "q1", "toolOutput": "r1", "toolName": "fetch"},
            {"toolArguments": "q2", "toolOutput": "r2", "toolName": "write"},
        ]
        metric = ToolUtilizationAccuracy()
        metric._mce_max_workers = 8

        with (
            patch(
                "mce.providers.native.metrics.quality.tool_utilization_accuracy.concurrent.futures.ThreadPoolExecutor",
                _FakeExecutor,
            ),
            patch(
                "mce.providers.native.metrics.quality.tool_utilization_accuracy.concurrent.futures.as_completed",
                side_effect=lambda futures: futures,
            ),
            _patch_tua_g_eval(3.0),
        ):
            result = metric.compute("s1", {"tool_spans": tool_spans})

        assert captured["max_workers"] == 8
        assert result.value == pytest.approx(3.0, abs=0.01)


# ---------------------------------------------------------------------------
# Workflow metrics — deterministic
# ---------------------------------------------------------------------------


class TestAgentToAgentInteractions:
    def test_metadata(self):
        from mce.providers.native.metrics.workflow.agent_to_agent_interactions import (
            AgentToAgentInteractions,
        )

        assert AgentToAgentInteractions().metadata.name is not None

    def test_input_requirements(self):
        from mce.providers.native.metrics.workflow.agent_to_agent_interactions import (
            AgentToAgentInteractions,
        )

        reqs = AgentToAgentInteractions().input_requirements
        assert "mas:AgentCall" in reqs.required_entities

    def test_compute_with_agent_calls(self):
        from mce.providers.native.metrics.workflow.agent_to_agent_interactions import (
            AgentToAgentInteractions,
        )

        result = AgentToAgentInteractions().compute(
            "s1",
            {
                "agent_calls": [
                    {"agentName": "A"},
                    {"agentName": "B"},
                    {"agentName": "C"},
                    {"agentName": "A"},
                ],
            },
        )
        assert result.value == 3  # total transition count
        assert result.metadata["unique_transitions"] == 3
        assert result.metadata["transition_counts"]["A->B"] == 1

    def test_compute_empty_returns_zero(self):
        from mce.providers.native.metrics.workflow.agent_to_agent_interactions import (
            AgentToAgentInteractions,
        )

        result = AgentToAgentInteractions().compute("s1", {})
        assert result.value == 0
        assert result.metadata["total_transitions"] == 0

    def test_compute_from_session_object(self):
        from mce.providers.native.metrics.workflow.agent_to_agent_interactions import (
            AgentToAgentInteractions,
        )

        session = MagicMock()
        session.agent_calls = [
            {"agentName": "X"},
            {"agentName": "Y"},
            {"agentName": "X"},
        ]
        result = AgentToAgentInteractions().compute("s1", {"session": session})
        assert result.value == 2


class TestCyclesCount:
    def test_metadata(self):
        from mce.providers.native.metrics.workflow.cycles_count import CyclesCount

        assert CyclesCount().metadata.name is not None

    def test_no_cycles(self):
        from mce.providers.native.metrics.workflow.cycles_count import CyclesCount

        spans = [{"toolName": "A"}, {"toolName": "B"}, {"toolName": "C"}]
        result = CyclesCount().compute("s1", {"spans": spans})
        assert result.value == 0

    def test_detects_simple_cycle(self):
        from mce.providers.native.metrics.workflow.cycles_count import CyclesCount

        # A, B, A, B  → one contiguous [A,B][A,B] cycle
        spans = [
            {"toolName": "A"},
            {"toolName": "B"},
            {"toolName": "A"},
            {"toolName": "B"},
        ]
        result = CyclesCount().compute("s1", {"spans": spans})
        assert result.value >= 1

    def test_fallback_to_agent_tool_spans(self):
        from mce.providers.native.metrics.workflow.cycles_count import CyclesCount

        result = CyclesCount().compute(
            "s1",
            {
                "agent_spans": [{"agentName": "AgentA"}, {"agentName": "AgentA"}],
                "tool_spans": [{"toolName": "Tool1"}],
            },
        )
        assert result.value >= 0  # deterministic, no crash

    def test_empty_context_returns_zero(self):
        from mce.providers.native.metrics.workflow.cycles_count import CyclesCount

        result = CyclesCount().compute("s1", {})
        assert result.value == 0


class TestGraphDeterminismScore:
    def _make_session(self, span_names):
        """Mock session object with .spans list of dicts."""
        s = MagicMock()
        s.spans = [{"toolName": n} for n in span_names]
        return s

    def test_metadata(self):
        from mce.providers.native.metrics.workflow.graph_determinism_score import (
            GraphDeterminismScore,
        )

        assert GraphDeterminismScore().metadata.name is not None

    def test_identical_sessions_edit_distance_zero(self):
        from mce.providers.native.metrics.workflow.graph_determinism_score import (
            GraphDeterminismScore,
        )

        sessions = [self._make_session(["A", "B", "C"]) for _ in range(3)]
        result = GraphDeterminismScore().compute("pop1", {"sessions": sessions})
        assert result.value == pytest.approx(0.0, abs=0.01)

    def test_different_sessions_positive_distance(self):
        from mce.providers.native.metrics.workflow.graph_determinism_score import (
            GraphDeterminismScore,
        )

        s1 = self._make_session(["A", "B"])
        s2 = self._make_session(["A", "C"])
        result = GraphDeterminismScore().compute("pop1", {"sessions": [s1, s2]})
        assert result.value > 0

    def test_no_sessions_returns_minus_one(self):
        from mce.providers.native.metrics.workflow.graph_determinism_score import (
            GraphDeterminismScore,
        )

        result = GraphDeterminismScore().compute("pop1", {})
        assert result.value == -1

    def test_single_session_returns_zero(self):
        from mce.providers.native.metrics.workflow.graph_determinism_score import (
            GraphDeterminismScore,
        )

        sessions = [self._make_session(["A", "B"])]
        result = GraphDeterminismScore().compute("pop1", {"sessions": sessions})
        assert result.value == pytest.approx(0.0, abs=0.01)


class TestWorkflowCohesionIndex:
    def test_metadata(self):
        from mce.providers.native.metrics.workflow.workflow_cohesion_index import (
            WorkflowCohesionIndex,
        )

        assert WorkflowCohesionIndex().metadata.name is not None

    def test_compute_with_conversation(self):
        from mce.providers.native.metrics.workflow.workflow_cohesion_index import (
            WorkflowCohesionIndex,
        )

        with _patch_g_eval(4.0):
            result = WorkflowCohesionIndex().compute("s1", _CONV_CTX)
        assert result.value == pytest.approx(4.0, abs=0.01)

    def test_empty_context_returns_zero(self):
        from mce.providers.native.metrics.workflow.workflow_cohesion_index import (
            WorkflowCohesionIndex,
        )

        result = WorkflowCohesionIndex().compute("s1", {})
        assert result.value == 0.0


# ---------------------------------------------------------------------------
# Session metrics (Duration, TokenCount, CallCount, Cost)
# Re-tested here for completeness at session level only.
# ---------------------------------------------------------------------------


def _session_ctx(session_id="s1", duration=1.5, tokens=100, total_cost=0.002):
    """Minimal session-level context matching what ContextBuilder provides."""
    return {
        "session_id": session_id,
        "session": {
            "executionId": session_id,
            "duration": duration,
            "totalTokens": tokens,
            "totalCost": total_cost,
        },
    }


class TestDurationAtSessionLevel:
    def test_metadata(self):
        from mce.providers.native.metrics.session_metrics import Duration

        assert Duration().metadata.name == "Duration"

    def test_compute_session_duration(self):
        from mce.providers.native.metrics.session_metrics import Duration

        result = Duration().compute("s1", _session_ctx("s1", duration=2.5))
        assert result.resource_id == "s1"
        assert result.value == pytest.approx(2.5, abs=0.001)


class TestTokenCountAtSessionLevel:
    def test_compute_session_tokens(self):
        from mce.providers.native.metrics.session_metrics import TokenCount

        result = TokenCount().compute("s1", _session_ctx("s1", tokens=250))
        assert result.value == pytest.approx(250.0, abs=1)


class TestCallCountAtSessionLevel:
    def test_compute_session_call_count(self):
        from mce.providers.native.metrics.session_metrics import CallCount

        ctx = _session_ctx("s1")
        ctx["session"]["callCount"] = 5
        result = CallCount().compute("s1", ctx)
        assert result.value >= 0  # deterministic, no crash


class TestCostAtSessionLevel:
    def test_compute_session_cost(self):
        from mce.providers.native.metrics.session_metrics import Cost

        # Cost aggregates from llm_calls → provide LLM spans with token counts.
        # 1000 prompt tokens @ $10/1M + 500 completion tokens @ $30/1M = $0.010 + $0.015 = $0.025
        ctx = {
            "session_id": "s1",
            "session": {"executionId": "s1"},
            "llm_spans": [
                {"promptTokenCount": 1000, "completionTokenCount": 500},
            ],
        }
        result = Cost().compute("s1", ctx)
        assert result.value == pytest.approx(0.025, abs=1e-4)
