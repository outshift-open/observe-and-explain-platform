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
from datetime import datetime, timezone
from pathlib import Path

import pytest
import fakeredis
from dotenv import load_dotenv
from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.connectors.neo4j import Neo4JConnector
from oxp.dependencies import get_db, get_redis
from fastapi.testclient import TestClient

# Load API .env for test-only environment defaults.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Path to CSV data shipped with the repo
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "csv", "otel_traces.csv")


# ── Module-scoped connector (shared across all tests) ────────────────────────

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
            "Using Neo4j connector — %s:%s/%s",
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
    """Initialise the database connector once for the module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture()
def local_db():
    """Provide the shared Neo4JConnector for the test database."""
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
    def test_info_returns_expected_message(self, local_db) -> None:
        c = LocalClient(db=local_db)
        result = c.info(domain="ui")
        assert result == "Hello! This is the UI endpoint."

    def test_get_applications(self, local_db, client) -> None:
        """Retrieve the list of applications."""
        if not isinstance(local_db, Neo4JConnector):
            logger.error(
                "test_get_applications requires Neo4JConnector, got %s",
                type(local_db).__name__,
            )
            return

        endpoint = f"{BASE}/applications"
        result_http = client.get(endpoint)
        if result_http.status_code == 404:
            endpoint = f"{BASE}/ui/applications/"
            result_http = client.get(endpoint)

        assert result_http.status_code == 200

        data = result_http.json()
        assert data is not None
        logger.info(f"\n── HTTP   {endpoint} ──")
        logger.info(json.dumps(data, indent=2))
