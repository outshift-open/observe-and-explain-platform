#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.client.worker — WorkerConfig and MCEWorkerService."""

from unittest.mock import MagicMock, patch

import pytest
import yaml

from mce.core.types import MetricResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_YAML = {
    "engine": {"max_workers": 2, "execution_strategy": "thread"},
    "metrics": {
        "Session": ["AnswerRelevancy", "GoalSuccessRate"],
        "LLMCall": ["Duration", "TokenCount"],
        "ToolCall": ["ToolError"],
    },
}


def _make_result(
    metric_id: str, resource_id: str = "s1", value: float = 0.8
) -> MetricResult:
    r = MagicMock(spec=MetricResult)
    r.metric_id = metric_id
    r.error = None  # no error → valid result
    r.to_legacy_dict.return_value = {
        "metric_id": metric_id,
        "value": value,
        "resource_id": resource_id,
    }
    return r


def _make_svc(cfg_dict: dict | None = None):
    """Return an MCEWorkerService with WorkerConfig and MCEClient mocked."""
    from mce.client.worker import MCEWorkerService, WorkerConfig

    cfg = MagicMock(spec=WorkerConfig)
    d = cfg_dict or _MINIMAL_YAML
    cfg.max_workers = d["engine"]["max_workers"]
    cfg.execution_strategy = d["engine"]["execution_strategy"]
    cfg.scope_metrics = d["metrics"]
    cfg.session_metrics = d["metrics"].get("Session", [])
    _element: list[str] = []
    _seen: set[str] = set()
    for scope, names in d["metrics"].items():
        if scope == "Session":
            continue
        for name in names:
            if name not in _seen:
                _seen.add(name)
                _element.append(name)
    cfg.element_metrics = _element
    cfg.has_element_metrics = bool(_element)
    cfg._session_metric_ids = frozenset(d["metrics"].get("Session", []))
    cfg._element_metric_ids = frozenset(
        name
        for scope, names in d["metrics"].items()
        if scope != "Session"
        for name in names
    )
    cfg.all_metric_ids = cfg._session_metric_ids | cfg._element_metric_ids
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


# ---------------------------------------------------------------------------
# WorkerConfig
# ---------------------------------------------------------------------------


