#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
import logging

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

import fakeredis
from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client.utils import timestamp_to_epoch
from oxp.connectors.clickhouse import ClickHouseConnector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_redis

load_dotenv()

logger = logging.getLogger(__name__)

# ── ClickHouse connector ─────────────────────────────────────────────────────

_connector: ClickHouseConnector | None = None


def _get_connector() -> ClickHouseConnector:
    global _connector  # noqa: PLW0603
    if _connector is None:
        _connector = ClickHouseConnector(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            username=settings.CLICKHOUSE_USERNAME,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
        _connector.connect()
        logger.info(
            "Using ClickHouse connector — %s:%s/%s",
            settings.CLICKHOUSE_HOST,
            settings.CLICKHOUSE_PORT,
            settings.CLICKHOUSE_DATABASE,
        )
    return _connector


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialise the ClickHouse connector once for the module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture()
def ch_connector():
    return _get_connector()


@pytest.fixture()
def client(ch_connector):
    """Return a FastAPI TestClient with the DB dependency overridden to ClickHouse."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_db] = lambda: ch_connector
    app.dependency_overrides[get_redis] = lambda: fake_redis
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)
    reset_client()


class _DummyProvider:
    def get_metrics(self, session_id: str, hops: int = 2):
        return []

    def save_metrics(self, results):
        return None


def test_get_sessions(client) -> None:
    """GET /sessions returns the list of available sessions."""

    response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── HTTP /api/v1/sessions ──")
    logger.info(json.dumps(body, indent=2, default=str))


def test_get_metrics_catalog(client) -> None:
    # response = metrics_endpoint.get_metrics_catalog()
    response = client.get("/api/v1/metrics/catalog", params={})

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── LIB metrics_endpoint.get_metrics_catalog() ──")
    logger.info(json.dumps(body, indent=2, default=str))

    # assert body["total"] == 30


def test_metrics_info(client) -> None:
    response = client.get("/api/v1/metrics/info", params={"metric_id": "Groundedness"})

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── LIB metrics_endpoint.get_metrics_info() ──")
    logger.info(json.dumps(body, indent=2, default=str))

    assert body["id"] == "Groundedness"
    assert body["name"] == "Groundedness"


def test_metrics_info_for_unknown_metric_id(client) -> None:
    """GET /metrics/info?metric_id=NonExistent returns HTTP 404."""

    response = client.get("/api/v1/metrics/info", params={"metric_id": "NonExistent"})

    assert response.status_code == 404
    assert "NonExistent" in response.json()["detail"]

    body = response.json()

    logger.info("\n── LIB metrics_endpoint.get_metrics_info() ──")
    logger.info(json.dumps(body, indent=2, default=str))


def test_get_metrics_timeseries_with_absolute_time(client) -> None:
    START_EPOCH = str(int(timestamp_to_epoch("2026-03-24 00:00:00")))
    END_EPOCH = str(int(timestamp_to_epoch("2026-03-27 10:40:00")))

    response = client.get(
        "/api/v1/metrics/timeseries",
        params={
            "metric_id": "Groundedness",
            "start_time": START_EPOCH,
            "end_time": END_EPOCH,
            "bucket": "day",
        },
    )

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── HTTP /api/v1/metrics/timeseries ──")
    logger.info(json.dumps(body, indent=2, default=str))

    # assert body["metric_id"] == "latency"
    # assert body["bucket_size"] == "day"
    # assert len(body["points"]) == 1
    # assert body["points"][0]["bucket"] == "2023-10-22T00:00:00+00:00"
    # assert body["points"][0]["avg_value"] == 123.4
    # assert body["points"][0]["min_value"] == 100.0
    # assert body["points"][0]["max_value"] == 150.0
    # assert body["points"][0]["n_sessions"] == 3


def test_get_metrics_timeseries_with_relative_time(client) -> None:
    response = client.get(
        "/api/v1/metrics/timeseries",
        params={
            "metric_id": "Groundedness",  # TokenCount Groundedness success_rate
            "duration": "4w",
            "bucket": "hour",
        },
    )

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── HTTP /api/v1/metrics/timeseries (relative) ──")
    logger.info(json.dumps(body, indent=2, default=str))

    # assert body["metric_id"] == "success_rate"
    # assert body["bucket_size"] == "hour"
    # assert "start" in body
    # assert "points" in body
    # assert isinstance(body["points"], list)


def test_get_session_metrics(client) -> None:
    """GET /metrics/sessions/{session_id} returns metrics for a session."""
    # session_id = "8efd73a9-ac4f-4d27-b9fa-918112ba4c14"
    session_id = "55441c35-72f4-4b71-a72d-7d0e582d635a"

    response = client.get(f"/api/v1/metrics/sessions/{session_id}")

    assert response.status_code == 200
    body = response.json()

    logger.info(f"\n── HTTP /api/v1/metrics/sessions/{session_id} ──")
    logger.info(json.dumps(body, indent=2, default=str))

    assert body["session_id"] == session_id
    assert "metrics" in body
    assert isinstance(body["metrics"], list)


def test_get_all_session_metrics(client) -> None:
    """GET /metrics/sessions/{session_id} for all sessions and print a summary."""

    # Get all sessions
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    body = response.json()
    sessions = body.get("sessions", [])

    # Collect metrics summary
    summary = []

    for session in sessions:
        session_id = session["session_id"]
        response = client.get(f"/api/v1/metrics/sessions/{session_id}")

        assert response.status_code == 200
        body = response.json()

        logger.info(f"\n── HTTP /api/v1/metrics/sessions/{session_id} ──")
        logger.info(json.dumps(body, indent=2, default=str))

        # Collect summary data
        num_metrics = len(body.get("metrics", []))
        summary.append({"session_id": session_id, "number_of_metrics": num_metrics})

    # Print summary
    logger.info("\n── Session Metrics Summary ──")
    logger.info("session_id | number_of_metrics")
    logger.info("-" * 50)
    for row in summary:
        logger.info(f"{row['session_id']} | {row['number_of_metrics']}")


def test_post_metrics_compute(client) -> None:
    """POST /metrics/compute computes metrics for the provided session list."""

    # session_id = "359cf98d-9a9c-4f95-b858-60f3d990eebe" # Does not contain any metrics
    session_id = "a6a1aad5-7f9c-4d3c-9d72-e43c6da40112"  # 18 metrics

    # class _DummyResult:
    #     def __init__(self, metric_id: str, value: float, resource_id: str) -> None:
    #         self.metric_id = metric_id
    #         self.value = value
    #         self.resource_id = resource_id
    #         self.error = None
    #         self.reasoning = "computed in test"

    # class _DummyEngine:
    #     def compute_session(self, session_id: str, recursive: bool = False):
    #         return [_DummyResult("complexity_score", 0.75, session_id)]

    # original_build_metric_engine = metrics_endpoint._build_metric_engine
    # metrics_endpoint._build_metric_engine = lambda metric_ids=None: _DummyEngine()

    # try:

    response = client.get(f"/api/v1/metrics/sessions/{session_id}")

    assert response.status_code == 200
    body = response.json()

    logger.info(f"\n── HTTP /api/v1/metrics/sessions/{session_id} ──")
    logger.info(json.dumps(body, indent=2, default=str))

    metric_id = "CallCount"

    response = client.post(
        "/api/v1/metrics/compute",
        json={
            "metric_id": metric_id,
            "session_ids": [session_id],
        },
    )

    assert response.status_code == 200
    body = response.json()

    logger.info("\n── HTTP POST /api/v1/metrics/compute ──")
    logger.info(json.dumps(body, indent=2, default=str))

    assert body["status"] in ["completed", "partial"]
    assert body["total_sessions"] == 1
    assert body["computed"] == 1
    assert body["failed"] == 0
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 1
    assert body["results"][0]["session_id"] == session_id
    assert body["results"][0]["metric_id"] == metric_id
    assert body["results"][0]["error"] in (None, "")

    # finally:
    #     metrics_endpoint._build_metric_engine = original_build_metric_engine
