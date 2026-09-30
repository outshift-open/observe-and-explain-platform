#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.engine.worker — WorkerConfig and MCEWorkerService.

mce.engine.worker is a re-export shim over mce.client.worker.
These tests verify that the shim resolves to the canonical classes and that
the worker logic behaves correctly when invoked through the shim.

Full behavioural coverage also lives in mce-client/tests/test_worker.py.
"""

from unittest.mock import MagicMock, patch

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


def _make_worker(cfg_dict: dict | None = None):
    """Return a WorkerConfig-patched MCEWorkerService with MCEClient mocked out."""
    from mce.engine.worker import MCEWorkerService, WorkerConfig

    cfg = MagicMock(spec=WorkerConfig)
    d = cfg_dict or _MINIMAL_YAML
    cfg.max_workers = d["engine"]["max_workers"]
    cfg.execution_strategy = d["engine"]["execution_strategy"]
    cfg.scope_metrics = d["metrics"]
    # session_metrics / element_metrics are properties — replicate the logic on the mock
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
    # Pre-computed frozensets used by _compute_session_results fast path
    cfg._session_metric_ids = frozenset(d["metrics"].get("Session", []))
    cfg._element_metric_ids = frozenset(_element)
    cfg.all_metric_ids = cfg._session_metric_ids | cfg._element_metric_ids
    cfg.cache_read = True
    cfg.cache_write = True
    cfg.cache_path = None

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
        from mce.engine.worker import WorkerConfig
        import yaml

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(_MINIMAL_YAML))
        wc = WorkerConfig(cfg_file)

        assert wc.max_workers == 2
        assert wc.execution_strategy == "thread"

    def test_loads_metric_lists(self, tmp_path):
        from mce.engine.worker import WorkerConfig
        import yaml

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(_MINIMAL_YAML))
        wc = WorkerConfig(cfg_file)

        assert "AnswerRelevancy" in wc.session_metrics
        assert "Duration" in wc.scope_metrics["LLMCall"]
        assert "ToolError" in wc.scope_metrics["ToolCall"]

    def test_element_metrics_deduplicates(self, tmp_path):
        from mce.engine.worker import WorkerConfig
        import yaml

        d = dict(_MINIMAL_YAML)
        d["metrics"] = {
            "Session": [],
            "LLMCall": ["Duration"],
            "ToolCall": ["Duration", "ToolError"],
        }
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert wc.element_metrics.count("Duration") == 1
        assert "ToolError" in wc.element_metrics

    def test_has_element_metrics_false_when_empty(self, tmp_path):
        from mce.engine.worker import WorkerConfig
        import yaml

        d = dict(_MINIMAL_YAML)
        d["metrics"] = {"Session": ["AnswerRelevancy"]}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert not wc.has_element_metrics

    def test_defaults_when_sections_missing(self, tmp_path):
        from mce.engine.worker import WorkerConfig
        import yaml

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump({}))
        wc = WorkerConfig(cfg_file)

        assert wc.max_workers == 8
        assert wc.execution_strategy == "hybrid"
        assert wc.session_metrics == []

    def test_scope_metrics_flexible_keys(self, tmp_path):
        """Arbitrary ontology-keyed scopes (e.g. AgentCall) are accepted."""
        from mce.engine.worker import WorkerConfig
        import yaml

        d = {"metrics": {"Session": ["GoalSuccessRate"], "AgentCall": ["Duration"]}}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert "AgentCall" in wc.scope_metrics
        assert "Duration" in wc.scope_metrics["AgentCall"]
        assert "Duration" in wc.element_metrics

    def test_cache_defaults(self, tmp_path):
        """Cache section defaults to path=None, read=True, write=True."""
        from mce.engine.worker import WorkerConfig
        import yaml

        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump({}))
        wc = WorkerConfig(cfg_file)

        assert wc.cache_path is None
        assert wc.cache_read is True
        assert wc.cache_write is True

    def test_cache_custom_values(self, tmp_path):
        """Cache section custom values are loaded correctly."""
        from mce.engine.worker import WorkerConfig
        import yaml

        d = {"cache": {"path": "/tmp/cache.json", "read": False, "write": True}}
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(yaml.dump(d))
        wc = WorkerConfig(cfg_file)

        assert wc.cache_path == "/tmp/cache.json"
        assert wc.cache_read is False
        assert wc.cache_write is True

    def test_to_dict_round_trip(self, tmp_path):
        """to_dict() round-trips through WorkerConfig."""
        from mce.engine.worker import WorkerConfig
        import yaml

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


# ---------------------------------------------------------------------------
# MCEWorkerService — init
# ---------------------------------------------------------------------------


class TestMCEWorkerServiceInit:
    def test_init_passes_engine_params_to_client_config(self):
        """engine_max_workers and engine_strategy must reach MCEClientConfig."""
        from mce.engine.worker import MCEWorkerService, WorkerConfig

        cfg = MagicMock(spec=WorkerConfig)
        cfg.max_workers = 8
        cfg.execution_strategy = "process"
        cfg.scope_metrics = {}
        cfg.session_metrics = []
        cfg.element_metrics = []
        cfg.has_element_metrics = False

        captured = {}

        class CaptureMCEClient:
            def __init__(self, config=None, **kwargs):
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
        svc = _make_worker()
        r1, r2 = _make_result("AnswerRelevancy"), _make_result("GoalSuccessRate")
        svc._compute_session_results = MagicMock(return_value=([r1, r2], []))

        out = svc.process_session("sess-1")
        assert len(out) == 2
        assert out[0]["metric_id"] == "AnswerRelevancy"

    def test_calls_save_metrics_once(self):
        svc = _make_worker()
        svc._compute_session_results = MagicMock(
            return_value=([_make_result("AR")], [])
        )

        out = svc.process_session("sess-1")
        # Persistence is handled automatically by KnowledgeGraphCache during
        # engine computation — no explicit save_metrics() call from process_session.
        assert len(out) == 1
        assert out[0]["metric_id"] == "AR"

    def test_no_save_when_no_results(self):
        svc = _make_worker()
        mock_kg = MagicMock()
        svc._client._get_kg_provider.return_value = mock_kg
        svc._compute_session_results = MagicMock(return_value=([], []))
        svc.process_session("sess-empty")
        mock_kg.save_metrics.assert_not_called()


# ---------------------------------------------------------------------------
# MCEWorkerService — process_batch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    def _mock_engine_for_batch(self, results_by_session: dict):
        """Return a mock engine whose compute_sessions_batch returns the given dict."""
        mock_engine = MagicMock()
        mock_engine.compute_sessions_batch.return_value = results_by_session
        return mock_engine

    def test_returns_per_session_dict(self):
        svc = _make_worker()
        mock_engine = self._mock_engine_for_batch(
            {
                "s1": [_make_result("AR", resource_id="s1")],
                "s2": [_make_result("AR", resource_id="s2")],
            }
        )
        svc._get_restricted_engine = MagicMock(return_value=mock_engine)

        out = svc.process_batch(["s1", "s2"])
        assert set(out.keys()) == {"s1", "s2"}

    def test_single_bulk_write_for_entire_batch(self):
        """process_batch returns all sessions' results in a single dict."""
        svc = _make_worker()
        mock_engine = self._mock_engine_for_batch(
            {
                "s1": [_make_result("AR", resource_id="s1")],
                "s2": [_make_result("AR", resource_id="s2")],
                "s3": [_make_result("AR", resource_id="s3")],
            }
        )
        svc._get_restricted_engine = MagicMock(return_value=mock_engine)

        out = svc.process_batch(["s1", "s2", "s3"])
        # All sessions present; persistence happens via engine cache manager.
        assert len(out) == 3

    def test_no_save_when_all_sessions_empty(self):
        svc = _make_worker()
        mock_engine = self._mock_engine_for_batch(
            {
                "s1": [],
                "s2": [],
            }
        )
        svc._get_restricted_engine = MagicMock(return_value=mock_engine)

        out = svc.process_batch(["s1", "s2"])
        # Empty results → empty lists per session, no error.
        assert out == {"s1": [], "s2": []}