class TestWorkerConfig:
    def test_loads_engine_params(self, tmp_path):
        from mce.client.worker import WorkerConfig

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(_MINIMAL_YAML))
        wc = WorkerConfig(cfg_file)

        assert wc.max_workers == 2
        assert wc.execution_strategy == "thread"

    def test_loads_metric_lists(self, tmp_path):
        from mce.client.worker import WorkerConfig

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(_MINIMAL_YAML))
        wc = WorkerConfig(cfg_file)

        assert "AnswerRelevancy" in wc.session_metrics
        assert "Duration" in wc.scope_metrics["LLMCall"]
        assert "ToolError" in wc.scope_metrics["ToolCall"]

    def test_element_metrics_deduplicates(self, tmp_path):
        from mce.client.worker import WorkerConfig

        d = {
            **_MINIMAL_YAML,
            "metrics": {
                "Session": [],
                "LLMCall": ["Duration"],
                "ToolCall": ["Duration", "ToolError"],
            },
        }
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert wc.element_metrics.count("Duration") == 1
        assert "ToolError" in wc.element_metrics

    def test_has_element_metrics_false_when_empty(self, tmp_path):
        from mce.client.worker import WorkerConfig

        d = {**_MINIMAL_YAML, "metrics": {"Session": ["AnswerRelevancy"]}}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert not wc.has_element_metrics

    def test_defaults_when_sections_missing(self, tmp_path):
        from mce.client.worker import WorkerConfig

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump({}))
        wc = WorkerConfig(cfg_file)

        assert wc.max_workers == 8
        assert wc.execution_strategy == "hybrid"
        assert wc.session_metrics == []

    def test_scope_metrics_flexible_keys(self, tmp_path):
        """Arbitrary ontology-keyed scopes (e.g. AgentCall) are accepted."""
        from mce.client.worker import WorkerConfig

        d = {"metrics": {"Session": ["GoalSuccessRate"], "AgentCall": ["Duration"]}}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert "AgentCall" in wc.scope_metrics
        assert "Duration" in wc.scope_metrics["AgentCall"]
        assert "Duration" in wc.element_metrics

    def test_cache_defaults(self, tmp_path):
        """Cache section defaults to path=None, read=True, write=True."""
        from mce.client.worker import WorkerConfig

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump({}))
        wc = WorkerConfig(cfg_file)

        assert wc.cache_path is None
        assert wc.cache_read is True
        assert wc.cache_write is True

    def test_cache_custom_values(self, tmp_path):
        """Cache section custom values are loaded correctly."""
        from mce.client.worker import WorkerConfig

        d = {"cache": {"path": "/tmp/cache.json", "read": False, "write": True}}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert wc.cache_path == "/tmp/cache.json"
        assert wc.cache_read is False
        assert wc.cache_write is True

    def test_pydantic_validation_rejects_bad_strategy(self, tmp_path):
        from mce.client.worker import WorkerConfig

        d = {
            **_MINIMAL_YAML,
            "engine": {"max_workers": 2, "execution_strategy": "invalid"},
        }
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))

        with pytest.raises(ValueError, match="Invalid worker config"):
            WorkerConfig(cfg_file)

    def test_pydantic_validation_rejects_extra_top_level_keys(self, tmp_path):
        from mce.client.worker import WorkerConfig

        d = {**_MINIMAL_YAML, "unknown_key": "oops"}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))

        with pytest.raises(ValueError, match="Invalid worker config"):
            WorkerConfig(cfg_file)

    def test_validate_file_classmethod_success(self, tmp_path):
        from mce.client.worker import WorkerConfig

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(_MINIMAL_YAML))
        schema = WorkerConfig.validate_file(cfg_file)

        assert schema.engine.max_workers == 2

    def test_validate_file_classmethod_failure(self, tmp_path):
        from mce.client.worker import WorkerConfig

        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(yaml.dump({"engine": {"max_workers": -1}}))

        with pytest.raises(ValueError, match="Config validation failed"):
            WorkerConfig.validate_file(cfg_file)

    def test_to_dict_round_trip(self, tmp_path):
        from mce.client.worker import WorkerConfig

        d = {
            "engine": {"max_workers": 3, "execution_strategy": "asyncio"},
            "cache": {"path": None, "read": True, "write": False},
            "metrics": {"Session": ["GoalSuccessRate"], "LLMCall": ["Duration"]},
        }
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)
        result = wc.to_dict()

        assert result["engine"]["max_workers"] == 3
        assert result["cache"]["write"] is False
        assert result["metrics"] == {
            "Session": ["GoalSuccessRate"],
            "LLMCall": ["Duration"],
        }

    def test_loads_bundled_default_when_no_path(self):
        """Constructing with no path and no env var should load bundled default."""
        import os
        from mce.client.worker import WorkerConfig

        env_backup = os.environ.pop("MCE_WORKER_CONFIG", None)
        try:
            wc = WorkerConfig()
            assert isinstance(wc.max_workers, int)
            assert wc.max_workers >= 1
        finally:
            if env_backup is not None:
                os.environ["MCE_WORKER_CONFIG"] = env_backup


# ---------------------------------------------------------------------------
# MCEWorkerService — init
# ---------------------------------------------------------------------------


class TestMCEWorkerServiceInit:
    def test_init_passes_engine_params_to_client_config(self):
        from mce.client.worker import MCEWorkerService, WorkerConfig

        cfg = MagicMock(spec=WorkerConfig)
        cfg.max_workers = 8
        cfg.execution_strategy = "process"
        cfg.scope_metrics = {}
        cfg.session_metrics = []
        cfg.element_metrics = []
        cfg.has_element_metrics = False

        captured = {}

        class CaptureMCEClient:
            def __init__(self, config=None, kg_provider=None):
                captured["config"] = config

        with (
            patch("mce.client.worker.WorkerConfig", return_value=cfg),
            patch("mce.client.worker.MCEClient", CaptureMCEClient),
        ):
            MCEWorkerService()

        assert captured["config"].engine_max_workers == 8
        assert captured["config"].engine_strategy == "process"


