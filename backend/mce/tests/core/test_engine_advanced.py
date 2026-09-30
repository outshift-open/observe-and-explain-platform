#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock
from mce.engine.engine import MetricEngine
from mce.core.provider import DataProvider
from mce.core.metadata import MetricRequirements
from mce.engine.strategies import HybridStrategy, ProcessStrategy
from mce.core.metric import Metric


class MockProvider(DataProvider):
    def fetch(self, resource_id, requirements):
        return {"session": {"id": resource_id}}


def test_engine_concurrency_hybrid():
    # Test that hybrid strategy initializes correctly
    engine = MetricEngine(execution_strategy="hybrid")
    # Strategy is stored in _executor (internal)
    assert isinstance(engine._executor, HybridStrategy)


def test_engine_process_fallback():
    # Test process strategy
    engine = MetricEngine(execution_strategy="process")
    assert isinstance(engine._executor, ProcessStrategy)


def test_engine_compute_error_handling():
    engine = MetricEngine()
    engine.set_data_provider(MockProvider())

    # Mock a metric that raises an exception
    bad_metric = MagicMock(spec=Metric)
    bad_metric.metadata = (
        MagicMock()
    )  # spec=Metric doesn't expose annotation-only attrs
    bad_metric.metric_id = "bad_metric"
    bad_metric.ontology_class = "ErrorMetric"
    bad_metric.scope.name = "SESSION"
    bad_metric.dependencies = []
    bad_metric.input_requirements = MetricRequirements()

    # Side effect: raise exception (simulating plugin failure)
    bad_metric.compute.side_effect = Exception("Boom")

    engine.register_metric(bad_metric)

    # Run compute
    # The engine catches exceptions per metric and logs them.
    # Since v2 error reporting, the engine returns MetricResult(error=...) entries
    # instead of silently dropping failed/unrouted metrics.
    results = engine.compute_session("session-1")

    # Assert graceful handling (no crash): at least one error result returned
    assert len(results) >= 1
    assert all(r.error is not None for r in results)
    engine = MetricEngine()

    m1 = MagicMock(spec=Metric)
    m1.metric_id = "m1"
    m1.ontology_class = "TestScore"

    m2 = MagicMock(spec=Metric)
    m2.metric_id = "m1"  # Same ID
    m2.ontology_class = "TestScore"

    engine.register_metric(m1)
    engine.register_metric(m2)

    registry = engine.get_implementations("TestScore")
    assert len(registry) == 1
    assert registry[0] == m2  # Last one wins
