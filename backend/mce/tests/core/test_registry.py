#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.core.registry.service.MetricRegistry."""

from unittest.mock import MagicMock, patch
import pytest

from mce.core.registry.service import MetricRegistry
from mce.core.metric import Metric


def _make_metric(metric_id: str = "AR", ontology_class: str = "Quality") -> Metric:
    """Create a minimal Metric mock that satisfies isinstance check."""
    m = MagicMock(spec=Metric)
    m.metric_id = metric_id
    m.ontology_class = ontology_class
    return m


@pytest.fixture(autouse=True)
def fresh_registry():
    """Isolate each test with a clean singleton."""
    MetricRegistry._instance = None
    yield
    MetricRegistry._instance = None


# ---------------------------------------------------------------------------
# Instantiation / singleton
# ---------------------------------------------------------------------------


def test_get_instance_creates_singleton():
    inst1 = MetricRegistry.get_instance()
    inst2 = MetricRegistry.get_instance()
    assert inst1 is inst2


def test_new_instance_is_empty():
    reg = MetricRegistry()
    assert reg.get_all() == []


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


def test_register_and_get_by_id():
    reg = MetricRegistry()
    m = _make_metric("AR")
    reg.register(m)
    assert reg.get_metric("AR") is m


def test_register_multiple_metrics():
    reg = MetricRegistry()
    m1 = _make_metric("AR")
    m2 = _make_metric("RC")
    reg.register(m1)
    reg.register(m2)
    assert len(reg.get_all()) == 2


def test_register_overwrite_warns(caplog):
    import logging

    reg = MetricRegistry()
    m1 = _make_metric("AR")
    m2 = _make_metric("AR")
    reg.register(m1)
    with caplog.at_level(logging.WARNING):
        reg.register(m2)
    assert reg.get_metric("AR") is m2  # newest wins


def test_register_type_error_on_non_metric():
    reg = MetricRegistry()
    with pytest.raises(TypeError):
        reg.register("not_a_metric_instance")


def test_register_type_error_on_none():
    reg = MetricRegistry()
    with pytest.raises(TypeError):
        reg.register(None)


# ---------------------------------------------------------------------------
# get_by_class()
# ---------------------------------------------------------------------------


def test_get_by_class_returns_metrics():
    reg = MetricRegistry()
    m1 = _make_metric("AR", "Quality")
    m2 = _make_metric("RC", "Quality")
    m3 = _make_metric("GS", "Success")
    reg.register(m1)
    reg.register(m2)
    reg.register(m3)

    quality = reg.get_by_class("Quality")
    assert m1 in quality
    assert m2 in quality
    assert m3 not in quality


def test_get_by_class_no_duplicate_on_double_register():
    reg = MetricRegistry()
    m = _make_metric("AR", "Quality")
    reg.register(m)
    reg.register(m)  # should not add twice
    assert reg.get_by_class("Quality").count(m) == 1


def test_get_by_class_unknown_returns_empty():
    reg = MetricRegistry()
    assert reg.get_by_class("UNKNOWN") == []


# ---------------------------------------------------------------------------
# get_metric() / get_all()
# ---------------------------------------------------------------------------


def test_get_metric_unknown_returns_none():
    reg = MetricRegistry()
    assert reg.get_metric("UNKNOWN") is None


def test_get_all_returns_list():
    reg = MetricRegistry()
    reg.register(_make_metric("AR"))
    result = reg.get_all()
    assert isinstance(result, list)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# load_provider()
# ---------------------------------------------------------------------------


def test_load_provider_calls_register_function():
    reg = MetricRegistry()
    mock_mod = MagicMock()
    with patch("importlib.import_module", return_value=mock_mod):
        reg.load_provider("fake.provider")
    mock_mod.register.assert_called_once_with(reg)


def test_load_provider_only_loads_once():
    reg = MetricRegistry()
    mock_mod = MagicMock()
    with patch("importlib.import_module", return_value=mock_mod):
        reg.load_provider("fake.provider")
        reg.load_provider("fake.provider")
    mock_mod.register.assert_called_once()


def test_load_provider_no_register_function_does_not_raise():
    reg = MetricRegistry()
    mock_mod = MagicMock(spec=[])  # no register attribute
    with patch("importlib.import_module", return_value=mock_mod):
        reg.load_provider("fake.no_register")  # must not raise


def test_load_provider_import_error_does_not_raise():
    reg = MetricRegistry()
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        reg.load_provider("non.existent.module")  # must not raise
