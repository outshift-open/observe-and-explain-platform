#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from pathlib import Path

import pytest
import fakeredis
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.connectors.clickhouse import ClickHouseConnector
from oxp.dependencies import get_db, get_redis

# Load API .env for test-only environment defaults.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

BASE = "/api/v1"
_connector: ClickHouseConnector | None = None


def _get_connector() -> ClickHouseConnector:
    """Lazily create a module-level ClickHouse connector."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        host = os.environ.get("CLICKHOUSE_HOST") or "localhost"
        port = int(os.environ.get("CLICKHOUSE_PORT") or "8123")
        username = os.environ.get("CLICKHOUSE_USERNAME") or "default"
        password = os.environ.get("CLICKHOUSE_PASSWORD") or ""
        database = os.environ.get("CLICKHOUSE_DATABASE") or "default"

        _connector = ClickHouseConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )
        _connector.connect()

    return _connector


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialise the ClickHouse connector once for the module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture()
def local_db():
    """Provide the shared ClickHouse connector for the test database."""
    return _get_connector()


@pytest.fixture()
def client(local_db):
    """Return a FastAPI TestClient with DB/Redis dependencies overridden."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_db] = lambda: local_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)
    reset_client()


def test_get_agentic_protocols_metrics_new_top_level_route_only(
    local_db,
    client,
):
    application = os.environ.get("APM_TEST_APPLICATION") or "noa-trip-planner-mas"
    start_time = os.environ.get("APM_TEST_START_TIME") or ""
    end_time = os.environ.get("APM_TEST_END_TIME") or ""

    expected = LocalClient(db=local_db).get_agentic_protocols_metrics(
        application=application,
        start_time=start_time or None,
        end_time=end_time or None,
    )

    response = client.get(
        f"{BASE}/agentic-protocols-metrics",
        params={
            "application": application,
            "start_time": start_time,
            "end_time": end_time,
        },
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
