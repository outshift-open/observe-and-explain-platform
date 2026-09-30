#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
import os
import sys

import fakeredis
import pytest
from fastapi.testclient import TestClient

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.connectors.neo4j import Neo4JConnector
from oxp.dependencies import get_neo4j_db, get_redis

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BASE = "/api/v1"
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

        if not password.strip():
            pytest.fail(
                "Neo4j password missing. Set NEO4J_PASSWORD before running "
                "tests/test_reasoning.py.",
                pytrace=False,
            )

        logger.info("Using Neo4j connector - %s:%s/%s", host, port, database)
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
            message = str(exc)
            if "Unauthorized" in message or "credentials" in message:
                pytest.fail(
                    "Neo4j authentication failed. Check NEO4J_USERNAME/NEO4J_PASSWORD. "
                    f"Original error: {message}",
                    pytrace=False,
                )
            pytest.skip(
                f"Neo4j connection failed for tests (non-auth issue). Error: {message}"
            )

        if not _connector.is_connected():
            pytest.fail(
                "Neo4j connector is not connected. Verify credentials and Neo4j "
                "availability (NEO4J_HOST/NEO4J_PORT).",
                pytrace=False,
            )

    return _connector


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialise Neo4j connector once for this module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture(scope="module")
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


@pytest.fixture(scope="module")
def symbolic_context(neo4j_db) -> dict[str, str | None]:
    """Discover one symbolic session + application for reasoning-path tests."""
    rows = neo4j_db.execute(
        """
        MATCH (session:Session)-[:executesSession]->(mas:MAS)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
        WHERE coalesce(sm.isActive, false) = true
        RETURN session.sessionId AS session_id, mas.masName AS application_id
        LIMIT 1
        """
    )
    if not rows:
        return {"session_id": None, "application_id": None}

    row = rows[0]
    return {
        "session_id": row.get("session_id"),
        "application_id": row.get("application_id"),
    }


class TestReasoningEndpoints:
    def test_session_reasoning_path(self, client, symbolic_context) -> None:
        session_id = symbolic_context.get("session_id")
        if not session_id:
            pytest.skip("No symbolic session found to test /session-reasoning-path")

        endpoint = f"{BASE}/session-reasoning-path"
        response = client.get(endpoint, params={"session_id": session_id})
        assert response.status_code == 200

        data = response.json()
        logger.info("\\n-- HTTP %s?session_id=%s --", endpoint, session_id)
        logger.info(json.dumps(data, indent=2, default=str))

        assert data.get("sessionId") == session_id
        assert isinstance(data.get("nodes"), list)
        assert isinstance(data.get("edges"), list)

    def test_application_reasoning_path(self, client, symbolic_context) -> None:
        application_id = symbolic_context.get("application_id")
        if not application_id:
            pytest.skip(
                "No symbolic application found to test /application-reasoning-path"
            )

        endpoint = f"{BASE}/application-reasoning-path"
        response = client.get(endpoint, params={"mas_name": application_id})
        assert response.status_code == 200

        data = response.json()
        logger.info("\\n-- HTTP %s?mas_name=%s --", endpoint, application_id)
        logger.info(json.dumps(data, indent=2, default=str))

        assert data.get("masName") == application_id
        assert isinstance(data.get("nodes"), list)
        assert isinstance(data.get("edges"), list)

    def test_timeline_reasoning_path(self, client, symbolic_context) -> None:
        session_id = symbolic_context.get("session_id")
        if not session_id:
            pytest.skip("No symbolic session found to test /timeline-reasoning-path")

        endpoint = f"{BASE}/timeline-reasoning-path"
        response = client.get(endpoint, params={"session_id": session_id})
        assert response.status_code == 200

        data = response.json()
        logger.info("\\n-- HTTP %s?session_id=%s --", endpoint, session_id)
        logger.info(json.dumps(data, indent=2, default=str))

        assert data.get("sessionId") == session_id
        assert isinstance(data.get("spans"), list)

    def test_applications_with_stateful_eval(self, client) -> None:
        endpoint = f"{BASE}/applications-with-stateful-eval"
        response = client.get(endpoint)
        assert response.status_code == 200

        data = response.json()
        logger.info("\\n-- HTTP %s --", endpoint)
        logger.info(json.dumps(data, indent=2, default=str))

        assert isinstance(data, list)
