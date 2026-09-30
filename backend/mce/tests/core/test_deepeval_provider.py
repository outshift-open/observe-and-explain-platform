#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock
import sys
from mce.providers.deepeval.provider import DeepEvalProvider

# Mock deepeval module with __spec__=None so importlib.util.find_spec won't raise ValueError
mock_deepeval = MagicMock()
mock_deepeval.__spec__ = None
sys.modules["deepeval"] = mock_deepeval
sys.modules["deepeval.metrics"] = mock_deepeval
sys.modules["deepeval.test_case"] = mock_deepeval


def test_deepeval_get_metric():
    provider = DeepEvalProvider()

    # Mock specific class imports
    mock_metric_cls = MagicMock()
    mock_deepeval.AnswerRelevancyMetric = mock_metric_cls

    # Test built-in metric mapping
    m = provider.get_metric("AnswerRelevancyMetric")
    mock_metric_cls.assert_called()
    assert m is not None

    # Test caching (should return same instance)
    m2 = provider.get_metric("AnswerRelevancyMetric")
    assert m is m2

    # Test unknown metric
    assert provider.get_metric("UnknownMetric") is None


def test_deepeval_build_test_case():
    provider = DeepEvalProvider()

    context = {"input_text": "Q", "output_text": "A", "retrieval_context": ["doc1"]}

    # Mock LLMTestCase constructor in deepeval
    mock_case_cls = MagicMock()
    mock_deepeval.LLMTestCase = mock_case_cls

    provider.build_test_case(context)

    # Verify mapping
    call_args = mock_case_cls.call_args[1]
    assert call_args["input"] == "Q"
    assert call_args["actual_output"] == "A"
    assert call_args["retrieval_context"] == ["doc1"]


def test_deepeval_set_model():
    provider = DeepEvalProvider()
    provider.set_model("gpt-4")
    assert provider._model_config == "gpt-4"
    # Should clear cache
    provider._instances = {"m": 1}
    provider.set_model("new")
    assert provider._instances == {}
