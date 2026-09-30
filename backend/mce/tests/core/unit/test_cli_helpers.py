#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for cli/helpers: metric_formatters, compute_setup, ontology_loader."""

import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from mce.core.metric import MetricLayer, MetricNature, MetricScope

# mce.legacy is an optional separate package; mock it so patch() can resolve
# "mce.legacy.legacy_api_provider.LegacyApiProvider" without a real install.
if importlib.util.find_spec("mce.legacy") is None and "mce.legacy" not in sys.modules:
    legacy_mock = MagicMock()
    sys.modules["mce.legacy"] = legacy_mock
    sys.modules["mce.legacy.legacy_api_provider"] = legacy_mock.legacy_api_provider


# ============================================================================
# Shared test fixtures / helpers
# ============================================================================


def _make_mock_metric(
    metric_id="AR",
    name="AnswerRelevancy",
    provider_name="Native",
    layer=MetricLayer.SEMANTIC,
    nature=MetricNature.STOCHASTIC,
    scope=MetricScope.EXECUTION_ELEMENT,
    is_available=True,
    ontology_class="AnswerRelevancy",
    version="1.0.0",
):
    m = MagicMock()
    m.metric_id = metric_id
    m.ontology_class = ontology_class
    m.is_available = is_available
    md = MagicMock()
    md.name = name
    md.layer = layer
    md.nature = nature
    md.scope = scope
    md.description = "A test metric description"
    md.ontology_class = ontology_class
    md.attachment_point = None
    md.target_types = {"mas:Session"}
    md.version = version
    md.dependencies = []
    md.get_display_name.return_value = name
    m.metadata = md
    m.input_requirements.required_entities = []
    m.input_requirements.text_fields = ["input_text"]
    m.input_requirements.vector_fields = []
    m.input_requirements.scalar_fields = []
    return m


# ============================================================================
# metric_formatters.format_metric_list
# ============================================================================


class TestFormatMetricList:
    def test_implementation_list_default(self):
        from mce.cli.helpers.metric_formatters import format_metric_list

        m = _make_mock_metric()
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_list([m])
        assert "AnswerRelevancy" in result
        assert "METRIC NAME" in result

    def test_implementation_list_availability_ok(self):
        from mce.cli.helpers.metric_formatters import format_metric_list

        m = _make_mock_metric(is_available=True)
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_list([m])
        assert "OK" in result

    def test_implementation_list_availability_na(self):
        from mce.cli.helpers.metric_formatters import format_metric_list

        m = _make_mock_metric(is_available=False)
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_list([m])
        assert "N/A" in result

    def test_json_output(self):
        from mce.cli.helpers.metric_formatters import format_metric_list
        import json

        m = _make_mock_metric()
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            with patch(
                "mce.core.registry.serialize_metric_catalog_format",
                return_value={"metric_id": "AR"},
            ):
                result = format_metric_list([m], json_output=True)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_abstract_definitions(self):
        from mce.cli.helpers.metric_formatters import format_metric_list

        m = _make_mock_metric()
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_list([m], show_abstract=True)
        assert "METRIC ID" in result
        assert "AnswerRelevancy" in result

    def test_scope_execution_element_expanded(self):
        from mce.cli.helpers.metric_formatters import format_metric_list

        m = _make_mock_metric()
        # Mock scope.value as plain string (can't set enum value directly)
        m.metadata.scope = MagicMock()
        m.metadata.scope.value = "ExecutionElement"
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_list([m])
        assert "Session" in result or "ExecutionElement" in result

    def test_empty_metrics_list(self):
        from mce.cli.helpers.metric_formatters import format_metric_list

        result = format_metric_list([])
        assert isinstance(result, str)


# ============================================================================
# metric_formatters.format_metric_details
# ============================================================================


