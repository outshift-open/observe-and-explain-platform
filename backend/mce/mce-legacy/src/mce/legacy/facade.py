#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.engine.engine import MetricEngine
from mce.core.types import MetricResult
from mce.core.metric import Metric

# ==========================================================
# LEGACY ADAPTER (The "Old" Logic rewritten as a Wrapper)
# ==========================================================


class LegacyMetricManager:
    """
    Facade for Backward Compatibility.

    Old code instantiates this manager and calls evaluate().
    Internally, it spins up the V2 engine, runs plugins, and downcasts results.
    """

    def __init__(self, use_v2_engine: bool = True):
        self.use_v2_engine = use_v2_engine
        self.v2_engine = MetricEngine()
        self._bootstrap_v2_defaults()

    def _bootstrap_v2_defaults(self):
        """Register default providers so generic 'evaluate' works out of the box."""
        from mce.providers.sdk.metrics import DurationMetric, TokenCountMetric

        self.v2_engine.register_metric(DurationMetric())
        self.v2_engine.register_metric(TokenCountMetric())

        from mce.providers.native import ToolErrorRate, ResponseCompleteness

        self.v2_engine.register_metric(ToolErrorRate())
        self.v2_engine.register_metric(ResponseCompleteness())

    def register_custom_metric(self, metric_implementation):
        """Register a V2 Metric or wrap a legacy function."""
        if isinstance(metric_implementation, Metric):
            self.v2_engine.register_metric(metric_implementation)

    def evaluate(
        self, trace_id: str, trace_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Legacy entry point.

        Returns a list of dictionaries (old format), not MetricResult objects.
        """
        v2_results: list[MetricResult] = self.v2_engine.compute_all(
            trace_id, trace_data
        )
        return [res.to_legacy_dict() for res in v2_results]


# Global singleton for easy import (common pattern in legacy libs)
default_manager = LegacyMetricManager()


def evaluate_trace(trace_id: str, data: Any) -> list[dict[str, Any]]:
    """Function-level legacy API."""
    return default_manager.evaluate(trace_id, data)
