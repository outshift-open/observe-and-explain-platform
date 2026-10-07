#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Tests for LLM-judge native metrics using LLMService v2.
Uses direct call_llm mock — no real LLM required.
"""

from unittest.mock import MagicMock
import pytest

from mce.engine.llm import LLMService
from mce.providers.native.metrics import (
    ResponseCompleteness,
    ToolUtilizationAccuracy,
    TaskDelegationAccuracy,
    GoalSuccessRate,
    IntentRecognitionAccuracy,
    ComponentConflictRate,
    SemanticConsistency,
    ContextPreservation,
    Groundedness,
    InformationRetention,
)


@pytest.fixture(autouse=True)
def reset_llm_singleton():
    LLMService._instance = None
    yield
    LLMService._instance = None


def _ctx_with_llm_judge_data():
    return {
        "input_query": "What is the capital of France?",
        "final_response": "Paris is the capital of France.",
        "tool_spans": [],
        "llm_spans": [],
    }


def _mock_score(metric_cls, score_str="1.0"):
    """Create metric instance with mocked call_llm returning a float string."""
    m = metric_cls()
    m.call_llm = MagicMock(return_value=score_str)
    return m


# ---------------------------------------------------------------------------
# LLMService configure for tests
# ---------------------------------------------------------------------------


def test_llm_service_configure():
    LLMService.configure(mode="replay", cache_path="/tmp/test_cache.json")
    svc = LLMService._instance
    assert svc.mode == "replay"


# ---------------------------------------------------------------------------
# ResponseCompleteness
# ---------------------------------------------------------------------------


def test_response_completeness_with_mocked_llm():
    m = _mock_score(ResponseCompleteness, "0.9")
    ctx = _ctx_with_llm_judge_data()
    result = m.compute("res1", ctx)
    assert result is not None
    assert 0.0 <= result.value <= 1.0


def test_response_completeness_score_zero():
    m = _mock_score(ResponseCompleteness, "0.0")
    result = m.compute("res1", _ctx_with_llm_judge_data())
    assert result.value == pytest.approx(0.0)


def test_response_completeness_score_clipped():
    """Scores outside [0,1] should be clipped."""
    m = _mock_score(ResponseCompleteness, "2.5")
    result = m.compute("res1", _ctx_with_llm_judge_data())
    assert result.value <= 1.0


# ---------------------------------------------------------------------------
# ToolUtilizationAccuracy
# ---------------------------------------------------------------------------


def test_tool_utilization_accuracy_no_tools():
    m = ToolUtilizationAccuracy()
    ctx = {"tool_spans": [], "input_query": "q", "final_response": "r"}
    result = m.compute("r1", ctx)
    assert result is not None


def test_tool_utilization_accuracy_with_tool():
    m = _mock_score(ToolUtilizationAccuracy, "1.0")
    ctx = {
        "tool_spans": [
            {"toolName": "search", "toolInput": "france", "toolOutput": "Paris"}
        ],
        "input_query": "Capital of France?",
        "final_response": "Paris",
    }
    result = m.compute("r1", ctx)
    assert result is not None
    assert 0.0 <= result.value <= 1.0


# ---------------------------------------------------------------------------
# TaskDelegationAccuracy
# ---------------------------------------------------------------------------


def test_task_delegation_accuracy_mocked():
    m = _mock_score(TaskDelegationAccuracy, "1.0")
    ctx = {"input_query": "delegate this", "final_response": "done", "llm_spans": []}
    result = m.compute("r1", ctx)
    assert result is not None


# ---------------------------------------------------------------------------
# GoalSuccessRate
# ---------------------------------------------------------------------------


def test_goal_success_rate_mocked():
    m = _mock_score(GoalSuccessRate, "1.0")
    result = m.compute("r1", _ctx_with_llm_judge_data())
    assert result is not None
    assert 0.0 <= result.value <= 1.0


# ---------------------------------------------------------------------------
# IntentRecognitionAccuracy
# ---------------------------------------------------------------------------


def test_intent_recognition_accuracy_mocked():
    m = _mock_score(
        IntentRecognitionAccuracy, "Reasoning: Good intent recognition.\nScore: 4"
    )
    result = m.compute("r1", _ctx_with_llm_judge_data())
    assert result is not None
    # Score 4 on 1-5 scale → (4-1)/(5-1) = 0.75
    assert result.value == pytest.approx(0.75, abs=0.01)


# ---------------------------------------------------------------------------
# ComponentConflictRate
# ---------------------------------------------------------------------------


def test_component_conflict_rate_no_conflict():
    m = _mock_score(ComponentConflictRate, "0.0")
    result = m.compute("r1", _ctx_with_llm_judge_data())
    assert result is not None
    assert result.value == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# SemanticConsistency
# ---------------------------------------------------------------------------


def test_consistency_mocked():
    m = _mock_score(SemanticConsistency, "1.0")
    result = m.compute("r1", _ctx_with_llm_judge_data())
    assert result is not None


# ---------------------------------------------------------------------------
# ContextPreservation
# ---------------------------------------------------------------------------


def test_context_preservation_mocked():
    m = _mock_score(ContextPreservation, "0.9")
    result = m.compute("r1", _ctx_with_llm_judge_data())
    assert result is not None


# ---------------------------------------------------------------------------
# Groundedness
# ---------------------------------------------------------------------------


def test_groundedness_mocked():
    m = _mock_score(Groundedness, "1.0")
    ctx = dict(_ctx_with_llm_judge_data())
    ctx["retrieval_context"] = "France is a country in Europe. Paris is its capital."
    result = m.compute("r1", ctx)
    assert result is not None


# ---------------------------------------------------------------------------
# InformationRetention
# ---------------------------------------------------------------------------


def test_information_retention_mocked():
    m = _mock_score(InformationRetention, "Reasoning: Decent retention.\nScore: 3")
    # InformationRetention uses extract_conversation_text which checks input_text/output_text
    ctx = {
        "input_text": "What is the capital of France?",
        "output_text": "Paris is the capital of France.",
    }
    result = m.compute("r1", ctx)
    assert result is not None
    # Score 3 on 1-5 scale → (3-1)/(5-1) = 0.5
    assert result.value == pytest.approx(0.5, abs=0.01)
