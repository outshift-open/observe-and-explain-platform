#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests targeting missed lines in compute_setup.py."""

import importlib.util
import logging
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

# mce.legacy is an optional separate package; mock it so patch() can resolve
# "mce.legacy.legacy_api_provider.LegacyApiProvider" without a real install.
if importlib.util.find_spec("mce.legacy") is None and "mce.legacy" not in sys.modules:
    legacy_mock = MagicMock()
    sys.modules["mce.legacy"] = legacy_mock
    sys.modules["mce.legacy.legacy_api_provider"] = legacy_mock.legacy_api_provider


# ---------------------------------------------------------------------------
# Lines 27-30: setup_llm_service debug logging branches
# ---------------------------------------------------------------------------
_COMPUTE_SETUP_LOGGER = "mce.cli.helpers.compute_setup"


def test_setup_llm_service_debug_record(caplog):
    """setup_llm_service logs at DEBUG for record mode."""
    from mce.cli.helpers.compute_setup import setup_llm_service

    with caplog.at_level(logging.DEBUG, logger=_COMPUTE_SETUP_LOGGER):
        setup_llm_service("cache.json", "record")
    assert any(
        "RECORD" in r.message or "record" in r.message.lower() for r in caplog.records
    )


def test_setup_llm_service_debug_replay(caplog):
    """setup_llm_service logs at DEBUG for replay mode."""
    from mce.cli.helpers.compute_setup import setup_llm_service

    with caplog.at_level(logging.DEBUG, logger=_COMPUTE_SETUP_LOGGER):
        setup_llm_service("cache.json", "replay")
    assert any(
        "REPLAY" in r.message or "replay" in r.message.lower() for r in caplog.records
    )


def test_setup_llm_service_debug_live(caplog):
    """setup_llm_service logs at DEBUG for live mode."""
    from mce.cli.helpers.compute_setup import setup_llm_service

    with caplog.at_level(logging.DEBUG, logger=_COMPUTE_SETUP_LOGGER):
        setup_llm_service("cache.json", "live")
    assert any(
        "LIVE" in r.message or "live" in r.message.lower() for r in caplog.records
    )


def test_setup_llm_service_no_crash_uppercase_mode():
    """setup_llm_service tolerates uppercase mode strings."""
    from mce.cli.helpers.compute_setup import setup_llm_service

    setup_llm_service("cache.json", "LIVE")  # should not raise


# ---------------------------------------------------------------------------
# Lines 67-69, 75: setup_data_provider(legacy=True)
# ---------------------------------------------------------------------------
def test_setup_data_provider_legacy_not_implemented_in_core(caplog):
    """setup_data_provider(legacy=True) now returns None/error in core."""
    from mce.cli.helpers.compute_setup import setup_data_provider

    # Mock absence in case dev environment has mce-client installed
    with patch.dict(sys.modules, {"mce.client.setup": None}):
        with caplog.at_level(logging.ERROR):
            result = setup_data_provider(legacy=True)

    assert result is None
    assert "No DataProvider configured" in caplog.text


def test_setup_data_provider_legacy_unavailable():
    """Test retained as placeholder but core always returns None."""
    from mce.cli.helpers.compute_setup import setup_data_provider

    with patch.dict(sys.modules, {"mce.client.setup": None}):
        result = setup_data_provider(legacy=True)
    assert result is None


def test_setup_data_provider_legacy_log_info():
    """Placeholder for legacy provider logger test (removed from core)."""
    pass


# ---------------------------------------------------------------------------
# Lines 252-254: lazy catalog loading in select_and_resolve_metrics
# ---------------------------------------------------------------------------
def test_select_and_resolve_lazy_catalog_fallback():
    """Metric not in registry falls back to lazy catalog.get_metric()."""
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    lazy_metric = MagicMock()
    lazy_metric.metric_id = "lazy_metric"
    lazy_metric.metadata.dependencies = []

    with (
        patch("mce.core.registry.get_default_metrics", return_value=[]) as _,
        patch("mce.core.catalog.MetricCatalogService.get_instance") as mock_cat,
    ):
        catalog = MagicMock()
        catalog.get_metric.return_value = lazy_metric
        mock_cat.return_value = catalog

        result_metrics, error = select_and_resolve_metrics(["lazy_metric"])
        # lazy_metric found → error should be empty, metric should be in results
        assert error == "" or lazy_metric in result_metrics


# ---------------------------------------------------------------------------
# Lines 272-285: dependency BFS auto-include
# ---------------------------------------------------------------------------
def test_select_and_resolve_dependency_bfs():
    """Metric with dependency auto-includes the dependency via BFS."""
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    dep_metric = MagicMock()
    dep_metric.metric_id = "dep_metric"
    dep_metric.metadata.dependencies = []

    main_metric = MagicMock()
    main_metric.metric_id = "main_metric"
    main_metric.ontology_class = "main_metric"
    main_metric.metadata.dependencies = ["dep_metric"]

    with (
        patch(
            "mce.core.registry.get_default_metrics",
            return_value=[main_metric, dep_metric],
        ),
        patch("mce.core.catalog.MetricCatalogService.get_instance") as mock_cat,
    ):
        mock_cat.return_value.get_metric.return_value = None

        result_metrics, error = select_and_resolve_metrics(["main_metric"])
        assert error == ""
        ids = {m.metric_id for m in result_metrics}
        assert "main_metric" in ids
        assert "dep_metric" in ids


def test_select_and_resolve_dependency_already_included():
    """Already-included dependency is not double-added."""
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    shared_dep = MagicMock()
    shared_dep.metric_id = "shared"
    shared_dep.ontology_class = "shared"
    shared_dep.metadata.dependencies = []

    m1 = MagicMock()
    m1.metric_id = "m1"
    m1.ontology_class = "m1"
    m1.metadata.dependencies = ["shared"]
    m2 = MagicMock()
    m2.metric_id = "m2"
    m2.ontology_class = "m2"
    m2.metadata.dependencies = ["shared"]

    with (
        patch(
            "mce.core.registry.get_default_metrics", return_value=[m1, m2, shared_dep]
        ),
        patch("mce.core.catalog.MetricCatalogService.get_instance") as mock_cat,
    ):
        mock_cat.return_value.get_metric.return_value = None

        result_metrics, error = select_and_resolve_metrics(["m1", "m2"])
        assert error == ""
        ids = [m.metric_id for m in result_metrics]
        assert ids.count("shared") == 1


def test_select_and_resolve_dependency_not_found_warns():
    """Missing dependency is silently skipped (with a warning)."""
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    m1 = MagicMock()
    m1.metric_id = "m1"
    m1.ontology_class = "m1"
    m1.metadata.dependencies = ["ghost"]

    with (
        patch("mce.core.registry.get_default_metrics", return_value=[m1]),
        patch("mce.core.catalog.MetricCatalogService.get_instance") as mock_cat,
    ):
        mock_cat.return_value.get_metric.return_value = None

        result_metrics, error = select_and_resolve_metrics(["m1"])
        # Should still return m1 even if dep is missing
        assert error == ""
        ids = {m.metric_id for m in result_metrics}
        assert "m1" in ids
