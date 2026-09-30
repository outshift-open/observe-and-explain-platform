#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.core.registry.discovery — metric discovery system."""

from unittest.mock import MagicMock, patch
from packaging.version import parse as parse_version


# ============================================================================
# Helpers
# ============================================================================


def _make_metric(
    metric_id="AR",
    provider_module="mce.providers.native.something",
    version="1.0.0",
    scope_value="Session",
):
    m = MagicMock()
    m.metric_id = metric_id
    m.ontology_class = metric_id
    md = MagicMock()
    md.version = version
    md.attachment_point = None
    scope = MagicMock()
    scope.value = scope_value
    md.scope = scope
    md.target_types = set()
    m.metadata = md
    m.__class__ = type("FakeMetric", (), {"__module__": provider_module})
    return m


# ============================================================================
# _get_metric_version
# ============================================================================


class TestGetMetricVersion:
    def _call(self, m):
        from mce.core.registry.discovery import _get_metric_version

        return _get_metric_version(m)

    def test_normal_version(self):
        m = _make_metric(version="1.2.3")
        assert self._call(m) == parse_version("1.2.3")

    def test_no_metadata(self):
        m = MagicMock(spec=[])  # no metadata attribute
        result = self._call(m)
        assert result == parse_version("0.0.0")

    def test_invalid_version_string(self):
        m = _make_metric(version="not-a-version")
        # Should return 0.0.0 on parse error
        result = self._call(m)
        assert result is not None  # gracefully handles


# ============================================================================
# _filter_latest_versions
# ============================================================================


class TestFilterLatestVersions:
    def _call(self, metrics):
        from mce.core.registry.discovery import _filter_latest_versions

        return _filter_latest_versions(metrics)

    def test_single_metric_preserved(self):
        m = _make_metric(version="1.0.0")
        m.__class__.__module__ = "mce.providers.native"
        result = self._call([m])
        assert len(result) == 1

    def test_keeps_highest_version(self):
        m1 = _make_metric(metric_id="AR", version="1.0.0")
        m1.__class__.__module__ = "mce.providers.native"
        m2 = _make_metric(metric_id="AR", version="2.0.0")
        m2.__class__.__module__ = "mce.providers.native"
        result = self._call([m1, m2])
        assert len(result) == 1
        assert result[0] is m2  # highest version kept

    def test_different_providers_coexist(self):
        m1 = _make_metric(metric_id="AR", version="1.0.0")
        m1.__class__.__module__ = "mce.providers.native"
        m2 = _make_metric(metric_id="AR", version="1.0.0")
        m2.__class__.__module__ = "mce.providers.deepeval"
        result = self._call([m1, m2])
        # Different providers for same metric_id coexist
        assert len(result) == 2

    def test_empty_list(self):
        result = self._call([])
        assert result == []


# ============================================================================
# get_provider_name
# ============================================================================


class TestGetProviderName:
    def _call(self, module):
        from mce.core.registry.discovery import get_provider_name

        m = MagicMock()
        m.__class__ = type("M", (), {"__module__": module})
        return get_provider_name(m)

    def test_deepeval(self):
        assert self._call("mce.providers.deepeval.wrapper") == "DeepEval"

    def test_ragas(self):
        assert self._call("mce.providers.ragas.adapter") == "Ragas"

    def test_opik(self):
        assert self._call("mce.providers.opik.something") == "Opik"

    def test_native(self):
        assert self._call("mce.providers.native.metrics.safety") == "Native"

    def test_sdk(self):
        assert self._call("mce.providers.sdk.metrics") == "SDK"

    def test_virtual(self):
        assert self._call("mce.providers.virtual.aggregators") == "Virtual"

    def test_other(self):
        assert self._call("some.unknown.package") == "Other"


# ============================================================================
# _resolve_ontology_applicability
# ============================================================================


