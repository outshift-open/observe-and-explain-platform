#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.deepeval.metrics_factory."""

import sys
from unittest.mock import MagicMock


def _ensure_deepeval_mocked():
    """Ensure deepeval is available as mock."""
    if "deepeval" not in sys.modules:
        sys.modules["deepeval"] = MagicMock()
    if "deepeval.metrics" not in sys.modules:
        sys.modules["deepeval.metrics"] = MagicMock()
    return sys.modules["deepeval.metrics"]


_ensure_deepeval_mocked()


class TestGetMetricFactory:
    def test_returns_dict(self):
        from mce.providers.deepeval.metrics_factory import get_metric_factory

        result = get_metric_factory()
        assert isinstance(result, dict)

    def test_contains_expected_metrics(self):
        from mce.providers.deepeval.metrics_factory import get_metric_factory

        factory = get_metric_factory()
        expected = ["AnswerRelevancy", "Bias", "Toxicity", "Coherence"]
        for name in expected:
            assert name in factory, f"{name} not in factory"

    def test_factory_functions_are_callable(self):
        from mce.providers.deepeval.metrics_factory import get_metric_factory

        factory = get_metric_factory()
        for name, fn in factory.items():
            assert callable(fn), f"{name} factory is not callable"

    def test_answer_relevancy_factory_calls_deepeval(self):
        from mce.providers.deepeval.metrics_factory import get_metric_factory

        factory = get_metric_factory()
        mock_model = MagicMock()
        mock_metric = MagicMock()
        deepeval_metrics = sys.modules["deepeval.metrics"]
        deepeval_metrics.AnswerRelevancyMetric = MagicMock(return_value=mock_metric)
        result = factory["AnswerRelevancy"](mock_model)
        assert result is mock_metric

    def test_bias_factory(self):
        from mce.providers.deepeval.metrics_factory import get_metric_factory

        factory = get_metric_factory()
        mock_model = MagicMock()
        mock_metric = MagicMock()
        sys.modules["deepeval.metrics"].BiasMetric = MagicMock(return_value=mock_metric)
        result = factory["Bias"](mock_model)
        assert result is mock_metric

    def test_toxicity_factory(self):
        from mce.providers.deepeval.metrics_factory import get_metric_factory

        factory = get_metric_factory()
        sys.modules["deepeval.metrics"].ToxicityMetric = MagicMock(
            return_value=MagicMock()
        )
        result = factory["Toxicity"](MagicMock())
        assert result is not None

    def test_coherence_factory_uses_geval(self):
        from mce.providers.deepeval.metrics_factory import get_metric_factory

        factory = get_metric_factory()
        mock_geval = MagicMock()
        sys.modules["deepeval.metrics"].GEval = MagicMock(return_value=mock_geval)
        result = factory["Coherence"](MagicMock())
        assert result is mock_geval
