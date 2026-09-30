#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""End-to-end YAML scenario tests for MCEWorkerService.

These tests validate the full chain:
  YAML config → _get_restricted_engine (scope-restricted metrics)
              → compute_session (real engine, real KnowledgeGraphCache)
              → MockKGProvider.save_metrics (asserted write log)

No real Neo4j connection, no real LLM calls.  Two test doubles are used:

- MockKGProvider  : implements both DataProvider (fetch) and MCEProvider
                    (save_metrics / get_metrics).  All writes are recorded
                    for assertion; get_metrics returns pre-seeded results
                    to simulate cache hits.
- MockMetric      : a lightweight Metric subclass that returns a fixed value
                    without any I/O, directly replacing the real metrics
                    returned by discover_all_metrics().

The MCEWorkerService and MCEClient both accept an optional ``kg_provider``
parameter for dependency injection — no patching needed at worker/client level.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import yaml

from mce.core.metric import Metric, MetricRequirements
from mce.core.metadata import MetricMetadata, MetricLayer, MetricNature, MetricScope
from mce.core.types import MetricResult
from mce.helper.interfaces import MetricsProvider


# ---------------------------------------------------------------------------
# MockKGProvider
# ---------------------------------------------------------------------------


class MockKGProvider(MetricsProvider):
    """In-memory test double for both DataProvider and MCEProvider interfaces.

    Parameters
    ----------
    session_data:
        Maps ``resource_id`` → context dict returned by ``fetch()``.
        Each context should contain ``session_id``, ``session``,
        ``llm_spans`` and ``tool_spans`` keys so the ContextBuilder
        can build all batches.
    seeded_metrics:
        MetricResult objects returned by ``get_metrics()``; these
        simulate existing KG cache entries and will suppress metric
        recomputation for matching (resource_id, metric_id) pairs.
    """

    def __init__(
        self,
        session_data: dict[str, dict[str, Any]] | None = None,
        seeded_metrics: list[MetricResult] | None = None,
    ):
        self.session_data: dict[str, dict[str, Any]] = session_data or {}
        self.seeded_metrics: list[MetricResult] = seeded_metrics or []

        # Write log — each flush produces one entry (a list of MetricResults).
        self.saved: list[list[MetricResult]] = []
        # Full call log for debugging.
        self.calls: list[tuple[str, Any]] = []

    # ------------------------------------------------------------------
    # DataProvider interface (engine.set_data_provider)
    # ------------------------------------------------------------------

    def fetch(
        self, resource_id: str, requirements: MetricRequirements
    ) -> dict[str, Any]:
        self.calls.append(("fetch", resource_id))
        ctx = dict(self.session_data.get(resource_id, {"session_id": resource_id}))
        # Ensure a "session" dict is present so session-level metrics work.
        if "session" not in ctx:
            ctx["session"] = {
                k: v
                for k, v in ctx.items()
                if k not in ("spans", "llm_spans", "tool_spans")
            }
        return ctx

    def fetch_batch(
        self, resource_ids: list[str], requirements: MetricRequirements
    ) -> list[dict[str, Any]]:
        return [self.fetch(rid, requirements) for rid in resource_ids]

    # ------------------------------------------------------------------
    # MCEProvider interface (KnowledgeGraphCache.provider)
    # ------------------------------------------------------------------

    def save_metrics(self, metrics: list[MetricResult]) -> bool:
        # flush() clears the buffer in-place *after* this call, so we copy now.
        snapshot = list(metrics)
        self.saved.append(snapshot)
        self.calls.append(("save_metrics", snapshot))
        return True

    def get_metrics(
        self,
        resource_ids: str | list[str],
        metric_ids: str | list[str] | None = None,
        session_ids: str | list[str] | None = None,
        **kwargs,
    ) -> list[MetricResult]:
        self.calls.append(("get_metrics", resource_ids))
        rids = {resource_ids} if isinstance(resource_ids, str) else set(resource_ids)
        mids = (
            ({metric_ids} if isinstance(metric_ids, str) else set(metric_ids))
            if metric_ids is not None
            else None
        )
        return [
            r
            for r in self.seeded_metrics
            if r.resource_id in rids and (mids is None or r.metric_id in mids)
        ]

    # ------------------------------------------------------------------
    # KGProvider / MetricsProvider abstract stubs (not used by test path)
    # ------------------------------------------------------------------

    def query_nodes(self, entity_type: str, options: Any | None = None) -> list[dict]:
        return []

    def clean_metrics(self, resource_ids: Any = None) -> bool:
        return True

    def get_metrics_over_time(self, *args: Any, **kwargs: Any) -> list:
        return []

    # ------------------------------------------------------------------
    # Convenience helpers for assertions
    # ------------------------------------------------------------------

    @property
    def all_saved(self) -> list[MetricResult]:
        """Flat list of every MetricResult written across all flush() calls."""
        return [r for batch in self.saved for r in batch]

    def saved_metric_ids(self) -> set[str]:
        return {r.metric_id for r in self.all_saved}

    def saved_for_resource(self, resource_id: str) -> list[MetricResult]:
        return [r for r in self.all_saved if r.resource_id == resource_id]


