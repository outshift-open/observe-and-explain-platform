#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for the entry_points plugin discovery system."""

from importlib.metadata import EntryPoint
from unittest.mock import MagicMock, patch


from mce.core.registry.discovery import _discover_plugin_metrics, _PLUGIN_GROUP
from mce.core.metric import (
    Metric,
    MetricMetadata,
    MetricLayer,
    MetricNature,
    MetricScope,
    MetricResult,
)


# ---------------------------------------------------------------------------
# Minimal concrete Metric implementation for testing
# ---------------------------------------------------------------------------


class _StubMetric(Metric):
    """Minimal Metric subclass to use as a plugin fixture."""

    @property
    def metadata(self) -> MetricMetadata:
        return MetricMetadata(
            name="StubMetric",
            description="A stub plugin metric for testing",
            layer=MetricLayer.AGENT,
            nature=MetricNature.QUANTITATIVE,
            scope=MetricScope.SESSION,
        )

    def compute(self, resource_id: str, context: dict) -> MetricResult:
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="plugin-test",
            value=1.0,
        )


# ---------------------------------------------------------------------------
# _PLUGIN_GROUP constant
# ---------------------------------------------------------------------------


def test_plugin_group_name():
    """Entry-point group must match telemetry-hub convention."""
    assert _PLUGIN_GROUP == "metrics_computation_engine.plugins"


# ---------------------------------------------------------------------------
# _discover_plugin_metrics — no plugins installed
# ---------------------------------------------------------------------------


def test_no_plugins_returns_empty_list():
    """When no plugins are registered, discovery returns an empty list."""
    with patch("mce.core.registry.discovery.entry_points", return_value=[]):
        result = _discover_plugin_metrics()
    assert result == []


# ---------------------------------------------------------------------------
# _discover_plugin_metrics — valid plugin
# ---------------------------------------------------------------------------


def test_valid_plugin_is_loaded():
    """A properly registered Metric subclass is instantiated and returned."""
    ep = MagicMock(spec=EntryPoint)
    ep.name = "StubMetric"
    ep.value = "test_plugin_discovery:_StubMetric"
    ep.load.return_value = _StubMetric

    with patch("mce.core.registry.discovery.entry_points", return_value=[ep]):
        result = _discover_plugin_metrics()

    assert len(result) == 1
    assert isinstance(result[0], _StubMetric)


# ---------------------------------------------------------------------------
# _discover_plugin_metrics — bad plugin (not a Metric subclass)
# ---------------------------------------------------------------------------


def test_non_metric_class_is_skipped(caplog):
    """A class that is not a Metric subclass is silently skipped with a WARNING."""

    class NotAMetric:
        pass

    ep = MagicMock(spec=EntryPoint)
    ep.name = "NotAMetric"
    ep.value = "test_plugin_discovery:NotAMetric"
    ep.load.return_value = NotAMetric

    with patch("mce.core.registry.discovery.entry_points", return_value=[ep]):
        with caplog.at_level("WARNING"):
            result = _discover_plugin_metrics()

    assert result == []
    assert "NotAMetric" in caplog.text


# ---------------------------------------------------------------------------
# _discover_plugin_metrics — broken plugin (load raises)
# ---------------------------------------------------------------------------


def test_broken_plugin_is_skipped(caplog):
    """An entry-point whose load() raises is silently skipped."""
    ep = MagicMock(spec=EntryPoint)
    ep.name = "BrokenMetric"
    ep.value = "broken_package:BrokenMetric"
    ep.load.side_effect = ImportError("missing dependency")

    with patch("mce.core.registry.discovery.entry_points", return_value=[ep]):
        with caplog.at_level("WARNING"):
            result = _discover_plugin_metrics()

    assert result == []
    assert "BrokenMetric" in caplog.text


# ---------------------------------------------------------------------------
# _discover_plugin_metrics — abstract class is skipped
# ---------------------------------------------------------------------------


def test_abstract_metric_is_skipped():
    """An abstract Metric subclass is NOT instantiated."""
    ep = MagicMock(spec=EntryPoint)
    ep.name = "AbstractMetric"
    ep.value = "mce.core.metric:Metric"
    ep.load.return_value = Metric  # Metric itself is abstract

    with patch("mce.core.registry.discovery.entry_points", return_value=[ep]):
        result = _discover_plugin_metrics()

    assert result == []
