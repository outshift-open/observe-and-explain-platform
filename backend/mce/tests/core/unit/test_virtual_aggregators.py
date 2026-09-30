#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.virtual.aggregators."""

import numpy as np
import pytest
from mce.providers.virtual.aggregators import (
    AggregateMetric,
    AverageMetric,
)
from mce.core.types import MetricResult


def _make_result(metric_id, resource_id, value):
    return MetricResult(
        metric_id=metric_id,
        resource_id=resource_id,
        provider="Native",
        value=value,
    )


class TestVirtualMetric:
    def test_is_virtual_true(self):
        m = AverageMetric("TestMetric")
        assert m.is_virtual is True


class TestAggregateMetric:
    def test_metric_id(self):
        m = AggregateMetric("AnswerRelevancy", "avg", np.mean)
        assert m.metric_id == "avg_AnswerRelevancy"

    def test_input_requirements_empty(self):
        m = AggregateMetric("AR", "max", np.max)
        assert m.input_requirements is not None

    def test_compute_aggregates_values(self):
        m = AggregateMetric("AR", "avg", np.mean)
        r1 = _make_result("AR", "e1", 0.6)
        r2 = _make_result("AR", "e2", 0.8)
        ctx = {"computed_metrics": [r1, r2], "other": "value"}
        result = m.compute("session1", ctx)
        assert result.value == pytest.approx(0.7, abs=0.01)
        assert result.metadata["count"] == 2
        assert result.provider == "virtual"

    def test_compute_returns_zero_when_no_values(self):
        m = AggregateMetric("NONEXISTENT", "avg", np.mean)
        result = m.compute("session1", {})
        assert result.value == 0.0
        assert result.metadata["count"] == 0
        assert result.provider == "virtual"

    def test_compute_filters_non_numeric_values(self):
        m = AggregateMetric("AR", "avg", np.mean)
        r_numeric = _make_result("AR", "e1", 0.5)
        r_string = _make_result("AR", "e2", "not-a-number")
        ctx = {"computed_metrics": [r_numeric, r_string]}
        result = m.compute("s1", ctx)
        assert result.value == pytest.approx(0.5, abs=0.01)
        assert result.metadata["count"] == 1

    def test_compute_max_operation(self):
        m = AggregateMetric("Score", "max", np.max)
        r1 = _make_result("Score", "e1", 0.3)
        r2 = _make_result("Score", "e2", 0.9)
        result = m.compute("s1", {"computed_metrics": [r1, r2]})
        assert result.value == pytest.approx(0.9, abs=0.001)

    def test_compute_includes_min_max_metadata(self):
        m = AggregateMetric("M", "avg", np.mean)
        r1 = _make_result("M", "e1", 0.2)
        r2 = _make_result("M", "e2", 0.8)
        result = m.compute("s1", {"computed_metrics": [r1, r2]})
        assert result.metadata["min"] == pytest.approx(0.2, abs=0.01)
        assert result.metadata["max"] == pytest.approx(0.8, abs=0.01)


class TestAverageMetric:
    def test_creates_with_avg_operation(self):
        m = AverageMetric("AnswerRelevancy")
        assert m.operation_name == "avg"
        assert m.metric_id == "avg_AnswerRelevancy"

    def test_compute_average(self):
        m = AverageMetric("AR")
        r1 = _make_result("AR", "e1", 0.4)
        r2 = _make_result("AR", "e2", 0.6)
        result = m.compute("s1", {"computed_metrics": [r1, r2]})
        assert result.value == pytest.approx(0.5, abs=0.01)

    def test_custom_ontology_class(self):
        m = AverageMetric("M", ontology_class="LLMCall")
        assert m.metadata.ontology_class == "LLMCall"
