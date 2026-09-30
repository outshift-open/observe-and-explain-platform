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
from oxp.api.api_v1.endpoints import metrics as metrics_endpoint
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.connectors.neo4j import Neo4JConnector
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


# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# from oxp.db.database import init_oxp_db
# from oxp.scripts.seed import seed_database_test
# import oxp.ui


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

    def test_get_session_metrics(self, local_db, client) -> None:
        # session_id = "session-abc"
        session_id = "e9815583-76e1-479b-9098-ba0c3f066bc8"
        hops = 2

        kg_client = LocalClient(db=local_db)

        result_lib = kg_client.get_session_metrics(session_id, hops=hops)
        logger.info(
            f"\n── LIB get_session_metrics (session_id={session_id}, hops={hops}) ──"
        )
        logger.info(json.dumps(result_lib.model_dump(), indent=2))

        assert result_lib.session_id == session_id
        assert isinstance(result_lib.metrics, list)

        metrics_endpoint._metrics_kg_client = kg_client
        result_http = client.get(
            f"{BASE}/metrics/sessions/{session_id}", params={"hops": hops}
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/metrics/sessions/{session_id}?hops={hops} ──")
        logger.info(json.dumps(data, indent=2))

        assert data["session_id"] == session_id
        assert isinstance(data.get("metrics", []), list)

    def test_get_session_timeline(self, local_db, client) -> None:
        # GET /graph/state-machine/0c589041-888a-449d-983e-19c6af599494?level=agent,call
        session_id = "0c589041-888a-449d-983e-19c6af599494"
        level = "agent"

        kg_client = LocalClient(db=local_db)
        result_lib = kg_client.get_session_timeline(
            session_id=session_id,
            level=level,
        )
        logger.info(f"\n── LIB _get_session_timeline (session_id={session_id}) ──")
        logger.info(json.dumps(result_lib.model_dump(), indent=2))

        result_http = client.get(
            f"{BASE}/sessions/{session_id}/timeline", params={"level": level}
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/sessions/{session_id}/timeline ──")
        logger.info(json.dumps(data, indent=2))

        # assert data["session_id"] == session_id
        # assert isinstance(data.get("metrics", []), list)

    def test_get_session_execution_graph(self, local_db, client) -> None:
        # session_id = "70accc97-78db-46f8-9089-a8498f5f05c5"
        # session_id = "4:eacdf8b8-42e1-48b7-be22-5c5e89afd043:43336"
        # session_id = "00bb4cd7-112c-443a-bcaf-f90c2955696a" # Pablo: this was working
        # session_id = "7fc16b47-d02f-4d0b-8c84-40bf939b1567" # from Paul
        session_id = "7a60d784-2c20-4410-9e27-5a1d9c846c5a"

        # client = LocalClient(db=local_db)
        # result_lib = client.get_session_execution_graph(
        #     session_id=session_id
        # )
        # logger.info(f"\n── LIB _get_session_execution_graph (session_id={session_id}) ──")
        # logger.info(json.dumps(result_lib.model_dump(), indent=2))

        result_http = client.get(f"{BASE}/sessions/{session_id}/execution-graph")
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/sessions/{session_id}/execution-graph ──")
        logger.info(json.dumps(data, indent=2))
        # assert data == result_lib.model_dump()

    def test_get_session_latent_space(self, local_db, client) -> None:
        """Test the latent space endpoint with state embeddings projected to 2D."""
        session_id = "7fc16b47-d02f-4d0b-8c84-40bf939b1567"

        # Test with default parameters
        result_http = client.get(f"{BASE}/sessions/{session_id}/latent-space")

        if result_http.status_code == 404:
            logger.info(f"\n── HTTP   {BASE}/sessions/{session_id}/latent-space ──")
            logger.info(
                f"Status: {result_http.status_code} — Session may not have state embeddings"
            )
            logger.info(json.dumps(result_http.json(), indent=2))
        else:
            assert result_http.status_code == 200
            data = result_http.json()
            logger.info(
                f"\n── HTTP   {BASE}/sessions/{session_id}/latent-space (default) ──"
            )
            logger.info(json.dumps(data, indent=2))

            # Verify response structure
            # assert "nodes" in data
            # assert "edges" in data
            # assert "session_id" in data
            # assert "metadata" in data
            # assert data["session_id"] == session_id

        # Test with custom UMAP parameters
        result_http_custom = client.get(
            f"{BASE}/sessions/{session_id}/latent-space",
            params={"n_neighbors": 10, "min_dist": 0.05},
        )

        if result_http_custom.status_code == 200:
            data_custom = result_http_custom.json()
            logger.info(
                f"\n── HTTP   {BASE}/sessions/{session_id}/latent-space (n_neighbors=10, min_dist=0.05) ──"
            )
            logger.info(json.dumps(data_custom, indent=2))

            # assert "nodes" in data_custom
            # assert "edges" in data_custom
            # assert data_custom["metadata"]["umap_params"]["n_neighbors"] == 10
            # assert data_custom["metadata"]["umap_params"]["min_dist"] == 0.05
