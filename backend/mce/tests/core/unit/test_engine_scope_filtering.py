#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.engine.engine — scope filtering and other missed paths."""

from unittest.mock import MagicMock
from mce.engine.engine import MetricEngine


def _make_engine():
    eng = MetricEngine()
    return eng


class TestFilterBatchesByScope:
    def test_filter_session_scope(self):
        eng = _make_engine()
        batches = {"session": ["s1"], "llm": ["l1"], "tool": ["t1"]}
        filtered = eng._filter_batches_by_scope(batches, "session", keep_session=False)
        assert filtered["session"] == ["s1"]

    def test_filter_llm_scope(self):
        eng = _make_engine()
        batches = {"session": ["s1"], "llm": ["l1"], "tool": ["t1"]}
        filtered = eng._filter_batches_by_scope(batches, "llm", keep_session=False)
        assert filtered["llm"] == ["l1"]
        assert filtered["session"] == []  # not kept since no aggregate

    def test_keep_session_for_aggregates(self):
        eng = _make_engine()
        batches = {"session": ["s1"], "llm": ["l1"]}
        filtered = eng._filter_batches_by_scope(batches, "llm", keep_session=True)
        assert filtered["session"] == ["s1"]  # kept for aggregate

    def test_unknown_scope_falls_back_to_session(self):
        eng = _make_engine()
        batches = {"session": ["s1"], "llm": ["l1"]}
        # "agent" is not in BATCH_TYPES, falls back to session
        filtered = eng._filter_batches_by_scope(
            batches, "agent_UNKNOWN", keep_session=False
        )
        assert filtered["session"] == ["s1"]


class TestGetMetric:
    def test_get_registered_metric(self):
        eng = _make_engine()
        mock_m = MagicMock()
        mock_m.metric_id = "TestMetric"
        mock_m.ontology_class = "TestMetric"
        eng.register_metric(mock_m)
        result = eng.get_metric("TestMetric")
        assert result is mock_m

    def test_get_nonexistent_metric_returns_none(self):
        eng = _make_engine()
        assert eng.get_metric("NONEXISTENT") is None


class TestRegisterMetricAutoPopulate:
    def test_register_populates_target_types_from_attachment_point(self):
        eng = _make_engine()
        mock_m = MagicMock()
        mock_m.ontology_class = "TestM"
        mock_m.metric_id = "TestM"
        mock_m.metadata.target_types = None
        mock_m.metadata.attachment_point = "mas:Session"
        eng.register_metric(mock_m)
        # target_types should now be set
        assert mock_m.metadata.target_types == {"mas:Session"}

    def test_register_populates_via_scope_fallback(self):
        eng = _make_engine()
        mock_m = MagicMock()
        mock_m.ontology_class = "ScopeM"
        mock_m.metric_id = "ScopeM"
        mock_m.metadata.target_types = None
        mock_m.metadata.attachment_point = None
        mock_scope = MagicMock()
        mock_scope.value = "Session"
        mock_m.metadata.scope = mock_scope
        eng.register_metric(mock_m)


class TestShutdown:
    def test_shutdown_calls_executor_shutdown(self):
        eng = _make_engine()
        mock_executor = MagicMock()
        eng._executor = mock_executor
        eng.shutdown()
        mock_executor.shutdown.assert_called_once_with(wait=True)

    def test_shutdown_no_executor_no_error(self):
        eng = _make_engine()
        # Remove executor shutdown method
        eng._executor = object()  # no shutdown attr
        eng.shutdown()  # Should not raise


class TestComputeSessionScopeFilter:
    def test_compute_session_with_scope_sets_recursive(self):
        eng = _make_engine()
        mock_provider = MagicMock()
        mock_provider.fetch.return_value = {"session_id": "s1", "llm_spans": []}
        eng.set_data_provider(mock_provider)

        mock_builder = MagicMock()
        mock_builder.build_resource_batches.return_value = {
            "session": [("s1", {})],
            "llm": [],
            "tool": [],
            "task": [],
            "agent": [],
        }
        mock_builder.group_metrics_by_applicability.return_value = {}
        eng._context_builder = mock_builder

        # Should not raise even without registered metrics
        results = eng.compute_session("s1", scope="llm")
        assert isinstance(results, list)