# ---------------------------------------------------------------------------
# MockMetric factory
# ---------------------------------------------------------------------------


def make_mock_metric(name: str, target_type: str, value: float = 0.75) -> Metric:
    """Return a Metric subclass that always returns *value* without any I/O.

    Parameters
    ----------
    name:
        The ``metric_id`` / metadata name (e.g. ``"GoalSuccessRate"``).
    target_type:
        The ontology URI this metric applies to (e.g. ``"mas:Session"``).
        Assigned directly to ``metadata.target_types`` so ``ensure_target_types``
        leaves it untouched.
    value:
        Fixed float returned by ``compute()``.
    """
    _target = target_type
    _value = value

    meta = MetricMetadata(
        name=name,
        description=f"Mock metric {name}",
        layer=MetricLayer.EXECUTION,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.SESSION,
        ontology_class=name,
        target_types={_target},
    )

    class _MockMetric(Metric):
        metadata = meta

        @property
        def input_requirements(self) -> MetricRequirements:
            return MetricRequirements()

        def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Mock",
                value=_value,
                metric_class=self.ontology_class,
            )

    _MockMetric.__name__ = f"Mock_{name}"
    return _MockMetric()


# ---------------------------------------------------------------------------
# Session context builder
# ---------------------------------------------------------------------------


def make_session_context(
    session_id: str,
    n_llm: int = 0,
    n_tool: int = 0,
) -> dict[str, Any]:
    """Build a minimal DataProvider context that the ContextBuilder accepts.

    Produces a context with ``n_llm`` LLM spans and ``n_tool`` tool spans.
    Each span dict contains an ``executionId`` and ``duration``.
    """
    llm_spans = [
        {"executionId": f"llm-{i}", "model": "mock-model", "duration": 100.0}
        for i in range(n_llm)
    ]
    tool_spans = [
        {"executionId": f"tool-{i}", "toolName": "mock_tool", "duration": 50.0}
        for i in range(n_tool)
    ]
    ctx: dict[str, Any] = {
        "session_id": session_id,
        "session": {"session_id": session_id, "duration": 1000.0, "startTime": 0.0},
        "llm_spans": llm_spans,
        "tool_spans": tool_spans,
        "conversation_text": "",
        "input_text": "hello",
        "output_text": "world",
    }
    return ctx


# ---------------------------------------------------------------------------
# Worker service factory (no real Neo4j, no real LLM)
# ---------------------------------------------------------------------------


def make_worker_for_scenario(
    tmp_path,
    yaml_metrics: dict[str, list[str]],
    mock_kg: MockKGProvider,
    cache_write: bool = True,
    cache_read: bool = False,
) -> Any:
    """Create an MCEWorkerService fully wired to *mock_kg* via DI.

    No patching of MCEClient or Neo4j — the provider is injected directly
    through the ``kg_provider`` parameter added to both MCEClient and
    MCEWorkerService.
    """
    from mce.client.worker import MCEWorkerService

    cfg = {
        "engine": {"max_workers": 1, "execution_strategy": "thread"},
        "cache": {"path": None, "read": cache_read, "write": cache_write},
        "metrics": yaml_metrics,
    }
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump(cfg))

    return MCEWorkerService(cfg_file, kg_provider=mock_kg)


# ---------------------------------------------------------------------------
# Scenario tests
# ---------------------------------------------------------------------------

_SESSION_ID = "session-abc"

# Maps YAML scope key → ontology URI (mirrors worker._YAML_SCOPE_TO_ONTOLOGY_URI)
_URI = {
    "Session": "mas:Session",
    "LLMCall": "mas:LLMCall",
    "ToolCall": "mas:ToolCall",
}


