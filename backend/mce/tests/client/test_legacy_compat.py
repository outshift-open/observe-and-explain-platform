#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Legacy compatibility tests for mce-client.

Adapted from
  telemetry-hub/metrics_computation_engine/src/metrics_computation_engine/tests/
to ensure the new mce-client/mce interface remains backward-compatible with
legacy MCE consumers (workflows worker, oxp-backend, etc.).

Sources for ported test patterns:
  - test_registry.py                      → TestEngineRegistryCompat
  - test_metric_processor_compatibility.py → TestMetricComputeBatchCompat
  - test_processor.py                     → TestWorkerOutputStructureCompat
  - models/eval.py + types.py             → TestMetricResultLegacyFormat
"""

from __future__ import annotations

import inspect
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from mce.core.types import MetricResult, LLMJudgeResult, normalize_metric_id

# ===========================================================================
# TestMetricResultLegacyFormat
# Ported from: types.py + old MCE models/eval.py consumer expectations.
#
# The old MCE's MetricResult had: metric_name, value, aggregation_level,
# category, app_name, agent_id, description, reasoning, unit, span_id,
# session_id, source, entities_involved, edges_involved, success, metadata,
# label, error_message, from_cache.
#
# The new MetricResult exposes a to_legacy_dict() that legacy consumers read.
# ===========================================================================


class TestMetricResultLegacyFormat:
    """Verify that MetricResult.to_legacy_dict() satisfies the legacy consumer contract."""

    # Required top-level keys expected in every legacy dict — taken from the
    # old MCE consumers (MCEWrapper test uses "metricName" and "value").
    REQUIRED_KEYS = {
        "metricName",
        "value",
        "score",
        "reasoning",
        "provider",
        "timestamp",
        "type",
    }

    def _make_result(self, **kwargs) -> MetricResult:
        defaults = dict(
            metric_id="AnswerRelevancy",
            resource_id="sess-1",
            provider="DeepEval",
            value=0.85,
        )
        defaults.update(kwargs)
        return MetricResult(**defaults)

    def test_to_legacy_dict_contains_all_required_keys(self):
        """to_legacy_dict returns every key expected by legacy consumers."""
        result = self._make_result()
        d = result.to_legacy_dict()
        missing = self.REQUIRED_KEYS - d.keys()
        assert not missing, f"to_legacy_dict missing keys: {missing}"

    def test_to_legacy_dict_value_is_float(self):
        """value field is a numeric type (float/int)."""
        result = self._make_result(value=0.75)
        d = result.to_legacy_dict()
        assert isinstance(d["value"], (float, int))
        assert d["value"] == pytest.approx(0.75)

    def test_to_legacy_dict_score_equals_value(self):
        """score is a backward-compat alias for value — must equal value."""
        result = self._make_result(value=0.6)
        d = result.to_legacy_dict()
        assert d["score"] == d["value"]

    def test_to_legacy_dict_timestamp_is_iso_string(self):
        """timestamp serialises to an ISO-8601 string (compat with V1 consumers)."""
        result = self._make_result()
        d = result.to_legacy_dict()
        ts = d["timestamp"]
        assert isinstance(ts, str)
        # Verify it parses back to a datetime without error
        datetime.fromisoformat(ts)

    def test_to_legacy_dict_metric_name_maps_to_metric_class(self):
        """metricName key is populated from metric_class (not metric_id)."""
        result = self._make_result(metric_class="AnswerRelevancy")
        d = result.to_legacy_dict()
        assert d["metricName"] == "AnswerRelevancy"

    def test_to_legacy_dict_default_type_is_quality(self):
        """type defaults to 'Quality' when not set in metadata (legacy default)."""
        result = self._make_result()
        d = result.to_legacy_dict()
        assert d["type"] == "Quality"

    def test_to_legacy_dict_custom_type_from_metadata(self):
        """type is overridden by metadata['legacy_type'] when present."""
        result = self._make_result(metadata={"legacy_type": "Performance"})
        d = result.to_legacy_dict()
        assert d["type"] == "Performance"

    def test_to_legacy_dict_reasoning_present(self):
        """reasoning key is present and matches the result reasoning."""
        result = self._make_result(reasoning="The response is relevant.")
        d = result.to_legacy_dict()
        assert d["reasoning"] == "The response is relevant."

    def test_to_legacy_dict_empty_reasoning_is_string(self):
        """reasoning is a string even when not set (not None)."""
        result = self._make_result()
        d = result.to_legacy_dict()
        assert isinstance(d["reasoning"], str)

    def test_llm_judge_result_to_legacy_dict_extends_base(self):
        """LLMJudgeResult.to_legacy_dict adds model/tokens on top of base keys."""
        result = LLMJudgeResult(
            metric_id="AnswerRelevancy",
            resource_id="sess-1",
            provider="DeepEval",
            value=0.9,
            model_name="gpt-4",
            tokens_used=512,
        )
        d = result.to_legacy_dict()
        # Base keys are present
        assert self.REQUIRED_KEYS <= d.keys()
        # LLM-specific extensions
        assert "model" in d
        assert d["model"] == "gpt-4"
        assert "tokens" in d
        assert d["tokens"] == 512

    def test_score_property_equals_value(self):
        """MetricResult.score property is a read-only alias of value."""
        result = self._make_result(value=0.42)
        assert result.score == result.value == pytest.approx(0.42)


# ===========================================================================
# TestNormalizeMetricId
# Ported from: old MCE convention where metric classes were named with a
# trailing "Metric" suffix (e.g., "AnswerRelevancyMetric").  normalize_metric_id
# strips that suffix for backward-compat cache lookups.
# ===========================================================================


class TestNormalizeMetricId:
    """normalize_metric_id handles the old 'Metric' suffix convention."""

    def test_strips_metric_suffix(self):
        assert normalize_metric_id("AnswerRelevancyMetric") == "AnswerRelevancy"

    def test_no_op_when_no_suffix(self):
        assert normalize_metric_id("AnswerRelevancy") == "AnswerRelevancy"

    def test_no_op_for_native_metric_names(self):
        """Native metric IDs that don't end in Metric are unchanged."""
        for name in ("ToolErrorRate", "Duration", "TokenCount", "Cost"):
            assert normalize_metric_id(name) == name

    def test_only_trailing_suffix_stripped(self):
        """Only the trailing 'Metric' is stripped, not occurrences mid-string."""
        assert normalize_metric_id("MetricFoo") == "MetricFoo"

    def test_empty_string_safe(self):
        assert normalize_metric_id("") == ""