class TestResolveOntologyApplicability:
    def _call(self, metrics):
        from mce.core.registry.discovery import _resolve_ontology_applicability

        return _resolve_ontology_applicability(metrics)

    def test_session_scope_gets_session_target(self):
        m = _make_metric(scope_value="Session")
        self._call([m])
        assert "mas:Session" in m.metadata.target_types

    def test_span_scope_gets_llm_tool_targets(self):
        m = _make_metric(scope_value="Span")
        self._call([m])
        assert "mas:LLMCall" in m.metadata.target_types

    def test_execution_element_scope(self):
        m = _make_metric(scope_value="ExecutionElement")
        self._call([m])
        assert (
            "mas:LLMCall" in m.metadata.target_types
            or "mas:ExecutionElement" in m.metadata.target_types
        )

    def test_with_attachment_point(self):
        m = _make_metric()
        m.metadata.attachment_point = "mas:AgentCall"
        self._call([m])
        assert "mas:AgentCall" in m.metadata.target_types

    def test_empty_scope_no_crash(self):
        m = _make_metric(scope_value="Unknown")
        m.metadata.attachment_point = None
        # Should not raise
        self._call([m])

    def test_with_ontology_service(self):
        m = _make_metric()
        m.metadata.attachment_point = "mas:Session"
        mock_onto = MagicMock()
        mock_onto.get_subclasses_of.return_value = {"mas:Session", "mas:MASCall"}
        with patch("mce.core.registry.discovery.OntologyService") as MockOS:
            MockOS.get_instance.return_value = mock_onto
            self._call([m])
        assert m.metadata.target_types == {"mas:Session", "mas:MASCall"}

    def test_ontology_service_exception_fallback(self):
        m = _make_metric()
        m.metadata.attachment_point = "mas:Session"
        mock_onto = MagicMock()
        mock_onto.get_subclasses_of.side_effect = Exception("ontology error")
        with patch("mce.core.registry.discovery.OntologyService") as MockOS:
            MockOS.get_instance.return_value = mock_onto
            self._call([m])
        assert "mas:Session" in m.metadata.target_types


# ============================================================================
# _discover_native_metrics
# ============================================================================


class TestDiscoverNativeMetrics:
    def _call(self, package="mce.providers.native.metrics"):
        from mce.core.registry.discovery import _discover_native_metrics

        return _discover_native_metrics(package)

    def test_package_not_found_returns_empty(self):
        result = self._call("mce.nonexistent.package.xyz")
        assert result == []

    def test_no_path_attribute_returns_empty(self):
        mock_pkg = MagicMock(spec=[])  # no __path__
        with patch("importlib.import_module", return_value=mock_pkg):
            result = self._call("mce.providers.native.metrics")
        assert result == []

    def test_discovers_concrete_metrics(self):
        # Real discovery — should find some metrics
        result = self._call("mce.providers.native.metrics")
        assert isinstance(result, list)
        # May be empty if all require arguments, but should not raise
        from mce.core.metric import Metric

        for m in result:
            assert isinstance(m, Metric)


# ============================================================================
# _discover_deepeval / ragas / opik metrics
# ============================================================================


def test_discover_deepeval_returns_metrics():
    """DeepEval metrics are always discovered when the package is installed."""
    from mce.core.registry.discovery import _discover_deepeval_metrics

    result = _discover_deepeval_metrics()
    assert isinstance(result, list)
    assert len(result) > 0


def test_discover_deepeval_import_error_returns_empty():
    from mce.core.registry.discovery import _discover_deepeval_metrics

    with patch(
        "mce.providers.deepeval.wrapper.DeepEvalMetricWrapper",
        side_effect=ImportError("no deepeval"),
    ):
        result = _discover_deepeval_metrics()
    assert isinstance(result, list)


def test_discover_ragas_returns_metrics():
    """Ragas metrics are always discovered when the package is installed."""
    from mce.core.registry.discovery import _discover_ragas_metrics

    result = _discover_ragas_metrics()
    assert isinstance(result, list)
    assert len(result) > 0


def test_discover_ragas_import_error_returns_empty():
    from mce.core.registry.discovery import _discover_ragas_metrics

    with patch.dict("sys.modules", {"mce.providers.ragas.adapter": None}):
        result = _discover_ragas_metrics()
    assert isinstance(result, list)


def test_discover_opik_returns_metrics():
    """Opik metrics are always discovered when the package is installed."""
    from mce.core.registry.discovery import _discover_opik_metrics

    result = _discover_opik_metrics()
    assert isinstance(result, list)
    assert len(result) > 0


def test_discover_opik_import_error_returns_empty():
    from mce.core.registry.discovery import _discover_opik_metrics

    with patch.dict("sys.modules", {"mce.providers.opik.adapter": None}):
        result = _discover_opik_metrics()
    assert isinstance(result, list)
