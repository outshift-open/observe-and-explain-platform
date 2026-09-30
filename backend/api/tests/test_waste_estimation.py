#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Functional tests for waste-estimation API v1 endpoints.

Run with:
    pytest tests/test_waste_estimation.py -v -s
"""

import json
import logging
import os
import sys

import fakeredis
import pytest
from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.connectors.neo4j import Neo4JConnector
from oxp.dependencies import get_neo4j_db, get_redis
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BASE = "/api/v1/waste-estimation"
_connector: Neo4JConnector | None = None


def _get_connector() -> Neo4JConnector:
    """Lazily create a module-level Neo4j connector."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        host = os.environ.get("NEO4J_HOST") or "localhost"
        port = int(os.environ.get("NEO4J_PORT") or "7687")
        username = os.environ.get("NEO4J_USERNAME") or "neo4j"
        password = os.environ.get("NEO4J_PASSWORD") or ""
        database = os.environ.get("NEO4J_DATABASE") or "neo4j"

        logger.info(
            "Using Neo4J connector - %s:%s/%s",
            host,
            port,
            database,
        )
        _connector = Neo4JConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )

        try:
            _connector.connect()
        except Exception as exc:
            pytest.skip(
                "Neo4j connection/authentication failed for tests. "
                f"Set valid NEO4J_* environment variables. Error: {exc}"
            )

        if not _connector.is_connected():
            pytest.skip("Neo4j connector is not connected for integration test")

    return _connector


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialise Neo4j connector once for this module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture()
def neo4j_db():
    """Provide the shared Neo4j connector for tests."""
    return _get_connector()


@pytest.fixture()
def client(neo4j_db):
    """Return a FastAPI TestClient with Neo4j dependency overridden."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_neo4j_db] = lambda: neo4j_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    yield TestClient(app)
    app.dependency_overrides.pop(get_neo4j_db, None)
    app.dependency_overrides.pop(get_redis, None)
    reset_client()


class TestWasteEstimationEndpoints:
    def test_get_waste_estimations(self, client) -> None:
        endpoint = f"{BASE}/waste-estimations"
        result_http = client.get(endpoint, params={"limit": 10})
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s --", endpoint)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_top_wasteful_sessions(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        endpoint = f"{BASE}/{app_name}/top-wasteful-sessions"
        result_http = client.get(
            endpoint,
            params={
                "threshold": 0,
                "limit": 25,
            },
        )
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s --", endpoint)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_top_wasteful_sessions_with_time_range(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        endpoint = f"{BASE}/{app_name}/top-wasteful-sessions"
        result_http = client.get(
            endpoint,
            params={
                "threshold": 0,
                "limit": 25,
                "start_time": 1767285027,
                "end_time": 1782830720,
            },
        )
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s (time range) --", endpoint)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_waste_estimations_semantic_groups(self, client) -> None:
        endpoint = f"{BASE}/waste-estimations-semantic-groups"
        result_http = client.get(endpoint)
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s --", endpoint)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_cost_efficiency_grouped_sessions(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        endpoint = f"{BASE}/{app_name}/cost-efficiency-groupped-sessions"
        result_http = client.get(endpoint)
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s --", endpoint)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_wasted_resources_features_score(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        top_wasteful = client.get(
            f"{BASE}/{app_name}/top-wasteful-sessions",
            params={"threshold": 0, "limit": 1},
        )
        assert top_wasteful.status_code == 200
        top_rows = top_wasteful.json()

        if not top_rows:
            pytest.skip(
                "No waste-estimation sessions available to test feature-score endpoint"
            )

        session_id = top_rows[0].get("sessionId")
        if not session_id:
            pytest.skip("Could not infer sessionId from top-wasteful-sessions response")

        endpoint = f"{BASE}/wasted-resources-features-score"
        result_http = client.get(endpoint, params={"session_id": session_id})
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s?session_id=%s --", endpoint, session_id)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_semantic_groups_insights(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        endpoint = f"{BASE}/{app_name}/semantic-groups-insights"
        result_http = client.get(endpoint)
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s --", endpoint)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_sessions_insights(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        endpoint = f"{BASE}/{app_name}/sessions-insights"
        result_http = client.get(endpoint, params={"limit": 25, "offset": 0})
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s --", endpoint)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_sessions_insights_with_semantic_group(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        top_wasteful = client.get(
            f"{BASE}/{app_name}/top-wasteful-sessions",
            params={"threshold": 0, "limit": 50},
        )
        assert top_wasteful.status_code == 200
        rows = top_wasteful.json()

        semantic_group_id = None
        for row in rows:
            candidate = row.get("semanticGroupId")
            if candidate:
                semantic_group_id = candidate
                break

        if semantic_group_id is None:
            pytest.skip(
                "No semanticGroupId available to test filtered sessions-insights"
            )

        app_name = "noa-trip-planner-mas"
        endpoint = f"{BASE}/{app_name}/sessions-insights"
        result_http = client.get(
            endpoint,
            params={"semantic_group_id": semantic_group_id, "limit": 25, "offset": 0},
        )
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info(
            "\n-- HTTP %s?semantic_group_id=%s --",
            endpoint,
            semantic_group_id,
        )
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)

    def test_get_single_session_insights(self, client) -> None:
        app_name = "noa-trip-planner-mas"
        sessions_insights = client.get(
            f"{BASE}/{app_name}/sessions-insights", params={"limit": 1}
        )
        assert sessions_insights.status_code == 200
        rows = sessions_insights.json()

        if not rows:
            pytest.skip("No session insights available to test single-session endpoint")

        session_id = rows[0].get("sessionId")
        if not session_id:
            pytest.skip("Could not infer sessionId from sessions-insights response")

        endpoint = f"{BASE}/session-insights"
        result_http = client.get(
            endpoint,
            params={"session_id": session_id, "limit": 25, "offset": 0},
        )
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("\n-- HTTP %s?session_id=%s --", endpoint, session_id)
        logger.info(json.dumps(data, indent=2))

        assert isinstance(data, list)