# ---------------------------------------------------------------------------
# MCEWorkerService — process_session
# ---------------------------------------------------------------------------


class TestProcessSession:
    def test_returns_legacy_dicts(self):
        svc = _make_svc()
        r1, r2 = _make_result("AnswerRelevancy"), _make_result("GoalSuccessRate")
        svc._compute_session_results = MagicMock(return_value=([r1, r2], []))

        out = svc.process_session("sess-1")
        assert len(out) == 2
        assert out[0]["metric_id"] == "AnswerRelevancy"

    def test_no_save_when_no_results(self):
        svc = _make_svc()
        mock_kg = MagicMock()
        svc._client._get_kg_provider.return_value = mock_kg
        svc._compute_session_results = MagicMock(return_value=([], []))

        svc.process_session("sess-empty")
        mock_kg.save_metrics.assert_not_called()


# ---------------------------------------------------------------------------
# MCEWorkerService — process_batch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    def _make_svc_with_batch_engine(self, batch_results: dict):
        """Return a service whose restricted engine stubs compute_sessions_batch."""
        svc = _make_svc()
        mock_engine = MagicMock()
        mock_engine.compute_sessions_batch.return_value = batch_results
        svc._restricted_engine = mock_engine  # bypass _get_restricted_engine()
        return svc, mock_engine

    def test_returns_per_session_dict(self):
        svc, _ = self._make_svc_with_batch_engine(
            {
                "s1": [_make_result("AnswerRelevancy", resource_id="s1")],
                "s2": [_make_result("AnswerRelevancy", resource_id="s2")],
            }
        )
        out = svc.process_batch(["s1", "s2"])
        assert set(out.keys()) == {"s1", "s2"}

    def test_single_compute_sessions_batch_call(self):
        """process_batch() must delegate to compute_sessions_batch(), not loop."""
        svc, mock_engine = self._make_svc_with_batch_engine(
            {
                "s1": [_make_result("AnswerRelevancy", resource_id="s1")],
                "s2": [_make_result("Duration", resource_id="s2")],
            }
        )
        svc.process_batch(["s1", "s2"])
        mock_engine.compute_sessions_batch.assert_called_once_with(["s1", "s2"])
        mock_engine.compute_session.assert_not_called()

    def test_empty_batch_returns_empty_dict(self):
        svc, mock_engine = self._make_svc_with_batch_engine({})
        out = svc.process_batch([])
        assert out == {}
        mock_engine.compute_sessions_batch.assert_not_called()


# ---------------------------------------------------------------------------
# MCEWorkerService — _compute_session_results (two-pass)
# ---------------------------------------------------------------------------


