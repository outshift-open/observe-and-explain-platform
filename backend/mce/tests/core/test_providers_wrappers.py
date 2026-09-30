#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E402

import sys
from unittest.mock import MagicMock, patch

# Mock deepeval before any mce imports that trigger deepeval loading (Python 3.14 __spec__ issue)
for _m in [
    "deepeval",
    "deepeval.metrics",
    "deepeval.test_case",
    "deepeval.models",
    "deepeval.telemetry",
]:
    if _m not in sys.modules:
        _mock = MagicMock()
        _mock.__spec__ = None
        sys.modules[_m] = _mock

from mce.providers.base_wrapper import ExternalMetricWrapper
from mce.providers.deepeval.wrapper import DeepEvalMetricWrapper
from mce.core.types import MetricResult
from mce.core.metadata import MetricNature, MetricScope, MetricLayer

# Removed LLMJudgeResult import


class TestBaseWrapper:
    def test_external_wrapper_instantiation(self):
        class MockResult:
            def __init__(self, score, reasoning):
                self.score = score
                # Support both naming conventions seen in base_wrapper
                self.reason = reasoning
                self.reasoning = reasoning

        class MockWrapper(ExternalMetricWrapper):
            def __init__(self):
                super().__init__("mock_ext", {}, "MockProvider", MetricScope.SPAN)

            @property
            def metric_id(self):
                return "mock_ext"

            @property
            def ontology_class(self):
                return "MockClass"

            @property
            def domain(self):
                return MetricLayer.GOVERNANCE

            @property
            def nature(self):
                return MetricNature.STOCHASTIC

            def call_external_sync(self, **kwargs):
                return MockResult(score=0.9, reasoning="Good stuff")

        wrapper = MockWrapper()
        res = wrapper.compute("trace_1", {"input": "foo", "output": "bar"})

        assert isinstance(res, MetricResult)
        assert res.value == 0.9
        assert res.reasoning == "Good stuff"
        assert res.provider == "MockProvider"


class TestDeepEvalWrapper:
    def test_wrapper_delegation(self):
        wrapper = DeepEvalMetricWrapper(metric_name="AnswerRelevancyMetric", config={})

        with patch(
            "mce.providers.deepeval.wrapper.DeepEvalProvider"
        ) as mock_provider_cls:
            mock_provider = mock_provider_cls.return_value
            mock_provider.evaluate.return_value = {"score": 0.8, "reasoning": "Decent"}
            wrapper._provider = mock_provider

            context = {"input_text": "Q", "output_text": "A", "context": ["C"]}
            res = wrapper.call_external_sync(**context)

            assert res["score"] == 0.8
            assert res["reasoning"] == "Decent"
            mock_provider.evaluate.assert_called_once()


class TestUnavailableWrapper:
    def test_unavailable_behavior(self):
        """Test that wrapper returns error result when dependency check fails."""

        class BrokenWrapper(ExternalMetricWrapper):
            def __init__(self):
                super().__init__(
                    "broken_metric", {}, "BrokenProvider", MetricScope.SPAN
                )

            def _check_availability(self):
                self._availability_status = False
                self._availability_error = "Module 'broken_lib' not found"

            def call_external_sync(self, **kwargs):
                raise RuntimeError("Should not be called")

        wrapper = BrokenWrapper()

        # Verify status property
        assert wrapper.is_available is False
        assert wrapper._availability_error == "Module 'broken_lib' not found"

        # Verify compute result behavior
        res = wrapper.compute("trace_id_123", {})

        assert isinstance(res, MetricResult)
        # Value might be 0.0 default, but error field must be present
        assert res.error == "Provider Unavailable: Module 'broken_lib' not found"
        assert "broken_metric" in res.metric_id
        assert res.provider == "BrokenProvider"