class TestSessionOnlyYaml:
    """YAML with only Session-level metrics: M=2 metrics, no spans.
    Expected: exactly 2 results written (one per metric, on session resource_id)."""

    _YAML = {"Session": ["GoalSuccessRate", "AnswerRelevancy"]}
    _MOCKS = [
        make_mock_metric("GoalSuccessRate", _URI["Session"], value=0.9),
        make_mock_metric("AnswerRelevancy", _URI["Session"], value=0.8),
    ]

    def test_save_metrics_called_once(self, tmp_path):
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
        )
        svc = make_worker_for_scenario(tmp_path, self._YAML, mock_kg)

        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        assert len(mock_kg.saved) == 1, "flush() should fire exactly once per session"

    def test_exactly_M_results_written(self, tmp_path):
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
        )
        svc = make_worker_for_scenario(tmp_path, self._YAML, mock_kg)

        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        assert len(mock_kg.all_saved) == 2
        assert mock_kg.saved_metric_ids() == {"GoalSuccessRate", "AnswerRelevancy"}

    def test_all_results_on_session_resource(self, tmp_path):
        """All saved results must reference the session resource_id."""
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
        )
        svc = make_worker_for_scenario(tmp_path, self._YAML, mock_kg)

        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        assert all(r.resource_id == _SESSION_ID for r in mock_kg.all_saved)


class TestMixedYaml:
    """YAML with Session×M + LLMCall×N + ToolCall×P.
    Session: 2 metrics  (GoalSuccessRate, AnswerRelevancy)
    LLMCall: 1 metric   (Duration)     × 3 LLM spans
    ToolCall: 1 metric  (ToolError)    × 2 tool spans
    Expected total writes: 2 + 3 + 2 = 7."""

    _M, _N_LLM_SPANS, _N_TOOL_SPANS = 2, 3, 2
    _YAML = {
        "Session": ["GoalSuccessRate", "AnswerRelevancy"],
        "LLMCall": ["Duration"],
        "ToolCall": ["ToolError"],
    }
    _MOCKS = [
        make_mock_metric("GoalSuccessRate", _URI["Session"], value=0.9),
        make_mock_metric("AnswerRelevancy", _URI["Session"], value=0.7),
        make_mock_metric("Duration", _URI["LLMCall"], value=120.0),
        make_mock_metric("ToolError", _URI["ToolCall"], value=0.0),
    ]

    def _run(self, tmp_path) -> MockKGProvider:
        mock_kg = MockKGProvider(
            session_data={
                _SESSION_ID: make_session_context(
                    _SESSION_ID, n_llm=self._N_LLM_SPANS, n_tool=self._N_TOOL_SPANS
                )
            },
        )
        svc = make_worker_for_scenario(tmp_path, self._YAML, mock_kg)
        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)
        return mock_kg

    def test_total_write_count(self, tmp_path):
        mock_kg = self._run(tmp_path)
        expected = self._M + 1 * self._N_LLM_SPANS + 1 * self._N_TOOL_SPANS
        assert len(mock_kg.all_saved) == expected

    def test_session_metric_count_equals_M(self, tmp_path):
        mock_kg = self._run(tmp_path)
        session_saved = [
            r
            for r in mock_kg.all_saved
            if r.metric_id in {"GoalSuccessRate", "AnswerRelevancy"}
        ]
        assert len(session_saved) == self._M

    def test_llm_metric_count_equals_N_times_spans(self, tmp_path):
        mock_kg = self._run(tmp_path)
        llm_saved = [r for r in mock_kg.all_saved if r.metric_id == "Duration"]
        assert len(llm_saved) == self._N_LLM_SPANS

    def test_tool_metric_count_equals_P_times_spans(self, tmp_path):
        mock_kg = self._run(tmp_path)
        tool_saved = [r for r in mock_kg.all_saved if r.metric_id == "ToolError"]
        assert len(tool_saved) == self._N_TOOL_SPANS

    def test_llm_results_reference_span_resource_ids(self, tmp_path):
        mock_kg = self._run(tmp_path)
        llm_rids = {
            r.resource_id for r in mock_kg.all_saved if r.metric_id == "Duration"
        }
        expected_rids = {f"llm-{i}" for i in range(self._N_LLM_SPANS)}
        assert llm_rids == expected_rids

    def test_tool_results_reference_span_resource_ids(self, tmp_path):
        mock_kg = self._run(tmp_path)
        tool_rids = {
            r.resource_id for r in mock_kg.all_saved if r.metric_id == "ToolError"
        }
        expected_rids = {f"tool-{i}" for i in range(self._N_TOOL_SPANS)}
        assert tool_rids == expected_rids

    def test_declared_metric_ids_only(self, tmp_path):
        """No metric outside the YAML declaration sneaks into the write log."""
        mock_kg = self._run(tmp_path)
        assert mock_kg.saved_metric_ids() == {
            "GoalSuccessRate",
            "AnswerRelevancy",
            "Duration",
            "ToolError",
        }