class TestComputeSessionResults:
    def _make_svc_with_engine(self, session_results, element_results):
        """Build a service with a single mock engine returning combined results.

        _compute_session_results makes one recursive call; the engine returns
        all results and _compute_session_results filters by configured IDs.
        """
        svc = _make_svc()
        mock_kg = MagicMock()
        mock_engine = MagicMock()
        # Single call — return session + element results combined
        mock_engine.compute_session.return_value = session_results + element_results
        mock_engine.set_data_provider = MagicMock()
        svc._client._get_kg_provider.return_value = mock_kg
        svc._restricted_engine = mock_engine  # bypass lazy cache
        return svc

    def test_session_pass_filters_to_session_metrics(self):
        svc = self._make_svc_with_engine(
            session_results=[_make_result("AnswerRelevancy"), _make_result("Unknown")],
            element_results=[],
        )

        results, failed = svc._compute_session_results("sess-1")
        ids = {r.metric_id for r in results + failed}
        assert "AnswerRelevancy" in ids
        assert "Unknown" not in ids

    def test_element_pass_filters_to_element_metrics(self):
        svc = self._make_svc_with_engine(
            session_results=[_make_result("AnswerRelevancy")],
            element_results=[_make_result("Duration"), _make_result("XYZ")],
        )
        results, failed = svc._compute_session_results("sess-1")
        ids = {r.metric_id for r in results + failed}
        assert "Duration" in ids
        assert "XYZ" not in ids

    def test_both_passes_combined(self):
        svc = self._make_svc_with_engine(
            session_results=[_make_result("AnswerRelevancy")],
            element_results=[_make_result("Duration"), _make_result("ToolError")],
        )
        results, failed = svc._compute_session_results("sess-1")
        ids = {r.metric_id for r in results + failed}
        assert ids == {"AnswerRelevancy", "Duration", "ToolError"}

    def test_single_engine_call_made(self):
        """Only one compute_session call is made (recursive=True)."""
        svc = _make_svc(
            {
                "engine": {"max_workers": 2, "execution_strategy": "thread"},
                "metrics": {"Session": ["AnswerRelevancy"]},
            }
        )
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = [_make_result("AnswerRelevancy")]
        svc._restricted_engine = mock_engine
        svc._client._get_kg_provider.return_value = MagicMock()

        svc._compute_session_results("sess-1")
        assert mock_engine.compute_session.call_count == 1
        _, kwargs = mock_engine.compute_session.call_args
        assert kwargs.get("recursive", False) is True

    @patch("mce.client.worker.logger")
    def test_logs_exception_when_engine_compute_session_raises(self, mock_logger):
        svc = _make_svc(
            {
                "engine": {"max_workers": 2, "execution_strategy": "thread"},
                "metrics": {"Session": ["AnswerRelevancy"]},
            }
        )
        mock_engine = MagicMock()
        mock_engine.compute_session.side_effect = RuntimeError("boom")
        svc._restricted_engine = mock_engine

        with pytest.raises(RuntimeError, match="boom"):
            svc._compute_session_results("sess-1")

        mock_logger.exception.assert_called_once()


# ---------------------------------------------------------------------------
# YAML-driven scope routing
# ---------------------------------------------------------------------------
# These tests validate that the declarative YAML config drives both:
#   (a) per-metric target_types in the restricted engine (scope routing)
#   (b) result counts returned/persisted per scope (write validation)
#
# Config under test:
#   Session:  [GoalSuccessRate, AnswerRelevancy]   M=2
#   LLMCall:  [Duration]                           N=1
#   ToolCall: [ToolError]                          P=1
# ---------------------------------------------------------------------------

_SCOPED_YAML = {
    "engine": {"max_workers": 1, "execution_strategy": "thread"},
    "metrics": {
        "Session": ["GoalSuccessRate", "AnswerRelevancy"],
        "LLMCall": ["Duration"],
        "ToolCall": ["ToolError"],
    },
}


def _make_scoped_svc(tmp_path):
    from mce.client.worker import MCEWorkerService

    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump(_SCOPED_YAML))
    with patch("mce.client.worker.MCEClient", return_value=MagicMock()):
        svc = MCEWorkerService(cfg_file)
    return svc


def _real_result(metric_id: str, resource_id: str = "x") -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        resource_id=resource_id,
        provider="test",
        value=0.5,
    )


