#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import logging
import os

import fakeredis
import pytest
from fastapi.testclient import TestClient

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.connectors.neo4j import Neo4JConnector
from oxp.dependencies import get_neo4j_db, get_redis

logger = logging.getLogger(__name__)

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
                "tests/test_sessions.py.",
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
    """Discover one symbolic session + application for session count test."""
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


def test_session_conversation(client, symbolic_context, neo4j_db) -> None:
    session_id = symbolic_context.get("session_id")
    if not session_id:
        session_rows = neo4j_db.execute(
            """
            MATCH (session:Session)
            RETURN session.sessionId AS session_id
            LIMIT 1
            """
        )
        session_id = session_rows[0].get("session_id") if session_rows else None

    if not session_id:
        pytest.skip("No session found to test /sessions/{session_id}/conversation")

    endpoint = f"{BASE}/sessions/{session_id}/conversation"
    response = client.get(endpoint)
    assert response.status_code == 200

    data = response.json()
    logger.info("\n-- HTTP %s --", endpoint)
    logger.info(json.dumps(data, indent=2, default=str))

    assert data["session_id"] == session_id
    assert isinstance(data["messages"], list)
    for message in data["messages"]:
        assert "transition_id" in message
        assert "agent_name" in message
        assert "input" in message
        assert "output" in message


def test_sessions_count(client, symbolic_context, neo4j_db) -> None:
    application_id = symbolic_context.get("application_id")
    if not application_id:
        app_rows = neo4j_db.execute(
            """
            MATCH (mas:MAS)
            RETURN mas.masName AS application_id
            LIMIT 1
            """
        )
        application_id = app_rows[0].get("application_id") if app_rows else None

    if not application_id:
        pytest.skip("No MAS application found to test /sessions/count")

    endpoint = f"{BASE}/sessions/count"
    response = client.get(endpoint, params={"application_id": application_id})
    assert response.status_code == 200

    data = response.json()
    logger.info("\n-- HTTP %s?application_id=%s --", endpoint, application_id)
    logger.info(json.dumps(data, indent=2, default=str))

    assert isinstance(data, dict)
    assert "count" in data
    assert isinstance(data["count"], int)
