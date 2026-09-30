#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
End-to-end metric computation tests using LLMService v2.
Exercises MetricEngine and native providers without real LLM / Neo4j.
"""

from unittest.mock import MagicMock
import pytest

from mce.engine.llm import LLMService
from mce.core.types import MetricResult
from mce.providers.native.metrics import (
    ResponseCompleteness,
    ToolError,
    ToolErrorRate,
)
from mce.providers.sdk.metrics import DurationMetric, TokenCountMetric


@pytest.fixture(autouse=True)
def reset_llm():
    LLMService._instance = None
    yield
    LLMService._instance = None


# ---------------------------------------------------------------------------
# MetricResult.to_legacy_dict
# ---------------------------------------------------------------------------


def test_metric_result_to_legacy_dict_has_expected_keys():
    r = MetricResult(
        metric_id="AR",
        resource_id="r1",
        value=0.8,
        provider="native",
        reasoning="Good answer",
    )
    legacy = r.to_legacy_dict()
    assert "metricName" in legacy
    assert "value" in legacy


def test_metric_result_to_legacy_dict_metric_name():
    r = MetricResult(
        metric_id="AR",
        resource_id="r1",
        value=0.5,
        provider="native",
        metric_class="AR",
    )
    legacy = r.to_legacy_dict()
    assert legacy["metricName"] == "AR"


def test_metric_result_to_legacy_dict_value():
    r = MetricResult(metric_id="AR", resource_id="r1", value=0.75, provider="native")
    legacy = r.to_legacy_dict()
    assert legacy["value"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Native metrics end-to-end (no LLM)
# ---------------------------------------------------------------------------


def test_tool_error_e2e_no_errors():
    metric = ToolError()
    # ToolError reads context["error"] and context["status_code"] directly
    ctx = {"error": None, "status_code": "OK"}
    result = metric.compute("span1", ctx)
    assert result is not None
    assert result.value == 0.0


def test_tool_error_e2e_with_error():
    metric = ToolError()
    # ToolError reads context["error"] directly (not in tool_spans)
    ctx = {"error": "timeout", "status_code": "ERROR"}
    result = metric.compute("span1", ctx)
    assert result is not None
    assert result.value == 1.0


def test_tool_error_rate_empty():
    metric = ToolErrorRate()
    result = metric.compute("r1", {"tool_spans": []})
    assert result.value == 0.0


def test_tool_error_rate_mixed():
    metric = ToolErrorRate()
    ctx = {
        "tool_spans": [
            {"toolName": "t1", "error": None},
            {"toolName": "t2", "error": "fail"},
        ]
    }
    result = metric.compute("r1", ctx)
    assert result.value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# SDK metrics end-to-end
# ---------------------------------------------------------------------------


def test_duration_metric_e2e():
    m = DurationMetric()
    result = m.compute("span1", {"duration_ms": 500.0})
    assert result.value == 500.0
    assert result.metric_id == "duration_ms"


def test_token_count_e2e():
    m = TokenCountMetric()
    result = m.compute("span1", {"prompt_tokens": 100, "completion_tokens": 50})
    assert result.value == 150.0


def test_cost_metric_e2e():
    from mce.providers.sdk.metrics import CostMetric

    m = CostMetric()
    result = m.compute("span1", {"cost_per_token": 0.002, "total_tokens": 500})
    assert result.value == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# LLM-judge metric with mocked LLM
# ---------------------------------------------------------------------------


def test_response_completeness_e2e_with_mock_llm():
    LLMService.configure(mode="replay", cache_path="/tmp/cache_e2e.json")
    metric = ResponseCompleteness()
    metric.call_llm = MagicMock(return_value="0.85")
    result = metric.compute(
        "res1",
        {
            "input_query": "What is the speed of light?",
            "final_response": "The speed of light is approximately 3x10^8 m/s.",
        },
    )
    assert result is not None
    assert 0.0 <= result.value <= 1.0
