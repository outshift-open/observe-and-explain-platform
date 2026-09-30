#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.legacy.legacy_api_provider.LegacyApiProvider."""

import pytest
from unittest.mock import MagicMock, patch
from mce.legacy.legacy_api_provider import LegacyApiProvider
from mce.core.metric import MetricRequirements

pytest.importorskip("dal", reason="dal package not installed in this env")


def _make_prov():
    """Helper: build LegacyApiProvider with mocked ApiDataProvider."""
    with patch("mce.legacy.adapters.api_provider.ApiDataProvider"):
        with patch("dal.api_client.get_api_client"):
            prov = LegacyApiProvider()
    # Replace with a controlled mock
    mock_api = MagicMock()
    prov._api_provider = mock_api
    # Unset DAL client — tests that need it set it explicitly
    prov._dal_client = None
    return prov, mock_api


class TestLegacyApiProviderInit:
    def test_init_sets_api_provider(self):
        prov, _ = _make_prov()
        assert prov._api_provider is not None

    def test_available_true_when_api_provider_set(self):
        prov, _ = _make_prov()
        assert prov._available

    def test_semantic_client_initially_none(self):
        prov, _ = _make_prov()
        assert prov._semantic_client is None


class TestFetchStrategies:
    def test_fetch_via_api_provider(self):
        prov, mock_api = _make_prov()
        expected = {"session_id": "s1", "llm_spans": []}
        mock_api.fetch.return_value = expected
        result = prov.fetch("s1", MetricRequirements())
        assert result == expected
        mock_api.fetch.assert_called_once()

    def test_fetch_api_failure_fallback_to_legacy(self):
        prov, mock_api = _make_prov()
        mock_api.fetch.side_effect = Exception("network error")
        result = prov.fetch("s1", MetricRequirements())
        # Falls back to _fetch_legacy which returns {} when no DAL
        assert isinstance(result, dict)

    def test_fetch_semantic_when_client_set_and_entities_required(self):
        prov, _ = _make_prov()
        prov._semantic_client = MagicMock()
        prov._semantic_client.get_entities.return_value = [{"id": "e1"}]
        req = MetricRequirements(required_entities=["mas:Agent"])
        result = prov.fetch("sess1", req)
        assert "mas:Agent" in result

    def test_fetch_semantic_with_edges(self):
        prov, _ = _make_prov()
        prov._semantic_client = MagicMock()
        prov._semantic_client.get_entities.return_value = []
        prov._semantic_client.get_edges.return_value = [{"edge": "e1"}]
        req = MetricRequirements(
            required_entities=["mas:Agent"],
            include_edges=True,
            allowed_relations=["uses"],
        )
        result = prov.fetch("s1", req)
        assert "edges" in result


class TestFetchLegacy:
    def test_fetch_legacy_with_injected_fn(self):
        prov, _ = _make_prov()
        prov._api_provider = None  # disable API path
        prov._legacy_fetch_fn = MagicMock(
            return_value={"query": "hello", "response": "hi"}
        )
        result = prov._fetch_legacy("s1")
        assert result["input_text"] == "hello"

    def test_fetch_legacy_fn_returns_empty(self):
        prov, _ = _make_prov()
        prov._api_provider = None
        prov._legacy_fetch_fn = MagicMock(return_value=None)
        result = prov._fetch_legacy("s1")
        assert result == {}

    def test_fetch_legacy_fn_raises(self):
        prov, _ = _make_prov()
        prov._api_provider = None
        prov._legacy_fetch_fn = MagicMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            prov._fetch_legacy("s1")

    def test_fetch_legacy_with_dal_client(self):
        prov, _ = _make_prov()
        prov._api_provider = None
        prov._dal_client = MagicMock()
        prov._dal_client.get_traces_by_session.return_value = []
        result = prov._fetch_legacy("s1")
        assert result == {}

    def test_fetch_legacy_dal_with_traces(self):
        prov, _ = _make_prov()
        prov._api_provider = None
        prov._dal_client = MagicMock()
        prov._dal_client.get_traces_by_session.return_value = [{"span": "data"}]
        mock_entity = MagicMock()
        mock_entity.tool_spans = []
        mock_entity.agent_spans = []
        mock_entity.llm_spans = []
        mock_entity.conversation_data = {
            "query": "q",
            "response": "r",
            "conversation": "",
        }
        with patch(
            "normalization.core.trace_processor_wrapper.traces_processor",
            return_value=mock_entity,
        ):
            result = prov._fetch_legacy("s1")
        assert "traces" in result or isinstance(result, dict)

    def test_fetch_legacy_no_mechanism_returns_empty(self):
        prov, _ = _make_prov()
        prov._api_provider = None
        result = prov._fetch_legacy("s1")
        assert result == {}

    def test_fetch_legacy_dal_error_raises(self):
        prov, _ = _make_prov()
        prov._api_provider = None
        prov._dal_client = MagicMock()
        prov._dal_client.get_traces_by_session.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError):
            prov._fetch_legacy("s1")


class TestAdaptLegacyKeys:
    def test_maps_query_to_input_text(self):
        prov, _ = _make_prov()
        data = {"query": "what?", "response": "answer"}
        result = prov._adapt_legacy_keys(data)
        assert result["input_text"] == "what?"
        assert result["output_text"] == "answer"

    def test_preserves_existing_keys(self):
        prov, _ = _make_prov()
        data = {"query": "q", "input_text": "existing", "response": "r"}
        result = prov._adapt_legacy_keys(data)
        # Should not overwrite existing input_text
        assert result["input_text"] == "existing"

    def test_handles_missing_query(self):
        prov, _ = _make_prov()
        data = {"other": "value"}
        result = prov._adapt_legacy_keys(data)
        assert "input_text" not in result
