#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E402

import pytest
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

from mce.providers.opik.adapter import OpikMetricWrapper, create_wrapper as create_opik
from mce.providers.ragas.adapter import (
    RagasMetricWrapper,
    create_wrapper as create_ragas,
)
from mce.providers.deepeval.adapter import create_wrapper as create_deepeval


class TestOpikWrapper:
    def test_opik_delegation(self):
        mock_opik = MagicMock()
        mock_metric_cls = MagicMock()
        mock_metric_instance = MagicMock()
        mock_metric_instance.score.return_value = 0.75

        with patch.dict("sys.modules", {"opik.evaluation.metrics": mock_opik}):
            setattr(mock_opik, "Hallucination", mock_metric_cls)
            mock_metric_cls.return_value = mock_metric_instance

            wrapper = OpikMetricWrapper("Hallucination", {})
            wrapper.init_with_model("gpt-4")

            res = wrapper.call_external_sync(input_text="in", output_text="out")
            assert res == 0.75

    def test_opik_factory(self):
        wrapper = create_opik("Hallucination")
        assert isinstance(wrapper, OpikMetricWrapper)
        assert wrapper.metric_id == "Hallucination"

        with pytest.raises(ValueError):
            create_opik("UnknownMetric")


class TestRagasWrapper:
    def test_ragas_raises_not_implemented(self):
        wrapper = RagasMetricWrapper("AnswerRelevancy", {})
        with pytest.raises(NotImplementedError):
            wrapper.call_external_sync(input_text="in", output_text="out")

    def test_ragas_factory(self):
        wrapper = create_ragas("TopicAdherenceScore")
        assert isinstance(wrapper, RagasMetricWrapper)

        wrapper_f1 = create_ragas("ragas.TopicAdherenceScore.f1")
        assert wrapper_f1._mode == "f1"
        assert wrapper_f1.metric_id == "TopicAdherenceScore_f1"


class TestDeepEvalAdapterFactory:
    def test_deepeval_factory(self):
        wrapper = create_deepeval("AnswerRelevancyMetric")
        assert wrapper.metric_id == "AnswerRelevancyMetric"
