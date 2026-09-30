#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Functional tests that log returned JSON to the terminal.

Run with:
    pytest tests/test_endpoint_ui_dev.py -v -s

Use CONNECTOR_TYPE to choose the database backend:
    CONNECTOR_TYPE=SQLITE  pytest tests/test_endpoint_ui_dev.py -v -s   (default)
    CONNECTOR_TYPE=CLICKHOUSE OXP_CH_HOST=... pytest tests/test_endpoint_ui_dev.py -v -s
"""

import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

import fakeredis
from dotenv import load_dotenv

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.connectors.clickhouse import ClickHouseConnector
from oxp.connectors.sqlalchemy import SQLAlchemyConnector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_redis
from oxp.repositories.sqlite_repository import SqliteOtelRepository
from fastapi.testclient import TestClient

load_dotenv()

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Path to CSV data shipped with the repo
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "csv", "otel_traces.csv")


# ── Connector type flag ──────────────────────────────────────────────────────
# Set CONNECTOR_TYPE=CLICKHOUSE to use a remote ClickHouse server,
# or CONNECTOR_TYPE=SQLITE (default) to use a local SQLite file.

CONNECTOR_TYPE = os.environ.get("CONNECTOR_TYPE", "SQLITE").upper()

# ── Module-scoped connector (shared across all tests) ────────────────────────

_DEBUG = logger.isEnabledFor(logging.DEBUG)

# SQLite-specific paths (only used when CONNECTOR_TYPE == "SQLITE")
OXP_DB_PATH = os.environ.get(
    "OXP_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox"),
)

if CONNECTOR_TYPE == "SQLITE":
    if _DEBUG:
        _db_dir = (
            os.path.dirname(OXP_DB_PATH) if OXP_DB_PATH.endswith(".db") else OXP_DB_PATH
        )
        os.makedirs(_db_dir, exist_ok=True)
        _DB_PATH = (
            OXP_DB_PATH
            if OXP_DB_PATH.endswith(".db")
            else os.path.join(OXP_DB_PATH, "oxp_test.db")
        )
    else:
        _tmp_dir = tempfile.mkdtemp(prefix="oxp_test_")
        _DB_PATH = os.path.join(_tmp_dir, "oxp_test.db")
else:
    _DB_PATH = None  # not used for ClickHouse

_connector: SQLAlchemyConnector | ClickHouseConnector | None = None


def _get_connector() -> SQLAlchemyConnector | ClickHouseConnector:
    """Lazily create a module-level connector (SQLite or ClickHouse)."""
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
    if CONNECTOR_TYPE == "SQLITE":
        if not _DEBUG and _DB_PATH and os.path.exists(_DB_PATH):
            os.remove(_DB_PATH)
        else:
            logger.debug("DEBUG mode — keeping SQLite DB at: %s", _DB_PATH)


@pytest.fixture()
def local_db():
    """Provide the shared connector (SQLite or ClickHouse) for the test database."""
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


class TestWithLocalDBs:
    # ── application_charts quality-and-reasoning ──────────────────────

    def test_get_application_charts_quality_and_reasoning(
        self, local_db, client
    ) -> None:
        application_id = "noa-trip-planner-mas"
        agent_id = "moderator"
        chart_type = "quality-and-reasoning"
        start = to_epoch("2026-03-23 00:00:00")
        end = to_epoch("2026-03-23 23:59:59")

        local_client = LocalClient(db=local_db)
        result = local_client.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
            start_time=start,
            end_time=end,
        )
        logger.info(
            f"\n── LIB get_application_charts (app={application_id}, agent_id={agent_id}, chart_type={chart_type}) ──"
        )
        logger.info(json.dumps(result.model_dump(), indent=2))

        # result_http = client.get(f"{BASE}/applications/{application_id}/agent/{agent_id}/charts", params={
        #     "chart_type": chart_type,
        #     "start_time": start,
        #     "end_time": end,
        # })
        # assert result_http.status_code == 200
        # data = result_http.json()
        # logger.info(f"\n── HTTP   {BASE}/applications/{application_id}/agent/{agent_id}/charts?chart_type={chart_type} ──")
        # logger.info(json.dumps(data, indent=2))
        # assert data == result_mocked.model_dump()
