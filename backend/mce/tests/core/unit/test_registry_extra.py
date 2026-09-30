#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests targeting missed lines in core/registry/__init__.py."""

import sys
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# Lines 39-47: load_registry
# ---------------------------------------------------------------------------
def test_load_registry_with_providers():
    """load_metrics_from_config passes configured providers to registry."""
    from mce.core.registry import load_metrics_from_config

    with patch("mce.core.registry.Registry") as mock_cls:
        reg = MagicMock()
        mock_cls.get_instance.return_value = reg
        load_metrics_from_config(
            {"providers": ["mce.providers.native", "mce.providers.deepeval"]}
        )
    reg.load_provider.assert_any_call("mce.providers.native")
    reg.load_provider.assert_any_call("mce.providers.deepeval")


def test_load_registry_empty_providers():
    """load_metrics_from_config with empty config calls no load_provider.
    Native metrics are already handled by discover_all_metrics(); there is no
    need to register them a second time via load_provider.
    """
    from mce.core.registry import load_metrics_from_config

    with patch("mce.core.registry.Registry") as mock_cls:
        reg = MagicMock()
        mock_cls.get_instance.return_value = reg
        load_metrics_from_config({})
    reg.load_provider.assert_not_called()


# ---------------------------------------------------------------------------
# Lines 79-81: serialize_metric_catalog_format with detailed=True
# ---------------------------------------------------------------------------
def _make_metric(name="TestMetric", module_path="mce.providers.native"):
    from mce.core.metadata import MetricMetadata, MetricLayer, MetricScope, MetricNature

    meta = MetricMetadata(
        name=name,
        display_name=name,
        description="A test metric",
        ontology_class=name,
        layer=MetricLayer.RAW,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.SESSION,
    )
    m = MagicMock()
    m.metric_id = name
    m.metadata = meta
    m.is_virtual = False
    m.is_available = True
    m.dependencies = []
    m.__class__.__module__ = module_path
    return m


def test_serialize_metric_catalog_format_basic():
    """serialize_metric_catalog_format returns expected keys."""
    from mce.core.registry import serialize_metric_catalog_format

    m = _make_metric()
    result = serialize_metric_catalog_format(m)
    assert "Name" in result
    assert "Description" in result
    assert "Provider" in result


def test_serialize_metric_catalog_format_detailed():
    """serialize_metric_catalog_format with detailed=True adds extra fields."""
    from mce.core.registry import serialize_metric_catalog_format

    m = _make_metric()
    result = serialize_metric_catalog_format(m, detailed=True)
    assert "Status" in result
    assert "Version" in result
    assert "Dependencies" in result


def test_get_provider_name_variants():
    """get_provider_name identifies provider from module path."""
    from mce.core.registry import get_provider_name

    for module, expected in [
        ("mce.providers.deepeval.wrapper", "DeepEval"),
        ("mce.providers.ragas.adapter", "Ragas"),
        ("mce.providers.opik.provider", "Opik"),
        ("mce.providers.native.metrics", "Native"),
        ("mce.providers.sdk", "SDK"),
        ("mce.providers.virtual", "Virtual"),
        ("unknown.provider", "Other"),
    ]:
        m = _make_metric(module_path=module)
        assert get_provider_name(m) == expected, f"Expected {expected} for {module}"