# ===========================================================================
# TestEngineRegistryCompat
# Adapted from: test_registry.py
# TestRegistryBasicOperations, TestRegistryMultipleMetrics
#
# Old MCE had MetricRegistry.register_metric(class, name) / get_metric(name).
# New MCE has MetricEngine.register_metric(instance) / get_metric(metric_id).
# Both support: start empty, register, lookup, list all.
# ===========================================================================


class TestEngineRegistryCompat:
    """MetricEngine registry operations mirror the old MetricRegistry contract."""

    def _make_engine(self) -> object:
        from mce.engine.engine import MetricEngine

        return MetricEngine(max_workers=1, execution_strategy="thread")

    def _make_metric(
        self, metric_id: str = "TestMetric", ontology_class: str = "TestMetric"
    ) -> MagicMock:
        """Create a minimal mock metric that MetricEngine.register_metric accepts."""
        from mce.core.metric import Metric

        m = MagicMock(spec=Metric)
        m.metric_id = metric_id
        m.ontology_class = ontology_class
        m.metadata = MagicMock()
        m.metadata.target_types = set()
        m.metadata.attachment_point = None
        m.metadata.scope = None
        m.metadata.dependencies = []
        return m

    # --- Ported from TestRegistryBasicOperations.test_registry_initialization ---
    def test_engine_starts_with_empty_registry(self):
        """Engine registry starts empty — equivalent to MetricRegistry()."""
        engine = self._make_engine()
        assert engine._registry == {}
        assert engine._all_metrics == []

    # --- Ported from TestRegistryBasicOperations.test_register_metric_with_explicit_name ---
    def test_register_metric_is_discoverable_by_id(self):
        """After registration, get_metric(metric_id) returns the metric instance."""
        engine = self._make_engine()
        metric = self._make_metric("MyMetric")

        engine.register_metric(metric)

        retrieved = engine.get_metric("MyMetric")
        assert retrieved is metric

    # --- Ported from TestRegistryBasicOperations.test_get_metric_nonexistent ---
    def test_get_metric_nonexistent_returns_none(self):
        """get_metric returns None for an unregistered metric_id."""
        engine = self._make_engine()
        result = engine.get_metric("NonExistentMetric")
        assert result is None

    # --- Ported from TestRegistryMultipleMetrics.test_register_multiple_different_metrics ---
    def test_register_multiple_metrics_all_discoverable(self):
        """All registered metrics appear in _all_metrics."""
        engine = self._make_engine()
        m1 = self._make_metric("Metric1", "Metric1")
        m2 = self._make_metric("Metric2", "Metric2")
        m3 = self._make_metric("Metric3", "Metric3")

        engine.register_metric(m1)
        engine.register_metric(m2)
        engine.register_metric(m3)

        all_ids = {m.metric_id for m in engine._all_metrics}
        assert {"Metric1", "Metric2", "Metric3"} <= all_ids

    # --- Ported from TestRegistryMultipleMetrics.test_register_same_name_twice_overwrites ---
    def test_register_same_metric_id_replaces_previous(self):
        """Registering a metrics with the same metric_id replaces the old one."""
        engine = self._make_engine()
        m1 = self._make_metric("MyMetric")
        m2 = self._make_metric("MyMetric")  # same metric_id, different object

        engine.register_metric(m1)
        engine.register_metric(m2)

        retrieved = engine.get_metric("MyMetric")
        assert retrieved is m2

    def test_select_implementation_nonexistent_returns_none(self):
        """select_implementation returns None for unknown ontology_class — mirrors get_metric."""
        engine = self._make_engine()
        assert engine.select_implementation("UnknownClass") is None