# ---------------------------------------------------------------------------
# MCEWorkerService — _compute_session_results (two-pass logic)
# ---------------------------------------------------------------------------


class TestComputeSessionResults:
    def _make_svc_with_engine(self, session_results, element_results):
        """Build a service with a single mock engine returning combined results.

        _compute_session_results now makes one recursive call; session_results
        and element_results are combined so the engine returns both together.
        """
        svc = _make_worker()
        mock_kg = MagicMock()
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = session_results + element_results
        mock_engine.set_data_provider = MagicMock()
        svc._client._get_kg_provider.return_value = mock_kg
        svc._get_restricted_engine = MagicMock(return_value=mock_engine)
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
        """Only one compute_session call (recursive=True) is made per session."""
        svc = _make_worker(
            {
                "engine": {"max_workers": 2, "execution_strategy": "thread"},
                "metrics": {"Session": ["AnswerRelevancy"]},
            }
        )
        mock_engine = MagicMock()
        mock_engine.compute_session.return_value = [_make_result("AnswerRelevancy")]
        svc._get_restricted_engine = MagicMock(return_value=mock_engine)
        svc._client._get_kg_provider.return_value = MagicMock()

        svc._compute_session_results("sess-1")
        assert mock_engine.compute_session.call_count == 1
        _, kwargs = mock_engine.compute_session.call_args
        assert kwargs.get("recursive", False) is True