class TestYamlDrivenScopeRouting:
    """_get_restricted_engine must restrict each metric's target_types to the
    exact ontology URI declared in the YAML config."""

    def _fake_metric(self, metric_id: str):
        """SimpleNamespace so copy.copy() produces a real distinct object."""
        from types import SimpleNamespace

        meta = SimpleNamespace(
            target_types={"mas:ExecutionElement"},
            attachment_point=None,
        )
        return SimpleNamespace(metric_id=metric_id, metadata=meta)

    def _run_restricted_engine(self, svc, metric_ids: list[str]) -> dict[str, set]:
        """Build the restricted engine with fake discovered metrics and return
        a dict of metric_id → target_types as registered in the engine."""
        fake_metrics = [self._fake_metric(mid) for mid in metric_ids]
        registered: dict[str, set] = {}

        class _CapturingEngine:
            def __init__(self, **kw):
                pass

            def register_metric(self, m):
                registered[m.metric_id] = set(m.metadata.target_types)

            def set_data_provider(self, p):
                pass

            def set_cache_manager(self, cm):
                pass

        svc._restricted_engine = None  # reset lazy cache
        with (
            patch(
                "mce.core.registry.discovery.discover_all_metrics",
                return_value=fake_metrics,
            ),
            patch("mce.core.registry.discovery.ensure_target_types"),
            patch("mce.engine.engine.MetricEngine", _CapturingEngine),
        ):
            svc._get_restricted_engine()

        return registered

    def test_session_metrics_restricted_to_session_uri(self, tmp_path):
        svc = _make_scoped_svc(tmp_path)
        registered = self._run_restricted_engine(
            svc, ["GoalSuccessRate", "AnswerRelevancy", "Duration", "ToolError"]
        )
        assert registered["GoalSuccessRate"] == {"mas:Session"}
        assert registered["AnswerRelevancy"] == {"mas:Session"}

    def test_llm_metric_restricted_to_llmcall_uri(self, tmp_path):
        svc = _make_scoped_svc(tmp_path)
        registered = self._run_restricted_engine(
            svc, ["GoalSuccessRate", "AnswerRelevancy", "Duration", "ToolError"]
        )
        assert registered["Duration"] == {"mas:LLMCall"}

    def test_tool_metric_restricted_to_toolcall_uri(self, tmp_path):
        svc = _make_scoped_svc(tmp_path)
        registered = self._run_restricted_engine(
            svc, ["GoalSuccessRate", "AnswerRelevancy", "Duration", "ToolError"]
        )
        assert registered["ToolError"] == {"mas:ToolCall"}

    def test_all_yaml_metrics_are_registered(self, tmp_path):
        """Every metric declared in the YAML appears in the engine."""
        svc = _make_scoped_svc(tmp_path)
        registered = self._run_restricted_engine(
            svc, ["GoalSuccessRate", "AnswerRelevancy", "Duration", "ToolError"]
        )
        assert set(registered) == {
            "GoalSuccessRate",
            "AnswerRelevancy",
            "Duration",
            "ToolError",
        }

    def test_metric_absent_from_yaml_not_registered(self, tmp_path):
        """A metric discovered globally but absent from YAML is never registered."""
        svc = _make_scoped_svc(tmp_path)
        # Cost and TokenCount are NOT in _SCOPED_YAML
        registered = self._run_restricted_engine(
            svc, ["GoalSuccessRate", "Duration", "Cost", "TokenCount"]
        )
        assert "Cost" not in registered
        assert "TokenCount" not in registered
        assert "GoalSuccessRate" in registered
        assert "Duration" in registered


