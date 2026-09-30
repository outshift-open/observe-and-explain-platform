#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mce.providers.sdk.metrics import CostMetric, TokenCountMetric, DurationMetric
from mce.core.types import MetricResult


def test_duration_metric():
    metric = DurationMetric()
    context = {"duration_ms": 123.45}
    result: MetricResult = metric.compute("span-123", context)
    assert result.value == 123.45
    assert result.resource_id == "span-123"


def test_duration_metric_aliases():
    metric = DurationMetric()
    context = {"latency": 500.0}
    result = metric.compute("span-456", context)
    assert result.value == 500.0


def test_token_count_flat():
    metric = TokenCountMetric()
    context = {"total_tokens": 150}
    result = metric.compute("span-1", context)
    assert result.value == 150.0


def test_token_count_sum():
    metric = TokenCountMetric()
    context = {"prompt_tokens": 100, "completion_tokens": 50}
    result = metric.compute("span-2", context)
    assert result.value == 150.0


def test_token_count_nested_usage():
    metric = TokenCountMetric()
    context = {"usage": {"total_tokens": 300, "prompt_tokens": 200}}
    result = metric.compute("span-3", context)
    assert result.value == 300.0


def test_cost_metric_simple():
    metric = CostMetric()
    context = {"cost_usd": 0.05}
    result = metric.compute("span-cost-1", context)
    assert result.value == 0.05
