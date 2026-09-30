#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import math
from unittest.mock import MagicMock
from mce.providers.native.metrics import (
    ToolError,
    ToolErrorRate,
    ResponseCompleteness,
    LLMAverageConfidence,
    LLMMinimumConfidence,
    LLMMaximumConfidence,
)


class TestNativeMetrics:
    def test_tool_error_metric(self):
        metric = ToolError()
        # Case 1: Success
        res = metric.compute("trace_1", {"status_code": "OK", "error": None})
        assert res.value == 0.0
        assert res.metric_id == "ToolError"

        # Case 2: Error Status
        res = metric.compute(
            "trace_2", {"status_code": "ERROR", "error": "Something bad"}
        )
        assert res.value == 1.0
        assert "Something bad" in res.reasoning

        # Case 3: Error Message only
        res = metric.compute("trace_3", {"status_code": "OK", "error": "Fail"})
        assert res.value == 1.0

    def test_tool_error_rate_metric(self):
        metric = ToolErrorRate()

        # Case 1: Empty
        res = metric.compute("sess_1", {"tool_spans": []})
        assert res.value == 0.0
        assert "No tool spans" in res.reasoning

        # Case 2: Mix
        spans = [
            {"status_code": "OK", "error": None},  # Good
            {"status_code": "ERROR", "error": "Bad"},  # Bad
            {"status_code": "OK", "error": "Bad"},  # Bad
            {"status_code": "OK", "error": None},  # Good
        ]
        # Total: 4, Errors: 2 -> Rate: 0.5
        res = metric.compute("sess_2", {"tool_spans": spans})
        assert res.value == 0.5
        assert res.metric_id == "ToolErrorRate"

    def test_response_completeness(self):
        metric = ResponseCompleteness()

        # Mock LLM call
        metric.call_llm = MagicMock(return_value="Reasoning: Excellent.\nScore: 5")

        context = {"conversation_text": "User: Hi\nBot: Hello"}
        res = metric.compute("sess_3", context)

        assert res.value == 1.0
        metric.call_llm.assert_called_once()

        # Test empty context fallback
        res_empty = metric.compute("sess_4", {})
        assert res_empty.value == 0.0
        assert "No conversation data" in res_empty.reasoning

    def test_uncertainty_metrics(self):
        context = {
            "llm_spans": [
                {
                    "output_payload": {
                        "logprobs": {"content": [{"logprob": -0.1}, {"logprob": -0.2}]}
                    }
                }
            ]
        }

        avg_metric = LLMAverageConfidence()
        min_metric = LLMMinimumConfidence()
        max_metric = LLMMaximumConfidence()

        res_avg = avg_metric.compute("sess_1", context)
        res_min = min_metric.compute("sess_1", context)
        res_max = max_metric.compute("sess_1", context)

        assert math.isclose(
            res_avg.value, (math.exp(-0.1) + math.exp(-0.2)) / 2.0, rel_tol=1e-6
        )
        assert math.isclose(res_min.value, math.exp(-0.2), rel_tol=1e-6)
        assert math.isclose(res_max.value, math.exp(-0.1), rel_tol=1e-6)