class TestYamlDrivenWriteCounts:
    """process_session must return/persist exactly the results that match the
    YAML declarations — correct counts per scope, no extras.

    Scenario: M=2 session metrics, N=1 LLM metric × n_llm=3 calls,
              P=1 tool metric × p_tool=2 calls  →  2+3+2 = 7 total results.
    """

    def _make_engine_results(self, n_llm: int = 3, p_tool: int = 2) -> list:
        return (
            [_real_result("GoalSuccessRate", "session-1")]
            + [_real_result("AnswerRelevancy", "session-1")]
            + [_real_result("Duration", f"llm-{i}") for i in range(n_llm)]
            + [_real_result("ToolError", f"tool-{i}") for i in range(p_tool)]
        )

    def test_total_result_count_matches_yaml_times_spans(self, tmp_path):
        """M + N*n_llm + P*p_tool = 2 + 1*3 + 1*2 = 7."""
        svc = _make_scoped_svc(tmp_path)
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = self._make_engine_results(
            n_llm=3, p_tool=2
        )
        svc._restricted_engine = mock_engine

        results, failed = svc._compute_session_results("session-1")
        assert len(results + failed) == 7

    def test_session_metrics_count_equals_M(self, tmp_path):
        svc = _make_scoped_svc(tmp_path)
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = self._make_engine_results()
        svc._restricted_engine = mock_engine

        results, _ = svc._compute_session_results("session-1")
        session_results = [
            r for r in results if r.metric_id in {"GoalSuccessRate", "AnswerRelevancy"}
        ]
        assert len(session_results) == 2  # M=2

    def test_llm_metric_count_equals_N_times_n_llm(self, tmp_path):
        svc = _make_scoped_svc(tmp_path)
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = self._make_engine_results(n_llm=4)
        svc._restricted_engine = mock_engine

        results, _ = svc._compute_session_results("session-1")
        llm_results = [r for r in results if r.metric_id == "Duration"]
        assert len(llm_results) == 4  # N=1 × n_llm=4

    def test_tool_metric_count_equals_P_times_p_tool(self, tmp_path):
        svc = _make_scoped_svc(tmp_path)
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = self._make_engine_results(p_tool=5)
        svc._restricted_engine = mock_engine

        results, _ = svc._compute_session_results("session-1")
        tool_results = [r for r in results if r.metric_id == "ToolError"]
        assert len(tool_results) == 5  # P=1 × p_tool=5

    def test_results_for_undeclared_metrics_are_dropped(self, tmp_path):
        """Engine output containing metric_ids not in YAML is silently discarded."""
        svc = _make_scoped_svc(tmp_path)
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = [
            _real_result("GoalSuccessRate", "session-1"),
            _real_result("Duration", "llm-0"),
            _real_result("Cost", "session-1"),  # not in YAML
            _real_result("TokenCount", "llm-0"),  # not in YAML
        ]
        svc._restricted_engine = mock_engine

        results, failed = svc._compute_session_results("session-1")
        ids = {r.metric_id for r in results + failed}
        assert ids == {"GoalSuccessRate", "Duration"}
        assert "Cost" not in ids
        assert "TokenCount" not in ids

    def test_process_session_serialises_all_scope_results(self, tmp_path):
        """process_session returns one dict per result across all scopes."""
        svc = _make_scoped_svc(tmp_path)
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = self._make_engine_results(
            n_llm=2, p_tool=1
        )
        svc._restricted_engine = mock_engine

        out = svc.process_session("session-1")
        # M=2 + N*2 + P*1 = 5
        assert len(out) == 5
        assert all(isinstance(d, dict) for d in out)
        returned_metric_names = {d["metricName"] for d in out}
        assert returned_metric_names == {
            "GoalSuccessRate",
            "AnswerRelevancy",
            "Duration",
            "ToolError",
        }


# ---------------------------------------------------------------------------
# KG write path — cache_manager wiring
# ---------------------------------------------------------------------------


