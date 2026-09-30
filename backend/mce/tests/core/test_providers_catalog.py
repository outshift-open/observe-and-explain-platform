#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.catalog — metric catalog functions."""

from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# get_provider_name
# ---------------------------------------------------------------------------


def test_get_provider_name_deepeval():
    from mce.core.registry.discovery import get_provider_name

    m = MagicMock()
    m.__class__.__module__ = "mce.providers.deepeval.wrapper"
    assert get_provider_name(m) == "DeepEval"


def test_get_provider_name_ragas():
    from mce.core.registry.discovery import get_provider_name

    m = MagicMock()
    m.__class__.__module__ = "mce.providers.ragas.adapter"
    assert get_provider_name(m) == "Ragas"


def test_get_provider_name_opik():
    from mce.core.registry.discovery import get_provider_name

    m = MagicMock()
    m.__class__.__module__ = "mce.providers.opik.adapter"
    assert get_provider_name(m) == "Opik"


def test_get_provider_name_native():
    from mce.core.registry.discovery import get_provider_name

    m = MagicMock()
    m.__class__.__module__ = "mce.providers.native.metrics.quality"
    assert get_provider_name(m) == "Native"


def test_get_provider_name_sdk():
    from mce.core.registry.discovery import get_provider_name

    m = MagicMock()
    m.__class__.__module__ = "mce.providers.sdk.metrics"
    assert get_provider_name(m) == "SDK"


def test_get_provider_name_other():
    from mce.core.registry.discovery import get_provider_name

    m = MagicMock()
    m.__class__.__module__ = "some.unknown.module"
    assert get_provider_name(m) == "Other"


# ---------------------------------------------------------------------------
# serialize_metric_catalog_format
# ---------------------------------------------------------------------------


def _make_metric_with_metadata():
    from unittest.mock import MagicMock
    from enum import Enum

    class FakeLayer(Enum):
        SPAN = "span"

    class FakeScope(Enum):
        SESSION = "session"

    class FakeNature(Enum):
        QUANTITATIVE = "quantitative"

    m = MagicMock()
    m.__class__.__module__ = "mce.providers.native.metrics.quality"
    m.metric_id = "AR"
    m.metadata.name = "AnswerRelevancy"
    m.metadata.description = "Measures answer relevancy"
    m.metadata.layer = FakeLayer.SPAN
    m.metadata.scope = FakeScope.SESSION
    m.metadata.nature = FakeNature.QUANTITATIVE
    m.metadata.ontology_class = "Quality"
    return m


def test_serialize_basic_fields():
    from mce.core.registry.discovery import serialize_metric_catalog_format

    m = _make_metric_with_metadata()
    doc = serialize_metric_catalog_format(m)
    assert "Name" in doc
    assert "Description" in doc
    assert "Layer" in doc
    assert "Scope" in doc
    assert "Provider" in doc
    assert "Nature" in doc
    assert doc["MCE Implemented"] == "Yes"


def test_serialize_uses_metadata_name():
    from mce.core.registry.discovery import serialize_metric_catalog_format

    m = _make_metric_with_metadata()
    doc = serialize_metric_catalog_format(m)
    assert doc["Name"] == "AnswerRelevancy"


def test_serialize_detailed_adds_extra_fields():
    from mce.core.registry.discovery import serialize_metric_catalog_format

    m = _make_metric_with_metadata()
    m.is_available = True
    doc = serialize_metric_catalog_format(m, detailed=True)
    assert "Status" in doc
    assert doc["Status"] == "Available"


def test_serialize_unavailable_metric():
    from mce.core.registry.discovery import serialize_metric_catalog_format

    m = _make_metric_with_metadata()
    m.is_available = False
    doc = serialize_metric_catalog_format(m, detailed=True)
    assert doc["Status"] == "Unavailable"


def test_serialize_is_virtual_false_by_default():
    from mce.core.registry.discovery import serialize_metric_catalog_format

    m = _make_metric_with_metadata()
    del m.is_virtual  # Remove so getattr fallback returns False
    type(m).is_virtual = property(lambda self: False)
    doc = serialize_metric_catalog_format(m)
    assert doc["Is Virtual"] is False


# ---------------------------------------------------------------------------
# get_default_metrics — smoke test (no real LLM/external SDK required)
# ---------------------------------------------------------------------------


def test_get_default_metrics_returns_list():
    from mce.core.registry.discovery import get_default_metrics

    metrics = get_default_metrics()
    assert isinstance(metrics, list)
    assert len(metrics) > 0


def test_get_default_metrics_contains_native_metrics():
    from mce.core.registry.discovery import get_default_metrics

    metrics = get_default_metrics()
    metric_ids = [m.metric_id for m in metrics]
    assert any("tool" in mid.lower() or "error" in mid.lower() for mid in metric_ids)


def test_get_default_metrics_has_workflow_metrics():
    from mce.core.registry.discovery import get_default_metrics
    from mce.providers.native.metrics.workflow.cycles_count import CyclesCount

    metrics = get_default_metrics()
    assert any(isinstance(m, CyclesCount) for m in metrics)
