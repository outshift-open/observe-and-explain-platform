#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import MagicMock

from mce.engine.engine import MetricEngine
from mce.core.provider import DataProvider
from mce.core.metadata import MetricRequirements, MetricNature, MetricScope, MetricLayer
from mce.core.metric import Metric
from mce.core.types import MetricResult


class MockMetric(Metric):
    @property
    def metric_id(self):
        return "mock_metric"

    @property
    def ontology_class(self):
        return "MockMetric"

    @property
    def domain(self):
        return MetricLayer.RAW

    @property
    def nature(self):
        return MetricNature.DETERMINISTIC

    @property
    def scope(self):
        return MetricScope.TRACE

    @property
    def dependencies(self):
        return []

    @property
    def input_requirements(self):
        return MetricRequirements(scalar_fields=["value"])

    def compute(self, resource_id, context):
        val = context.get("value", 0)
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Test",
            value=val,
            metric_class=self.ontology_class,
        )


class TestMetricEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MetricEngine()
        self.metric = MockMetric()
        self.engine.register_metric(self.metric)

    def test_registration(self):
        self.assertEqual(self.engine.get_metric("mock_metric"), self.metric)

    def test_requirements_aggregation(self):
        reqs = self.engine.get_aggregated_requirements()
        self.assertIn("value", reqs.scalar_fields)

    def test_push_computation(self):
        context = {"value": 10}
        results = self.engine.compute_all("id_1", context)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].value, 10)

    def test_pull_computation(self):
        mock_provider = MagicMock(spec=DataProvider)
        mock_provider.fetch_batch.return_value = [{"value": 20}]
        self.engine.set_data_provider(mock_provider)

        results = self.engine.compute_all("id_2")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].value, 20)
        mock_provider.fetch_batch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