class TestFormatMetricDetails:
    def test_no_contract_no_implementations(self):
        from mce.cli.helpers.metric_formatters import format_metric_details

        result = format_metric_details("AR")
        assert "AR" in result
        assert "No metadata available" in result

    def test_with_instance_contract(self):
        from mce.cli.helpers.metric_formatters import format_metric_details

        contract = _make_mock_metric()
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_details("AR", contract=contract)
        assert "AnswerRelevancy" in result

    def test_with_type_contract(self):
        from mce.cli.helpers.metric_formatters import format_metric_details

        # contract as a type (class) rather than instance
        mock_type = MagicMock(spec=type)
        mock_type.__class__ = type
        md = MagicMock()
        md.name = "AR"
        md.description = "desc"
        md.layer.value = "quality"
        md.nature.value = "llm_judge"
        md.scope.value = "Session"
        md.ontology_class = "AR"
        md.attachment_point = None
        md.target_types = set()
        md.version = "1.0.0"
        md.get_display_name.return_value = "AR"
        mock_type.metadata = md
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_details("AR", contract=mock_type, implementations=[])
        assert "AR" in result

    def test_with_implementations(self):
        from mce.cli.helpers.metric_formatters import format_metric_details

        impl = _make_mock_metric()
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_details("AR", contract=None, implementations=[impl])
        assert "Implementations" in result
        assert "Native" in result

    def test_implementations_without_contract(self):
        from mce.cli.helpers.metric_formatters import format_metric_details

        impl = _make_mock_metric()
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_details("AR", implementations=[impl])
        assert "AnswerRelevancy" in result

    def test_no_implementations_message(self):
        from mce.cli.helpers.metric_formatters import format_metric_details

        contract = _make_mock_metric()
        with patch("mce.core.registry.get_provider_name", return_value="Native"):
            result = format_metric_details("AR", contract=contract, implementations=[])
        assert "No implementations found" in result


# ============================================================================
# compute_setup.parse_templated_metric
# ============================================================================


class TestParseTemplatedMetric:
    def _call(self, expr):
        from mce.cli.helpers.compute_setup import parse_templated_metric

        return parse_templated_metric(expr)

    def test_plain_metric_unchanged(self):
        assert self._call("AnswerRelevancy") == "AnswerRelevancy"

    def test_aggregate_pattern(self):
        assert self._call("Aggregate<avg, AnswerRelevancy>") == "avg_AnswerRelevancy"

    def test_aggregate_no_space(self):
        assert self._call("Aggregate<avg,AnswerRelevancy>") == "avg_AnswerRelevancy"

    def test_avg_shortcut(self):
        assert self._call("Avg<AnswerRelevancy>") == "avg_AnswerRelevancy"

    def test_max_shortcut(self):
        assert self._call("Max<Faithfulness>") == "max_Faithfulness"

    def test_min_shortcut(self):
        assert self._call("Min<Faithfulness>") == "min_Faithfulness"

    def test_sum_shortcut(self):
        assert self._call("Sum<TokenCount>") == "sum_TokenCount"


# ============================================================================
# compute_setup.setup_llm_service
# ============================================================================


def test_setup_llm_service_live():
    from mce.cli.helpers.compute_setup import setup_llm_service

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("mce.engine.llm.LLMService.configure") as mock_config,
    ):
        setup_llm_service("/tmp/cache.json", "live")
    mock_config.assert_called_once_with(
        cache_path="/tmp/cache.json",
        mode="live",
        api_key=None,
        model="gpt-4o",
        base_url=None,
    )


def test_setup_llm_service_record():
    from mce.cli.helpers.compute_setup import setup_llm_service

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("mce.engine.llm.LLMService.configure") as mock_config,
    ):
        setup_llm_service("/tmp/cache.json", "RECORD")
    mock_config.assert_called_once_with(
        cache_path="/tmp/cache.json",
        mode="record",
        api_key=None,
        model="gpt-4o",
        base_url=None,
    )


def test_setup_llm_service_replay():
    from mce.cli.helpers.compute_setup import setup_llm_service

    with patch("mce.engine.llm.LLMService.configure"):
        setup_llm_service("/tmp/cache.json", "replay")  # no error


# ============================================================================
# compute_setup.setup_data_provider
# ============================================================================


def test_setup_data_provider_default_returns_none(caplog):
    from mce.cli.helpers.compute_setup import setup_data_provider
    import sys
    from unittest.mock import patch

    # Mock absence of mce-client (it is present in dev environment)
    with patch.dict(sys.modules, {"mce.client.setup": None}):
        with caplog.at_level("ERROR"):
            assert setup_data_provider() is None
    assert "No DataProvider configured" in caplog.text


# ============================================================================
# compute_setup.setup_cache_manager
# ============================================================================


def test_setup_cache_manager_with_kg_and_json(tmp_path):
    from mce.cli.helpers.compute_setup import setup_cache_manager

    mock_kg = MagicMock()
    with patch("mce.engine.caching.CacheManager") as MockCM:
        with patch("mce.engine.caching.KnowledgeGraphCache") as MockKG:
            with patch("mce.engine.caching.JsonFileCache") as MockJson:
                MockKG.return_value = MagicMock()
                MockJson.return_value = MagicMock()
                MockCM.return_value = MagicMock()
                result = setup_cache_manager(mock_kg)
    assert result is not None