# ===========================================================================
# TestMetricComputeBatchCompat
# Adapted from: test_metric_processor_compatibility.py
# TestMetricProcessorCompatibility.test_metric_compute_signatures
#
# Old MCE required all metric compute() methods to accept **kwargs so the
# MetricsProcessor could inject context.  New MCE uses compute_batch() with
# explicit (resource_ids, contexts) signature.  This test verifies that all
# discovered metrics expose the expected compute_batch interface.
# ===========================================================================


class TestMetricComputeBatchCompat:
    """All discovered mce metrics satisfy the expected compute_batch contract."""

    def test_discover_returns_nonempty_list(self):
        """discover_all_metrics() returns at least one metric — parity with old NATIVE_METRICS."""
        from mce.core.registry.discovery import discover_all_metrics

        metrics = discover_all_metrics()
        assert len(metrics) > 0, "discover_all_metrics() returned empty list"

    # --- Ported from TestMetricProcessorCompatibility.test_metric_compute_signatures ---
    def test_all_metrics_have_compute_batch(self):
        """Every metric exposes compute_batch(resource_ids, contexts) — replaces old **kwargs check."""
        from mce.core.registry.discovery import discover_all_metrics

        metrics = discover_all_metrics()
        missing = []
        for m in metrics:
            if not callable(getattr(m, "compute_batch", None)):
                missing.append(m.metric_id)
        assert not missing, f"Metrics missing compute_batch: {missing}"

    def test_all_metrics_have_metric_id(self):
        """Every metric has a non-empty metric_id — equivalent to old metric_name."""
        from mce.core.registry.discovery import discover_all_metrics

        for m in discover_all_metrics():
            assert isinstance(m.metric_id, str) and m.metric_id, (
                f"metric has empty/None metric_id: {m!r}"
            )

    def test_all_metrics_have_ontology_class(self):
        """Every metric has a non-empty ontology_class — used for engine routing."""
        from mce.core.registry.discovery import discover_all_metrics

        for m in discover_all_metrics():
            assert isinstance(m.ontology_class, str) and m.ontology_class, (
                f"metric {m.metric_id!r} has empty/None ontology_class"
            )

    def test_compute_batch_signature_accepts_resource_ids_and_contexts(self):
        """compute_batch signature must accept positional (resource_ids, contexts)."""
        from mce.core.registry.discovery import discover_all_metrics

        incompatible = []
        for m in discover_all_metrics():
            cb = getattr(m, "compute_batch", None)
            if not callable(cb):
                continue
            sig = inspect.signature(cb)
            params = [
                name
                for name, p in sig.parameters.items()
                if name not in ("self",)
                and p.kind
                not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                )
            ]
            # compute_batch must accept at least two positional params (resources, contexts)
            if len(params) < 2:
                incompatible.append(f"{m.metric_id}: {sig}")
        assert not incompatible, (
            "Metrics with incompatible compute_batch signature:\n"
            + "\n".join(f"  - {s}" for s in incompatible)
        )

    # --- Ported from TestMetricProcessorCompatibility.test_metric_coverage_report ---
    def test_native_metrics_count_at_least_matches_known_minimum(self):
        """At least 4 native metrics are available (Duration, Cost, TokenCount, ToolError)."""
        from mce.core.registry.discovery import discover_all_metrics

        metrics = discover_all_metrics()
        ids = {m.metric_id for m in metrics}
        known_native = {"Duration", "Cost", "TokenCount", "ToolError"}
        missing = known_native - ids
        assert not missing, f"Expected native metrics missing: {missing}"


