#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock
from mce.providers.native.metrics import (
    ResponseCompleteness,
    ToolUtilizationAccuracy,
    TaskDelegationAccuracy,
    GoalSuccessRate,
    IntentRecognitionAccuracy,
    ComponentConflictRate,
    Consistency,
    ContextPreservation,
    Groundedness,
    InformationRetention,
)


def _mock_llm(metric, return_val="Reasoning: Excellent execution.\nScore: 5"):
    metric.call_llm = MagicMock(return_value=return_val)


def test_response_completeness():
    metric = ResponseCompleteness()
    _mock_llm(metric)
    res = metric.compute("id", {"conversation_text": "text"})
    assert res.value == 1.0


def test_tool_utilization_accuracy():
    metric = ToolUtilizationAccuracy()
    _mock_llm(metric)
    res = metric.compute("id", {"input_text": "a", "output_text": "b", "toolName": "t"})
    assert res.value == 1.0


def test_task_delegation_accuracy():
    metric = TaskDelegationAccuracy()
    _mock_llm(metric)
    res = metric.compute("id", {"input_text": "a", "output_text": "b"})
    assert res.value == 1.0


def test_goal_success_rate():
    metric = GoalSuccessRate()
    _mock_llm(metric)
    # Missing
    assert metric.compute("id", {}).value == 0.0
    # Valid
    res = metric.compute("id", {"input_query": "q", "final_response": "r"})
    assert res.value == 1.0


def test_intent_recognition_accuracy():
    metric = IntentRecognitionAccuracy()
    _mock_llm(metric)
    # Missing
    assert metric.compute("id", {}).value == 0.0
    # Valid
    res = metric.compute("id", {"input_query": "q", "final_response": "r"})
    assert res.value == 1.0


def test_component_conflict_rate():
    metric = ComponentConflictRate()
    _mock_llm(metric)
    # Missing
    assert metric.compute("id", {}).value == 0.0
    # Valid
    res = metric.compute("id", {"conversation_text": "conv"})
    assert res.value == 1.0


def test_consistency():
    metric = Consistency()
    _mock_llm(metric)
    # Missing
    assert metric.compute("id", {}).value == 0.0
    # Valid
    res = metric.compute("id", {"conversation_text": "conv"})
    assert res.value == 1.0


def test_context_preservation():
    metric = ContextPreservation()
    _mock_llm(metric)
    # Missing
    assert metric.compute("id", {}).value == 0.0
    # Valid
    res = metric.compute("id", {"conversation_text": "conv"})
    assert res.value == 1.0


def test_groundedness():
    metric = Groundedness()
    _mock_llm(metric)
    # Missing
    assert metric.compute("id", {}).value == 0.0
    # Valid
    res = metric.compute("id", {"conversation_text": "conv"})
    assert res.value == 1.0


def test_information_retention():
    metric = InformationRetention()
    _mock_llm(metric)
    # Missing
    assert metric.compute("id", {}).value == 0.0
    # Valid
    res = metric.compute("id", {"conversation_text": "conv"})
    assert res.value == 1.0
