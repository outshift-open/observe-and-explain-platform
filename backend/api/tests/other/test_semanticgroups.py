#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Functional tests that log returned JSON to the terminal.

Run with:
    pytest tests/test_functions.py -v -s
"""

import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

import fakeredis
from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.connectors.neo4j import Neo4JConnector
from oxp.connectors.sqlalchemy import SQLAlchemyConnector
from oxp.dependencies import get_db, get_redis
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Path to CSV data shipped with the repo
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "csv", "otel_traces.csv")


# ── Module-scoped connector (shared across all tests) ────────────────────────

_tmp_dir = tempfile.mkdtemp(prefix="oxp_test_")
_DB_PATH = os.path.join(_tmp_dir, "oxp_test.db")
_connector: SQLAlchemyConnector | None = None

_connector: Neo4JConnector | None = None


def _get_connector() -> Neo4JConnector:
    """Lazily create a module-level connector (Neo4J)."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        host = os.environ.get("NEO4J_HOST") or "localhost"
        port = int(os.environ.get("NEO4J_PORT") or "7687")
        username = os.environ.get("NEO4J_USERNAME") or "neo4j"
        password = os.environ.get("NEO4J_PASSWORD") or ""
        database = os.environ.get("NEO4J_DATABASE") or "neo4j"

        logger.info(
            "Using Neo4J connector — %s:%s/%s",
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
        _connector.connect()
        if not _connector.is_connected():
            raise RuntimeError(
                "Neo4j connection/authentication failed for tests. "
                "Set valid NEO4J_* environment variables."
            )
    return _connector


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Seed the SQLite database once for the module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()
    if os.path.exists(_DB_PATH):
        os.remove(_DB_PATH)


@pytest.fixture()
def local_db():
    """Provide the shared SQLAlchemyConnector for the test database."""
    return _get_connector()


@pytest.fixture()
def client(local_db):
    """Return a FastAPI ``TestClient`` with the DB dependency overridden."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_db] = lambda: local_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)
    reset_client()


# ── Helpers ──────────────────────────────────────────────────────────────────

BASE = "/api/v1"


def to_epoch(timestamp: str) -> str:
    """Convert a human-readable timestamp to a Unix epoch string.

    Accepts the format used in otel_traces.csv, e.g.
    ``"2025-10-06 15:00:23.626769894"``.
    """
    # Truncate to whole seconds — sub-second precision is not needed
    truncated = timestamp[:19]  # "YYYY-MM-DD HH:MM:SS"
    try:
        dt = datetime.strptime(truncated, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        return str(dt.timestamp())
    except ValueError:
        raise ValueError(f"Cannot parse timestamp: {timestamp!r}")


# ── tests ────────────────────────────────────────────────────


class TestLocalClientInstance:
    """Verify LocalClient works when instantiated with a local SQLite connector."""

    def test_info_returns_expected_message(self, local_db) -> None:
        c = LocalClient(db=local_db)
        result = c.info(domain="ui")
        assert result == "Hello! This is the UI endpoint."

    def test_healthz(self, client):
        response = client.get(f"{BASE}/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_get_application_semanticgroups(self, local_db, client) -> None:
        application_id = "noa-trip-planner-mas"
        # application_id = "NOA"

        # c = LocalClient(db=local_db)
        # result_lib = c.get_application_semanticgroups(
        #     application_id=application_id,
        # )
        # logger.info(f"\n── LIB get_application_semanticgroups (application={application_id}) ──")
        # logger.info(json.dumps(result_lib.model_dump(), indent=2))

        result_http = client.get(
            f"{BASE}/applications/{application_id}/semanticgroups", params={}
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/semanticgroups ──"
        )
        logger.info(json.dumps(data, indent=2))

        # assert data == result_lib.model_dump(by_alias=True)

        # data = result_lib.model_dump(by_alias=True)

        assert any(node.get("children_nodes") for node in data.get("nodes", [])), (
            "Expected semanticgroups to include at least one internal node with children"
        )
        assert any(not node.get("children_nodes") for node in data.get("nodes", [])), (
            "Expected semanticgroups to include at least one leaf node without children"
        )

    def test_get_application_semanticgroups_table(self, local_db, client) -> None:
        # application_id = "NOA"
        application_id = "noa-trip-planner-mas"

        c = LocalClient(db=local_db)
        result_lib = c.get_application_semanticgroups_table(
            application_id=application_id,
        )
        logger.info(
            f"\n── LIB get_application_semanticgroups_table (application={application_id}) ──"
        )
        logger.info(json.dumps(result_lib.model_dump(), indent=2))

        result_http = client.get(
            f"{BASE}/applications/{application_id}/semanticgroups/table", params={}
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/semanticgroups/table ──"
        )
        logger.info(json.dumps(data, indent=2))

        # assert data == result_lib.model_dump(by_alias=True)

    def test_get_semanticgroup_normal_behavior(self, local_db, client) -> None:
        semanticgroup_id = "sg_internal_192_f446d175"

        c = LocalClient(db=local_db)
        result_lib = c.get_semanticgroup_normal_behavior(
            semanticgroup_id=semanticgroup_id,
        )
        logger.info(
            f"\n── LIB get_semanticgroup_normal_behavior (semanticgroup_id={semanticgroup_id}) ──"
        )
        logger.info(json.dumps(result_lib.model_dump(), indent=2))

        result_http = client.get(
            f"{BASE}/semanticgroups/{semanticgroup_id}/normal_behavior", params={}
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/semanticgroups/{semanticgroup_id}/normal_behavior ──"
        )
        logger.info(json.dumps(data, indent=2))

        assert data == result_lib.model_dump(by_alias=True)

    def test_get_semanticgroup_details(self, local_db, client) -> None:
        semanticgroup_id = "sg_internal_192_f446d175"

        c = LocalClient(db=local_db)
        result_lib = c.get_semanticgroup_details(
            semanticgroup_id=semanticgroup_id,
        )
        logger.info(
            f"\n── LIB get_semanticgroup_details (semanticgroup_id={semanticgroup_id}) ──"
        )
        logger.info(json.dumps(result_lib.model_dump(), indent=2))

        result_http = client.get(f"{BASE}/semanticgroups/{semanticgroup_id}", params={})
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/semanticgroups/{semanticgroup_id} ──")
        logger.info(json.dumps(data, indent=2))

        assert data == result_lib.model_dump(by_alias=True)

    def test_get_session_trajectory(self, local_db, client) -> None:
        session_id = "70accc97-78db-46f8-9089-a8498f5f05c5"

        # result_mocked = mocker._get_session_trajectory(
        #     session_id=session_id
        # )

        c = LocalClient(db=local_db)
        result_lib = c.get_session_trajectory(session_id=session_id)
        logger.info(f"\n── LIB _get_session_trajectory (session_id={session_id}) ──")
        logger.info(json.dumps(result_lib.model_dump(), indent=2))
        #     assert result_lib.model_dump() == result_mocked.model_dump()

        result_http = client.get(f"{BASE}/sessions/{session_id}/trajectory")
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/sessions/{session_id}/trajectory ──")
        logger.info(json.dumps(data, indent=2))
        assert data == result_lib.model_dump()