# ===========================================================================
# TestWorkerOutputStructureCompat
# Adapted from: test_processor.py
# TestEmptyDataHandling + TestComputeMetricsValidSessions
#
# Old MCE: processor.compute_metrics(session_set) returned:
#   { "span_metrics": [...], "session_metrics": [...], "agent_metrics": [...],
#     "population_metrics": [...], "failed_metrics": [...] }
#
# New MCE: MCEWorkerService.process_session(session_id) returns list[dict].
#          MCEWorkerService.process_batch(session_ids) returns dict[str, list[dict]].
# Legacy consumers (MCEWrapper) pass through these structures unchanged.
# ===========================================================================


def _make_result(
    metric_id: str = "AnswerRelevancy", resource_id: str = "s1", value: float = 0.8
) -> MagicMock:
    r = MagicMock(spec=MetricResult)
    r.metric_id = metric_id
    r.error = None  # no error → valid result
    r.to_legacy_dict.return_value = {
        "metricName": metric_id,
        "value": value,
        "score": value,
        "reasoning": "",
        "provider": "native",
        "timestamp": "2026-01-01T00:00:00",
        "type": "Quality",
    }
    return r


def _make_svc() -> object:
    """MCEWorkerService with WorkerConfig and MCEClient both mocked."""
    from mce.client.worker import MCEWorkerService, WorkerConfig

    cfg = MagicMock(spec=WorkerConfig)
    cfg.max_workers = 2
    cfg.execution_strategy = "thread"
    cfg.scope_metrics = {"Session": ["AnswerRelevancy"], "LLMCall": ["Duration"]}
    cfg.session_metrics = ["AnswerRelevancy"]
    cfg.element_metrics = ["Duration"]
    cfg.has_element_metrics = True
    cfg._session_metric_ids = frozenset({"AnswerRelevancy"})
    cfg._element_metric_ids = frozenset({"Duration"})
    cfg.all_metric_ids = frozenset({"AnswerRelevancy", "Duration"})
    cfg.cache_path = None
    cfg.cache_read = True
    cfg.cache_write = True

    mock_client = MagicMock()
    with (
        patch("mce.client.worker.WorkerConfig", return_value=cfg),
        patch("mce.client.worker.MCEClient", return_value=mock_client),
    ):
        svc = MCEWorkerService()

    svc._cfg = cfg
    svc._client = mock_client
    return svc


