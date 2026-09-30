#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.core.catalog.MetricCatalogService."""

import pytest
from unittest.mock import MagicMock, patch
import threading

from mce.core.catalog import MetricCatalogService
from mce.core.metric import Metric


@pytest.fixture(autouse=True)
def fresh_catalog():
    """Reset singleton between tests."""
    MetricCatalogService._instance = None
    yield
    MetricCatalogService._instance = None


def _make_metric(metric_id: str, ontology_class: str = "Quality") -> Metric:
    m = MagicMock(spec=Metric)
    m.metric_id = metric_id
    md = MagicMock()
    md.name = metric_id
    md.ontology_class = ontology_class
    md.attachment_point = None
    m.metadata = md
    return m


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_instance_creates_singleton():
    c1 = MetricCatalogService.get_instance()
    c2 = MetricCatalogService.get_instance()
    assert c1 is c2


def test_fresh_instance_has_empty_contracts():
    cat = MetricCatalogService()
    assert cat.get_all_contracts() == []


# ---------------------------------------------------------------------------
# register_metric — instance
# ---------------------------------------------------------------------------


def test_register_metric_instance():
    cat = MetricCatalogService()
    m = _make_metric("AR")
    cat.register_metric(m)
    assert cat.get_contract("AR") is m


def test_register_metric_stores_in_unified():
    cat = MetricCatalogService()
    m = _make_metric("AR")
    cat.register_metric(m)
    result = cat.get_metric("AR")
    assert result is m


def test_register_metric_multiple_same_id():
    cat = MetricCatalogService()
    m1 = _make_metric("AR")
    m2 = _make_metric("AR")
    cat.register_metric(m1)
    cat.register_metric(m2)
    # Both stored in unified list but contract returns first registered
    result = cat.get_metric("AR")
    assert result is m1


# ---------------------------------------------------------------------------
# register_metric — class (abstract)
# ---------------------------------------------------------------------------


def test_register_metric_class_with_metadata():
    cat = MetricCatalogService()

    class FakeMetricClass:
        metadata = MagicMock()
        metadata.name = "FakeMetric"

    cat.register_metric(FakeMetricClass)
    assert cat.get_contract("FakeMetric") is FakeMetricClass


def test_register_metric_class_without_metadata_is_skipped():
    cat = MetricCatalogService()

    class NoMeta:
        pass

    cat.register_metric(NoMeta)
    # Should not raise, and contracts should be empty
    assert cat.get_all_contracts() == []


# ---------------------------------------------------------------------------
# get_contract / get_metric
# ---------------------------------------------------------------------------


def test_get_contract_returns_none_for_missing():
    cat = MetricCatalogService()
    assert cat.get_contract("missing") is None


def test_get_metric_returns_none_for_missing():
    cat = MetricCatalogService()
    assert cat.get_metric("missing") is None


def test_get_metric_lazy_avg_creates_average_metric():
    cat = MetricCatalogService()
    # Register base metric first
    base = _make_metric("AR")
    cat.register_metric(base)
    cat._contracts["AR"] = base  # ensure contract exists

    result = cat.get_metric("avg_AR")
    assert result is not None
    assert result.metric_id.startswith("avg_")


def test_get_metric_lazy_max_creates_aggregate():
    cat = MetricCatalogService()
    base = _make_metric("score")
    cat.register_metric(base)
    cat._contracts["score"] = base

    result = cat.get_metric("max_score")
    assert result is not None


def test_get_metric_lazy_missing_base_returns_none():
    cat = MetricCatalogService()
    # "avg_missing" — base "missing" not registered
    assert cat.get_metric("avg_missing") is None


# ---------------------------------------------------------------------------
# get_all_contracts
# ---------------------------------------------------------------------------


def test_get_all_contracts_returns_all():
    cat = MetricCatalogService()
    m1 = _make_metric("AR")
    m2 = _make_metric("F1")
    cat.register_metric(m1)
    cat.register_metric(m2)
    contracts = cat.get_all_contracts()
    assert len(contracts) == 2


# ---------------------------------------------------------------------------
# discover_metrics
# ---------------------------------------------------------------------------


def test_discover_metrics_invalid_package_logs_warning():
    cat = MetricCatalogService()

    with patch.object(MetricCatalogService, "register_metric") as mock_reg:
        cat.discover_metrics("nonexistent.package")
    # Should not raise — just warns
    mock_reg.assert_not_called()


# ---------------------------------------------------------------------------
# Thread safety — singleton
# ---------------------------------------------------------------------------


def test_singleton_thread_safe():
    results = []

    def get():
        results.append(MetricCatalogService.get_instance())

    threads = [threading.Thread(target=get) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All should be the same instance
    assert all(r is results[0] for r in results)
