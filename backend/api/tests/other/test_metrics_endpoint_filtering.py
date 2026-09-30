#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
import logging

from oxp.api import app
from oxp.api.api_v1.endpoints import metrics as metrics_endpoint
from oxp.interfaces.models import MetricResult
from oxp.models.otel_traces import MetricCatalogItem
from oxp.providers.kg_query_runner import KGQueryExecutionError
from fastapi import HTTPException
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)


class _DummyProvider:
    def get_metrics(self, session_id: str, hops: int = 2):
        return []

    def save_metrics(self, results):
        return None


def test_session_metrics_filters_single_requested_metric(monkeypatch) -> None:
    session_id = "session-123"

    def fake_compute(
        target_session_id: str, metric_ids: list[str], recursive: bool = False
    ):
        assert target_session_id == session_id
        assert metric_ids == ["WorkflowEfficiency"]
        return [
            MetricResult(
                metric_id="WorkflowEfficiency",
                resource_id=target_session_id,
                provider="Native",
                value=0.81,
            ),
            MetricResult(
                metric_id="Cost",
                resource_id=target_session_id,
                provider="Native",
                value=12.5,
            ),
        ]

    monkeypatch.setattr(metrics_endpoint, "_provider", _DummyProvider())
    monkeypatch.setattr(metrics_endpoint, "_compute_session_metrics", fake_compute)

    client = TestClient(app)
    response = client.get(
        f"/api/v1/metrics/sessions/{session_id}",
        params=[("metric_names", "WorkflowEfficiency"), ("use_cache", "false")],
    )

    assert response.status_code == 200
    assert [metric["name"] for metric in response.json()["metrics"]] == [
        "WorkflowEfficiency"
    ]


def test_session_metrics_accepts_comma_separated_metric_names(monkeypatch) -> None:
    session_id = "session-456"

    def fake_compute(
        target_session_id: str, metric_ids: list[str], recursive: bool = False
    ):
        assert target_session_id == session_id
        assert metric_ids == ["WorkflowEfficiency", "Cost"]
        return [
            MetricResult(
                metric_id="WorkflowEfficiency",
                resource_id=target_session_id,
                provider="Native",
                value=0.81,
            ),
            MetricResult(
                metric_id="Cost",
                resource_id=target_session_id,
                provider="Native",
                value=12.5,
            ),
        ]

    monkeypatch.setattr(metrics_endpoint, "_provider", _DummyProvider())
    monkeypatch.setattr(metrics_endpoint, "_compute_session_metrics", fake_compute)

    client = TestClient(app)
    response = client.get(
        f"/api/v1/metrics/sessions/{session_id}",
        params={"metric_names": "WorkflowEfficiency, Cost", "use_cache": "false"},
    )

    assert response.status_code == 200
    assert [metric["name"] for metric in response.json()["metrics"]] == [
        "WorkflowEfficiency",
        "Cost",
    ]


def test_compute_session_metrics_raises_503_when_kg_query_fails(monkeypatch) -> None:
    class _FailingEngine:
        def compute_session(self, session_id: str, recursive: bool = False):
            raise KGQueryExecutionError(
                "fetch_session",
                RuntimeError("neo4j down"),
                RuntimeError("neo4j down"),
            )

    monkeypatch.setattr(
        metrics_endpoint, "_build_metric_engine", lambda metric_ids: _FailingEngine()
    )

    try:
        metrics_endpoint._compute_session_metrics(
            "session-neo4j-down", ["Cost"], recursive=False
        )
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "knowledge graph unavailable" in str(exc.detail).lower()
    else:
        raise AssertionError("Expected HTTPException")


def test_session_metrics_returns_503_when_compute_layer_raises_http_exception(
    monkeypatch,
) -> None:
    session_id = "session-neo4j-down"

    def fake_compute(
        target_session_id: str, metric_ids: list[str], recursive: bool = False
    ):
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph unavailable while computing metrics: neo4j down",
        )

    monkeypatch.setattr(metrics_endpoint, "_provider", _DummyProvider())
    monkeypatch.setattr(metrics_endpoint, "_compute_session_metrics", fake_compute)

    client = TestClient(app)
    response = client.get(
        f"/api/v1/metrics/sessions/{session_id}",
        params={"metric_names": "Cost", "use_cache": "false"},
    )

    assert response.status_code == 503
    assert "neo4j" in response.json()["detail"].lower()