class TestWorkerOutputStructureCompat:
    """MCEWorkerService output is structurally compatible with old MCE consumers."""

    def _mock_engines(self, svc, compute_return_value):
        """Mock _get_restricted_engine with a single engine returning compute_return_value."""
        engine = MagicMock()
        engine.set_data_provider = MagicMock()
        engine.compute_session.return_value = compute_return_value
        svc._get_restricted_engine = MagicMock(return_value=engine)
        return engine

    # --- Ported from TestEmptyDataHandling.test_compute_metrics_empty_session_set ---
    def test_process_session_returns_list(self):
        """process_session always returns a list (never None) — equivalent to
        processor.compute_metrics() returning an empty list when no sessions."""
        svc = _make_svc()
        self._mock_engines(svc, [])
        svc._client._get_kg_provider.return_value.save_metrics = MagicMock()

        result = svc.process_session("sess-empty")
        assert isinstance(result, list)
        assert result == []

    def test_process_session_with_results_returns_list_of_dicts(self):
        """process_session returns list of dicts (to_legacy_dict output)."""
        svc = _make_svc()
        self._mock_engines(svc, [_make_result("AnswerRelevancy", "sess-1", 0.84)])
        svc._client._get_kg_provider.return_value.save_metrics = MagicMock()

        results = svc.process_session("sess-1")
        assert isinstance(results, list)
        assert len(results) >= 1
        assert isinstance(results[0], dict)
        assert "metricName" in results[0]
        assert "value" in results[0]

    def test_process_session_each_dict_has_required_legacy_keys(self):
        """Each dict in process_session output has the full legacy schema."""
        svc = _make_svc()
        self._mock_engines(
            svc,
            [
                _make_result("AnswerRelevancy", "sess-1", 0.84),
                _make_result("Duration", "sess-1", 2500.0),
            ],
        )
        svc._client._get_kg_provider.return_value.save_metrics = MagicMock()

        results = svc.process_session("sess-1")
        for d in results:
            for key in (
                "metricName",
                "value",
                "score",
                "reasoning",
                "provider",
                "timestamp",
                "type",
            ):
                assert key in d, f"Legacy key '{key}' missing from result dict: {d}"

    # --- Ported from TestEmptyDataHandling.test_compute_metrics_batch_returns_dict ---
    def test_process_batch_returns_dict_keyed_by_session_id(self):
        """process_batch returns a dict[session_id → list] — same contract as old DAL."""
        svc = _make_svc()
        self._mock_engines(svc, [])
        svc._client._get_kg_provider.return_value.save_metrics = MagicMock()

        session_ids = ["sess-1", "sess-2", "sess-3"]
        result = svc.process_batch(session_ids)

        assert isinstance(result, dict)
        for sid in session_ids:
            assert sid in result, f"session_id {sid!r} missing from batch result"
            assert isinstance(result[sid], list)

    def test_process_batch_empty_session_id_list(self):
        """process_batch with empty list returns empty dict — mirrors old empty session_set handling."""
        svc = _make_svc()
        self._mock_engines(svc, [])
        svc._client._get_kg_provider.return_value.save_metrics = MagicMock()

        result = svc.process_batch([])
        assert result == {}

    def test_process_batch_bulk_writes_once(self):
        """process_batch calls compute_sessions_batch once for all sessions (single KG round-trip)."""
        svc = _make_svc()
        engine = self._mock_engines(svc, [_make_result()])
        engine.compute_sessions_batch = MagicMock(
            return_value={
                "sess-1": [_make_result()],
                "sess-2": [_make_result()],
            }
        )

        result = svc.process_batch(["sess-1", "sess-2"])

        # One bulk engine call covers all sessions, not one call per session
        engine.compute_sessions_batch.assert_called_once_with(["sess-1", "sess-2"])
        assert set(result.keys()) == {"sess-1", "sess-2"}

    def test_process_session_no_kg_write_when_empty(self):
        """process_session skips KG write when no results are produced."""
        svc = _make_svc()
        self._mock_engines(svc, [])
        mock_kg = svc._client._get_kg_provider.return_value
        mock_kg.save_metrics = MagicMock()

        svc.process_session("sess-no-results")
        mock_kg.save_metrics.assert_not_called()


# ===========================================================================
# TestClientInterfaceCompat
# Verify that MCEClient exposes the stable API expected by workflow consumers.
# ===========================================================================


class TestClientInterfaceCompat:
    """MCEClient public API parity with what callers expect."""

    def test_client_has_compute_and_store(self):
        """compute_and_store() is the new equivalent of old processor.compute_metrics()."""
        from mce.client import MCEClient

        assert callable(getattr(MCEClient, "compute_and_store", None))

    def test_client_has_get_metrics(self):
        """get_metrics() retrieves pre-computed results — DAL equivalent of old DAL API."""
        from mce.client import MCEClient

        assert callable(getattr(MCEClient, "get_metrics", None))

    def test_client_has_list_sessions(self):
        """list_sessions() maps to old get_all_session_ids() from the DAL cli."""
        from mce.client import MCEClient

        assert callable(getattr(MCEClient, "list_sessions", None))

    def test_client_is_context_manager(self):
        """MCEClient supports 'with' context manager (clean resource handling)."""
        from mce.client import MCEClient

        assert hasattr(MCEClient, "__enter__") and hasattr(MCEClient, "__exit__")

    def test_worker_service_has_process_session(self):
        """MCEWorkerService.process_session is the drop-in for old processor.compute_metrics()."""
        from mce.client import MCEWorkerService

        assert callable(getattr(MCEWorkerService, "process_session", None))

    def test_worker_service_has_process_batch(self):
        """MCEWorkerService.process_batch is the drop-in for old batch DAL processing."""
        from mce.client import MCEWorkerService

        assert callable(getattr(MCEWorkerService, "process_batch", None))

    def test_package_exports_expected_symbols(self):
        """mce.client.__all__ exports the four symbols old code imports."""
        import mce.client

        for symbol in (
            "MCEClient",
            "MCEClientConfig",
            "MCEWorkerService",
            "WorkerConfig",
        ):
            assert hasattr(mce.client, symbol), f"mce.client missing export: {symbol}"
