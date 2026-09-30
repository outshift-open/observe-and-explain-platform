#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
from unittest.mock import MagicMock
from mce.engine.engine import MetricEngine
from mce.core.metric import Metric
from mce.core.metadata import MetricScope, MetricNature, MetricRequirements
from mce.core.types import MetricResult


class _MockMetadata:
    """Minimal metadata stub for context_builder compatibility."""

    name: str = "mock_metric"

    def __init__(self):
        self.target_types: set = set()
        self.attachment_point = None
        self.scope = MetricScope.SESSION
        self.dependencies = []


class MockMetric(Metric):
    def __init__(self, metric_id, cls_name, scope=MetricScope.SESSION):
        self._id = metric_id
        self._cls = cls_name
        self._scope = scope
        # Each instance gets its own metadata so target_types isn't shared
        self.metadata = _MockMetadata()
        self.metadata.scope = scope

    @property
    def metric_id(self):
        return self._id

    @property
    def ontology_class(self):
        return self._cls

    @property
    def scope(self):
        return self._scope

    @property
    def nature(self):
        return MetricNature.ABSTRACT

    @property
    def input_requirements(self):
        return MetricRequirements(text_fields=["q"])

    @property
    def dependencies(self):
        return []

    def compute(self, resource_id, context):
        if "fail" in resource_id:
            raise ValueError("Computation Failed")
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Test",
            value=1.0,
            metric_class=self.ontology_class,
            reasoning="ok",
        )


def test_shutdown():
    engine = MetricEngine(execution_strategy="thread")
    engine.shutdown()
    # No assertion needed, just ensure no error


def test_register_duplicate():
    engine = MetricEngine()
    m1 = MockMetric("m1", "ClassA")
    m2 = MockMetric("m1", "ClassA")  # Same ID

    engine.register_metric(m1)
    engine.register_metric(m2)  # Should warn and overwrite

    implementations = engine.get_implementations("ClassA")
    assert len(implementations) == 1
    assert implementations[0] is m2


def test_compute_session_span_selectors():
    engine = MetricEngine(execution_strategy="hybrid")

    # Tool Metric — explicitly targets tool calls only
    m_tool = MockMetric("tool_metric", "ToolDuration", MetricScope.SPAN)
    m_tool.metadata.attachment_point = "mas:ToolCall"
    # LLM Metric — explicitly targets LLM calls only
    m_llm = MockMetric("llm_metric", "LLMCost", MetricScope.SPAN)
    m_llm.metadata.attachment_point = "mas:LLMCall"

    engine.register_metric(m_tool)
    engine.register_metric(m_llm)

    # Mock Provider
    provider = MagicMock()
    provider.fetch.return_value = {
        "session": "s1",
        "tool_spans": [{"span_id": "t1"}, {"span_id": "t2"}],
        "llm_spans": [{"span_id": "l1"}],
    }
    engine.set_data_provider(provider)

    results = engine.compute_session("sess_id", recursive=True)

    # Expect 2 tool results + 1 llm result = 3
    assert len(results) == 3


def test_compute_session_metric_failure():
    engine = MetricEngine()
    m_fail = MockMetric("fail_metric", "FailClass")
    engine.register_metric(m_fail)

    provider = MagicMock()
    provider.fetch.return_value = {}
    engine.set_data_provider(provider)

    results = engine.compute_session("fail_session")  # Trigger failure in compute
    # Engine wraps errors in MetricResult with error field set (doesn't discard them)
    assert len(results) == 1
    assert results[0].error is not None


def test_compute_batch_fallback():
    engine = MetricEngine()
    provider = MagicMock()
    # Ensure provider DOES NOT have fetch_batch
    del provider.fetch_batch
    provider.fetch.return_value = {"q": "text"}

    engine.set_data_provider(provider)

    res = engine.compute(["id1", "id2"])
    assert len(res) == 2
    assert "id1" in res
    assert provider.fetch.call_count == 2  # Called in loop


def test_compute_batch_missing_keys_warning():
    engine = MetricEngine()
    provider = MagicMock()
    provider.fetch.return_value = {"other": "val"}  # Missing "q"
    engine.set_data_provider(provider)

    m = MockMetric("req_metric", "ReqClass")  # Requires "q"
    engine.register_metric(m)

    res = engine.compute(["id1"])
    # Should skip execution due to missing keys
    # Result for id1 should be empty list
    assert res["id1"] == []


def test_compute_batch_fetch_error():
    engine = MetricEngine()
    provider = MagicMock()
    # Simulate fetch_batch existing but failing
    provider.fetch_batch = MagicMock(side_effect=Exception("Data Error"))
    engine.set_data_provider(provider)

    with pytest.raises(RuntimeError, match="Data provider failed to fetch batch"):
        engine.compute(["id1"])