def test_build_metric_engine_configures_llm_and_clones_runtime_wrappers(
    monkeypatch,
) -> None:
    from mce.core.metadata import MetricLayer, MetricMetadata, MetricNature, MetricScope
    from mce.core.metric import Metric
    from mce.engine.llm import LLMService

    class _FakeExternalMetric(Metric):
        def __init__(self) -> None:
            self.metadata = MetricMetadata(
                name="Coherence",
                description="fake external metric",
                layer=MetricLayer.GOVERNANCE,
                nature=MetricNature.STOCHASTIC,
                scope=MetricScope.EXECUTION_ELEMENT,
                ontology_class="Coherence",
                attachment_point="mas:ExecutionElement",
                provider="DeepEval",
            )
            self._model = None

        def init_with_model(self, model):
            self._model = model

        def compute(self, resource_id: str, context: dict):
            raise NotImplementedError

    wrapper = _FakeExternalMetric()

    captured: dict[str, object] = {}

    def fake_configure(**kwargs):
        captured.update(kwargs)

    monkeypatch.setenv("MCE_LLM_MODEL", "azure/gpt-4o-mini")
    monkeypatch.setenv("MCE_LLM_MODE", "live")
    monkeypatch.setattr(metrics_endpoint, "_get_neo4j_graph_provider", lambda: object())
    monkeypatch.setattr("mce.core.registry.get_default_metrics", lambda: [wrapper])
    monkeypatch.setattr(LLMService, "configure", staticmethod(fake_configure))

    engine = metrics_endpoint._build_metric_engine(["Coherence"])
    registered = engine._by_id["Coherence"]

    assert captured["model"] == "azure/gpt-4o-mini"
    assert captured["mode"] == "live"
    assert registered is not wrapper
    assert getattr(registered, "_model", None) == "azure/gpt-4o-mini"
    assert getattr(wrapper, "_model", None) is None


def test_build_metric_engine_uses_configured_max_workers(monkeypatch) -> None:
    class _FakeEngine:
        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.provider = None
            self._by_id = {}

        def set_data_provider(self, provider):
            self.provider = provider

        def register_metric(self, metric):
            self._by_id[metric.metric_id] = metric

    class _FakeMetric:
        metric_id = "WorkflowEfficiency"

    monkeypatch.setenv("MCE_ENGINE_MAX_WORKERS", "11")
    monkeypatch.setattr(metrics_endpoint, "_get_neo4j_graph_provider", lambda: object())
    monkeypatch.setattr(
        metrics_endpoint, "_configure_llm_runtime", lambda: "azure/gpt-4o-mini"
    )
    monkeypatch.setattr(
        metrics_endpoint, "_prepare_metric_for_runtime", lambda metric, _: metric
    )
    monkeypatch.setattr("mce.engine.engine.MetricEngine", _FakeEngine)
    monkeypatch.setattr(
        "mce.core.registry.get_default_metrics", lambda: [_FakeMetric()]
    )

    engine = metrics_endpoint._build_metric_engine(["WorkflowEfficiency"])

    assert engine.max_workers == 11


def test_build_metric_engine_falls_back_to_default_max_workers_on_invalid_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MCE_ENGINE_MAX_WORKERS", "invalid")

    assert metrics_endpoint._get_configured_engine_max_workers() == 8


def test_get_metrics_catalog_returns_total_and_metrics(monkeypatch) -> None:
    """Test that get_metrics_catalog returns the correct response structure with total count."""
    expected_items = [
        MetricCatalogItem(
            metric_id="Groundedness",
            id="Groundedness",
            name="Groundedness",
            provider="Native",
            scope="session",
            target_types=["mas:Session"],
            description="Groundedness metric",
        ),
        MetricCatalogItem(
            metric_id="Cost",
            id="Cost",
            name="Cost",
            provider="Native",
            scope="session",
            target_types=["mas:Session"],
            description="Cost metric",
        ),
    ]

    monkeypatch.setattr(metrics_endpoint, "_build_catalog", lambda: expected_items)

    # response = metrics_endpoint.get_metrics_catalog()
    client = TestClient(app)
    response = client.get("/api/v1/metrics/catalog", params={})

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── LIB metrics_endpoint.get_metrics_catalog() ──")
    logger.info(json.dumps(body, indent=2, default=str))

    assert body["total"] == 2
    assert body["metrics"] == [item.model_dump() for item in expected_items]


def test_metrics_info_returns_detail_for_known_metric_id(monkeypatch) -> None:
    """GET /metrics/info?metric_id=Groundedness returns single-metric detail."""
    catalog_items = [
        MetricCatalogItem(
            metric_id="Groundedness",
            id="Groundedness",
            name="Groundedness Score",
            provider="Native",
            scope="session",
            target_types=["mas:Session"],
            description="Measures how grounded the response is.",
        ),
        MetricCatalogItem(
            metric_id="Cost",
            id="Cost",
            name="Cost",
            provider="Native",
            scope="session",
            target_types=["mas:Session"],
            description="Total cost metric",
        ),
    ]

    monkeypatch.setattr(metrics_endpoint, "_build_catalog", lambda: catalog_items)

    client = TestClient(app)
    response = client.get("/api/v1/metrics/info", params={"metric_id": "Groundedness"})

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── LIB metrics_endpoint.get_metrics_info() ──")
    logger.info(json.dumps(body, indent=2, default=str))

    assert body["id"] == "Groundedness"
    assert body["name"] == "Groundedness Score"
    assert body["description"] == "Measures how grounded the response is."
    assert "mas:Session" in body["dimensions"]


def test_metrics_info_returns_404_for_unknown_metric_id(monkeypatch) -> None:
    """GET /metrics/info?metric_id=NonExistent returns HTTP 404."""
    monkeypatch.setattr(metrics_endpoint, "_build_catalog", lambda: [])

    client = TestClient(app)
    response = client.get("/api/v1/metrics/info", params={"metric_id": "NonExistent"})

    assert response.status_code == 404
    assert "NonExistent" in response.json()["detail"]

    body = response.json()

    logger.info("\n── LIB metrics_endpoint.get_metrics_info() ──")
    logger.info(json.dumps(body, indent=2, default=str))
