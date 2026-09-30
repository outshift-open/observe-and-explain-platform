#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Extended tests for mce.core.metric.Metric — covering missed lines."""

import pytest
from unittest.mock import MagicMock, patch
from mce.core.metric import Metric, MetricResult, MetricRequirements
from mce.core.metadata import MetricMetadata, MetricLayer, MetricNature, MetricScope


def _make_concrete_metric(name="TestM", raise_on_compute=False):
    meta = MetricMetadata(
        name=name,
        description="test",
        layer=MetricLayer.EXECUTION,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.SESSION,
        ontology_class=name,
    )

    class ConcreteM(Metric):
        metadata = meta

        @property
        def input_requirements(self):
            return MetricRequirements()

        def compute(self, resource_id, context):
            if raise_on_compute:
                raise ValueError("compute error")
            return MetricResult(
                metric_id=name, resource_id=resource_id, provider="test", value=1.0
            )

    return ConcreteM()


class TestMetricProperties:
    def test_is_virtual_returns_false(self):
        m = _make_concrete_metric()
        assert m.is_virtual is False

    def test_input_requirements_returns_empty(self):
        m = _make_concrete_metric()
        reqs = m.input_requirements
        assert isinstance(reqs, MetricRequirements)

    def test_domain_proxy(self):
        m = _make_concrete_metric()
        assert m.domain == MetricLayer.EXECUTION

    def test_nature_proxy(self):
        m = _make_concrete_metric()
        assert m.nature == MetricNature.DETERMINISTIC


class TestComputeBatch:
    def test_compute_batch_all_success(self):
        m = _make_concrete_metric()
        results = m.compute_batch(["e1", "e2"], [{}, {}])
        assert len(results) == 2
        assert all(r.value == 1.0 for r in results)

    def test_compute_batch_handles_exception(self):
        m = _make_concrete_metric(raise_on_compute=True)
        results = m.compute_batch(["e1"], [{}])
        assert len(results) == 1
        assert results[0].error is not None
        assert "compute error" in results[0].error
        assert results[0].value == 0.0

    def test_compute_batch_partial_failure(self):
        """First succeeds, second fails."""
        call_count = [0]
        meta = MetricMetadata(
            name="Partial",
            description="",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.DETERMINISTIC,
            scope=MetricScope.SESSION,
            ontology_class="Partial",
        )

        class PartialM(Metric):
            metadata = meta

            @property
            def input_requirements(self):
                return MetricRequirements()

            def compute(self, resource_id, context):
                call_count[0] += 1
                if call_count[0] > 1:
                    raise RuntimeError("second call fails")
                return MetricResult(
                    metric_id="Partial",
                    resource_id=resource_id,
                    provider="test",
                    value=0.5,
                )

        m = PartialM()
        results = m.compute_batch(["e1", "e2"], [{}, {}])
        assert results[0].value == 0.5
        assert results[1].error is not None


class TestCallLlm:
    def test_call_llm_uses_service(self):
        m = _make_concrete_metric()
        mock_service = MagicMock()
        mock_service.get_completion.return_value = "mocked response"
        with patch("mce.engine.llm.LLMService.get_instance", return_value=mock_service):
            result = m.call_llm("test prompt")
        assert result == "mocked response"

    def test_call_llm_propagates_exception(self):
        m = _make_concrete_metric()
        with patch(
            "mce.engine.llm.LLMService.get_instance", side_effect=RuntimeError("no llm")
        ):
            with pytest.raises(RuntimeError, match="no llm"):
                m.call_llm("prompt")