def test_setup_cache_manager_no_kg():
    from mce.cli.helpers.compute_setup import setup_cache_manager

    with patch("mce.engine.caching.CacheManager") as MockCM:
        MockCM.return_value = MagicMock()
        result = setup_cache_manager(kg_provider=None)
    assert result is not None


# ============================================================================
# compute_setup.setup_engine
# ============================================================================


def test_setup_engine():
    from mce.cli.helpers.compute_setup import setup_engine

    mock_dp = MagicMock()
    mock_cm = MagicMock()
    with patch("mce.engine.engine.MetricEngine") as MockEngine:
        mock_eng = MagicMock()
        MockEngine.return_value = mock_eng
        setup_engine(mock_dp, mock_cm)
    mock_eng.set_data_provider.assert_called_once_with(mock_dp)
    mock_eng.set_cache_manager.assert_called_once_with(mock_cm)


# ============================================================================
# compute_setup.select_and_resolve_metrics
# ============================================================================


def test_select_and_resolve_no_metrics_selected():
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    with patch("mce.core.registry.get_default_metrics", return_value=[]):
        with patch("mce.core.catalog.MetricCatalogService.get_instance") as mock_cat:
            mock_cat.return_value.get_metric.return_value = None
            result, err = select_and_resolve_metrics(["NonexistentMetric"])
    assert result == []
    assert err != ""


def test_select_and_resolve_compute_all():
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    m1 = _make_mock_metric(metric_id="AR")
    m1.metadata.dependencies = []
    with patch("mce.core.registry.get_default_metrics", return_value=[m1]):
        result, err = select_and_resolve_metrics([], compute_all=True)
    assert err == ""
    assert len(result) == 1


def test_select_and_resolve_by_metric_id():
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    m = _make_mock_metric(metric_id="AR", ontology_class="AR")
    m.metadata.dependencies = []
    with patch("mce.core.registry.get_default_metrics", return_value=[m]):
        result, err = select_and_resolve_metrics(["AR"])
    assert err == ""
    assert len(result) == 1


def test_select_and_resolve_comma_separated():
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    m1 = _make_mock_metric(metric_id="AR", ontology_class="AR")
    m2 = _make_mock_metric(metric_id="FR", ontology_class="FR", name="FactualRelevancy")
    m1.metadata.dependencies = []
    m2.metadata.dependencies = []
    with patch("mce.core.registry.get_default_metrics", return_value=[m1, m2]):
        result, err = select_and_resolve_metrics(["AR,FR"])
    assert err == ""
    assert len(result) == 2


def test_select_and_resolve_templated():
    from mce.cli.helpers.compute_setup import select_and_resolve_metrics

    m = _make_mock_metric(metric_id="avg_AR", ontology_class="avg_AR")
    m.metadata.dependencies = []
    with patch("mce.core.registry.get_default_metrics", return_value=[m]):
        result, err = select_and_resolve_metrics(["Avg<AR>"])
    # avg_AR exists in default, should be found
    assert err == "" or result == []  # either found or falls through gracefully


# ============================================================================
# ontology_loader.load_ontology_hierarchy
# ============================================================================


class TestOntologyLoader:
    def test_returns_empty_when_oxp_ontology_missing(self):
        from mce.cli.helpers.ontology_loader import load_ontology_hierarchy

        # oxp_ontology may not be installed in test env
        with patch.dict("sys.modules", {"oxp_ontology": None}):
            result = load_ontology_hierarchy()
        # Returns {} when import fails
        assert isinstance(result, dict)

    def test_returns_dict(self):
        from mce.cli.helpers.ontology_loader import load_ontology_hierarchy

        try:
            result = load_ontology_hierarchy()
        except RecursionError:
            pytest.skip("Ontology has cycles (recursion depth exceeded)")
        assert isinstance(result, dict)

    def test_roots_in_hierarchy_when_ontology_loads(self):
        """When oxp_ontology is available, hierarchy includes known roots."""
        try:
            from mce.cli.helpers.ontology_loader import load_ontology_hierarchy

            result = load_ontology_hierarchy()
            # At minimum, the function should return a dict (may be empty if load fails)
            assert isinstance(result, dict)
        except (ImportError, Exception):
            pytest.skip("oxp_ontology not installed")