class TestKGWritePath:
    """Verify that _get_restricted_engine wires a KnowledgeGraphCache so that
    computed results are flushed to Neo4j via save_metrics().

    The chain is:
        engine.compute_session()
            → KnowledgeGraphCache.store(result)      (per result)
            → KnowledgeGraphCache.flush()             (end of batch)
            → kg_provider.save_metrics(buffer)        ← this is what we assert
    """

    def _build_engine_and_capture(self, tmp_path):
        """Build _get_restricted_engine with real KnowledgeGraphCache and
        return (svc, mock_kg_provider, captured set_cache_manager call)."""
        from mce.client.worker import MCEWorkerService

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(_SCOPED_YAML))

        mock_kg = MagicMock()
        mock_client = MagicMock()
        mock_client._get_kg_provider.return_value = mock_kg

        with patch("mce.client.worker.MCEClient", return_value=mock_client):
            svc = MCEWorkerService(cfg_file)

        svc._client = mock_client
        return svc, mock_kg

    def test_engine_has_cache_manager_set(self, tmp_path):
        """_get_restricted_engine must call engine.set_cache_manager()."""
        svc, mock_kg = self._build_engine_and_capture(tmp_path)

        captured_cache_manager = {}

        class _CapturingEngine:
            def __init__(self, **kw):
                pass

            def register_metric(self, m):
                pass

            def set_data_provider(self, p):
                pass

            def set_cache_manager(self, cm):
                captured_cache_manager["cm"] = cm

        with (
            patch("mce.core.registry.discovery.discover_all_metrics", return_value=[]),
            patch("mce.core.registry.discovery.ensure_target_types"),
            patch("mce.engine.engine.MetricEngine", _CapturingEngine),
        ):
            svc._get_restricted_engine()

        assert "cm" in captured_cache_manager, "set_cache_manager() was never called"

    def test_cache_manager_uses_kg_provider(self, tmp_path):
        """KnowledgeGraphCache inside the cache_manager must wrap the KG provider."""
        from mce.engine.caching import KnowledgeGraphCache

        svc, mock_kg = self._build_engine_and_capture(tmp_path)

        captured = {}

        class _CapturingEngine:
            def __init__(self, **kw):
                pass

            def register_metric(self, m):
                pass

            def set_data_provider(self, p):
                pass

            def set_cache_manager(self, cm):
                captured["cm"] = cm

        with (
            patch("mce.core.registry.discovery.discover_all_metrics", return_value=[]),
            patch("mce.core.registry.discovery.ensure_target_types"),
            patch("mce.engine.engine.MetricEngine", _CapturingEngine),
        ):
            svc._get_restricted_engine()

        cm = captured["cm"]
        kg_backends = [b for b in cm.backends if isinstance(b, KnowledgeGraphCache)]
        assert len(kg_backends) == 1
        assert kg_backends[0].provider is mock_kg

    def test_flush_triggers_save_metrics_with_correct_results(self, tmp_path):
        """End-to-end: after compute_session, flush() calls save_metrics() on
        the KG provider with exactly the results declared in YAML.

        Engine and cache_manager are real objects; only the KG provider and
        metric discovery are mocked.

        Note: flush() clears the buffer in-place after calling save_metrics(),
        so we capture the results via a side_effect rather than inspecting
        call_args after the fact.
        """
        from mce.engine.caching import CacheManager, KnowledgeGraphCache

        saved_on_flush: list = []
        mock_kg = MagicMock()
        mock_kg.save_metrics.side_effect = lambda buf: saved_on_flush.extend(list(buf))

        backend = KnowledgeGraphCache(mock_kg)
        cm = CacheManager([backend])

        engine_results = [
            _real_result("GoalSuccessRate", "session-1"),
            _real_result("AnswerRelevancy", "session-1"),
            _real_result("Duration", "llm-0"),
            _real_result("ToolError", "tool-0"),
        ]

        for r in engine_results:
            cm.store(r)
        cm.flush()

        assert mock_kg.save_metrics.call_count == 1
        assert {r.metric_id for r in saved_on_flush} == {
            "GoalSuccessRate",
            "AnswerRelevancy",
            "Duration",
            "ToolError",
        }

    def test_cache_write_disabled_skips_save_metrics(self, tmp_path):
        """When cache_write=False in YAML, save_metrics() must not be called."""
        from mce.client.worker import MCEWorkerService
        from mce.engine.caching import KnowledgeGraphCache

        d = {**_SCOPED_YAML, "cache": {"path": None, "read": True, "write": False}}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))

        mock_kg = MagicMock()
        mock_client = MagicMock()
        mock_client._get_kg_provider.return_value = mock_kg

        with patch("mce.client.worker.MCEClient", return_value=mock_client):
            svc = MCEWorkerService(cfg_file)
        svc._client = mock_client

        captured = {}

        class _CapturingEngine:
            def __init__(self, **kw):
                pass

            def register_metric(self, m):
                pass

            def set_data_provider(self, p):
                pass

            def set_cache_manager(self, cm):
                captured["cm"] = cm

        with (
            patch("mce.core.registry.discovery.discover_all_metrics", return_value=[]),
            patch("mce.core.registry.discovery.ensure_target_types"),
            patch("mce.engine.engine.MetricEngine", _CapturingEngine),
        ):
            svc._get_restricted_engine()

        cm = captured["cm"]
        kg_backend = next(b for b in cm.backends if isinstance(b, KnowledgeGraphCache))
        # write_enabled=False → flush() is a no-op
        assert kg_backend.write_enabled is False