class TestCacheReadSkipsRecompute:
    """Pre-seeding a metric in MockKGProvider.seeded_metrics simulates an
    existing KG cache entry.  With cache_read=True the engine must skip
    recomputing it — so save_metrics receives only the missing metrics."""

    _YAML = {"Session": ["GoalSuccessRate", "AnswerRelevancy"]}
    _MOCKS = [
        make_mock_metric("GoalSuccessRate", _URI["Session"], value=0.9),
        make_mock_metric("AnswerRelevancy", _URI["Session"], value=0.8),
    ]

    def _seeded_result(self, metric_id: str) -> MetricResult:
        return MetricResult(
            metric_id=metric_id,
            resource_id=_SESSION_ID,
            provider="Neo4j",
            value=0.5,
        )

    def test_cached_metric_not_rewritten(self, tmp_path):
        """GoalSuccessRate is already in the KG → only AnswerRelevancy is written."""
        seeded = [self._seeded_result("GoalSuccessRate")]
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
            seeded_metrics=seeded,
        )
        svc = make_worker_for_scenario(
            tmp_path, self._YAML, mock_kg, cache_read=True, cache_write=True
        )
        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        # Only AnswerRelevancy should have been newly computed and written
        assert mock_kg.saved_metric_ids() == {"AnswerRelevancy"}

    def test_all_cached_nothing_written(self, tmp_path):
        """Both metrics already in KG → save_metrics never called."""
        seeded = [
            self._seeded_result("GoalSuccessRate"),
            self._seeded_result("AnswerRelevancy"),
        ]
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
            seeded_metrics=seeded,
        )
        svc = make_worker_for_scenario(
            tmp_path, self._YAML, mock_kg, cache_read=True, cache_write=True
        )
        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        assert len(mock_kg.saved) == 0  # flush() is no-op when buffer is empty

    def test_cache_read_false_recomputes_all(self, tmp_path):
        """Even if seeded, cache_read=False forces full recomputation."""
        seeded = [self._seeded_result("GoalSuccessRate")]
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
            seeded_metrics=seeded,
        )
        svc = make_worker_for_scenario(
            tmp_path, self._YAML, mock_kg, cache_read=False, cache_write=True
        )
        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        assert mock_kg.saved_metric_ids() == {"GoalSuccessRate", "AnswerRelevancy"}


class TestCacheWriteDisabled:
    """cache_write: false in YAML → computed results must NOT be persisted."""

    _YAML_NO_WRITE = {
        "engine": None,  # overridden in make_worker_for_scenario
        "metrics": {"Session": ["GoalSuccessRate"]},
    }
    _MOCKS = [make_mock_metric("GoalSuccessRate", _URI["Session"], value=0.9)]

    def test_save_metrics_never_called(self, tmp_path):
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
        )
        svc = make_worker_for_scenario(
            tmp_path,
            {"Session": ["GoalSuccessRate"]},
            mock_kg,
            cache_write=False,
        )
        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        assert len(mock_kg.saved) == 0


class TestEmptyYaml:
    """No metrics declared → engine does nothing → save_metrics never called."""

    def test_no_write_when_no_metrics(self, tmp_path):
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
        )
        svc = make_worker_for_scenario(tmp_path, {}, mock_kg)

        with patch("mce.core.registry.discovery.discover_all_metrics", return_value=[]):
            result = svc.process_session(_SESSION_ID)

        assert result == []
        assert len(mock_kg.saved) == 0


class TestMetricValuesInWriteLog:
    """Verify that the values written to the KG match MockMetric output."""

    _YAML = {"Session": ["GoalSuccessRate"]}
    _VALUE = 0.42
    _MOCKS = [make_mock_metric("GoalSuccessRate", _URI["Session"], value=_VALUE)]

    def test_written_value_matches_mock_metric(self, tmp_path):
        mock_kg = MockKGProvider(
            session_data={_SESSION_ID: make_session_context(_SESSION_ID)},
        )
        svc = make_worker_for_scenario(tmp_path, self._YAML, mock_kg)

        with patch(
            "mce.core.registry.discovery.discover_all_metrics", return_value=self._MOCKS
        ):
            svc.process_session(_SESSION_ID)

        saved = mock_kg.all_saved
        assert len(saved) == 1
        assert saved[0].value == pytest.approx(self._VALUE)
        assert saved[0].metric_id == "GoalSuccessRate"
        assert saved[0].resource_id == _SESSION_ID
