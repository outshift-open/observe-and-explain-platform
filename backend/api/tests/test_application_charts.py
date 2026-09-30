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
from oxp.connectors.clickhouse import ClickHouseConnector
from oxp.connectors.sqlalchemy import SQLAlchemyConnector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_redis
from oxp.repositories.sqlite_repository import SqliteOtelRepository
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Path to CSV data shipped with the repo
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "csv", "otel_traces.csv")


# ── Connector type flag ──────────────────────────────────────────────────────
# Set CONNECTOR_TYPE=CLICKHOUSE to run against a real ClickHouse instance.
# Neo4J is used automatically for graph endpoints via the get_neo4j_db
# singleton in oxp.dependencies — no override needed here.
# Defaults to SQLITE for fully local, dependency-free runs.

CONNECTOR_TYPE = os.environ.get("CONNECTOR_TYPE", "SQLITE").upper()

# ── Module-scoped connector (shared across all tests) ────────────────────────

_tmp_dir = tempfile.mkdtemp(prefix="oxp_test_")
_DB_PATH = os.path.join(_tmp_dir, "oxp_test.db") if CONNECTOR_TYPE == "SQLITE" else None
_connector: ClickHouseConnector | SQLAlchemyConnector | None = None


def _get_connector() -> ClickHouseConnector | SQLAlchemyConnector:
    """Lazily create a module-level connector (ClickHouse or SQLite)."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        if CONNECTOR_TYPE == "CLICKHOUSE":
            _connector = ClickHouseConnector(
                host=settings.CLICKHOUSE_HOST,
                port=settings.CLICKHOUSE_PORT,
                username=settings.CLICKHOUSE_USERNAME,
                password=settings.CLICKHOUSE_PASSWORD,
                database=settings.CLICKHOUSE_DATABASE,
            )
            logger.info(
                "Using ClickHouse connector — %s:%s/%s",
                settings.CLICKHOUSE_HOST,
                settings.CLICKHOUSE_PORT,
                settings.CLICKHOUSE_DATABASE,
            )
            _connector.connect()
        else:
            db_url = f"sqlite:///{_DB_PATH}"
            _connector = SQLAlchemyConnector(url=db_url)
            _connector.connect()
            logger.debug("Using SQLite connector — DB path: %s", _DB_PATH)
            SqliteOtelRepository().seed(CSV_PATH, connector=_connector)
    return _connector


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialise the database connector once for the module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()
    if CONNECTOR_TYPE == "SQLITE" and _DB_PATH and os.path.exists(_DB_PATH):
        os.remove(_DB_PATH)


@pytest.fixture()
def local_db():
    """Provide the shared connector (ClickHouse or SQLite) for the test database."""
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


class TestApplicationCharts:
    """Verify LocalClient works when instantiated with a local SQLite connector."""

    def test_get_metrics_catalog_by_category(self, local_db, client) -> None:
        application_id = "noa-trip-planner-mas"

        # 1. Fetch the category catalog via HTTP
        response = client.get(f"{BASE}/metrics/catalog_with_categories")
        assert response.status_code == 200

        categories_meta = response.json()
        logger.info(
            "\n── HTTP get_catalog_with_categories ── %s",
            application_id,
        )
        logger.info(json.dumps(categories_meta, indent=2, default=str))

    def test_get_metrics_by_category_meta(self, local_db, client) -> None:
        application_id = "noa-trip-planner-mas"

        # 1. Fetch the category catalog via HTTP
        response = client.get(f"{BASE}/metrics/catalog_with_categories_meta")
        assert response.status_code == 200

        categories_meta = response.json()
        logger.info(
            "\n── HTTP get_catalog_with_categories_meta ── %s",
            application_id,
        )
        logger.info(json.dumps(categories_meta, indent=2, default=str))

        # ###
        # response = client.get(f"{BASE}/sessions")
        # assert response.status_code == 200
        # body = response.json()
        # logger.info("\n── HTTP /api/v1/sessions ──")
        # logger.info(json.dumps(body, indent=2, default=str))

        # print("**************************************")

        # 2. For each category call both category-aware and explicit-list endpoints, and also retrieve one by one all the metrics from mcev2

        for cat_key, meta in (categories_meta or {}).items():
            metrics_list = meta.get("metrics_list") or []

            if metrics_list:
                params = [("metric_names", name) for name in metrics_list]
                for name in metrics_list:
                    print("##################################")
                    print(name)
                    print("##################################")
                    response = client.get(
                        f"{BASE}/metrics/info", params={"metric_id": name}
                    )
                    if response.status_code == 404:
                        logger.debug(
                            "\n── HTTP /api/v1/metrics/info (metric_id=%s) → 404 NOT FOUND: %s",
                            name,
                            response.text,
                        )
                        print(f"[404] metric not found: {name} — {response.text}")
                        continue
                    assert response.status_code == 200
                    body = response.json()
                    logger.info(
                        "\n── HTTP /api/v1/metrics/info (metric_id=%s) ──", name
                    )
                    logger.info(json.dumps(body, indent=2, default=str))

            # GET /metrics/applications/{id}/metrics?metric_names=...
            if metrics_list:
                params = [("metric_names", name) for name in metrics_list]
                resp1 = client.get(
                    f"{BASE}/metrics/applications/{application_id}/metrics",
                    params=params,
                )
                assert resp1.status_code == 200, (
                    f"GET /metrics failed for category {cat_key}: {resp1.status_code} {resp1.text}"
                )
                metrics_by_list = resp1.json()
                logger.info(
                    "\n── HTTP get_metrics (category=%s, metrics=%s) ──\n%s",
                    cat_key,
                    metrics_list,
                    json.dumps(metrics_by_list, indent=2, default=str),
                )

            # GET /metrics/applications/{id}/category/{cat_key}
            resp2 = client.get(
                f"{BASE}/metrics/applications/{application_id}/category/{cat_key}"
            )
            assert resp2.status_code == 200, (
                f"GET /metrics/category/{cat_key} failed: {resp2.status_code} {resp2.text}"
            )
            metrics_by_cat = resp2.json()
            logger.info(
                "\n── HTTP get_metrics_per_category (category=%s) ──\n%s",
                cat_key,
                json.dumps(metrics_by_cat, indent=2, default=str),
            )


def test_get_session_metrics() -> None:
    """GET /metrics/sessions/{session_id} returns metrics for a session."""
    # session_id = "8efd73a9-ac4f-4d27-b9fa-918112ba4c14"
    session_id = "55441c35-72f4-4b71-a72d-7d0e582d635a"

    client = TestClient(app)
    response = client.get(f"{BASE}/metrics/sessions/{session_id}")

    assert response.status_code == 200
    body = response.json()

    logger.info(f"\n── HTTP /api/v1/metrics/sessions/{session_id} ──")
    logger.info(json.dumps(body, indent=2, default=str))

    assert body["session_id"] == session_id
    assert "metrics" in body
    assert isinstance(body["metrics"], list)
