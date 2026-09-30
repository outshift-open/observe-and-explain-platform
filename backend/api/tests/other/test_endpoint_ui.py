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
import tests.other.test_endpoint_ui_data_mocker as mocker
from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.client.sessions import _get_session_timeline_waterfall
from oxp.connectors.sqlalchemy import SQLAlchemyConnector
from oxp.dependencies import get_db, get_redis
from oxp.query_builders.types import Dialect
from oxp.repositories.sqlite_repository import SqliteOtelRepository
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


def _get_connector() -> SQLAlchemyConnector:
    """Lazily create and seed a module-level SQLite connector."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        _connector = SQLAlchemyConnector(url=f"sqlite:///{_DB_PATH}")
        _connector.connect()
        SqliteOtelRepository().seed(CSV_PATH, connector=_connector)
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

    def test_info_returns_expected_message(self, local_db) -> None:
        c = LocalClient(db=local_db)
        result = c.info(domain="ui")
        assert result == "Hello! This is the UI endpoint."

    def test_healthz(self, client):
        response = client.get(f"{BASE}/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    # ── get_application_names ─────────────────────────────────────

    def test_get_application_names(self, local_db, client) -> None:
        result_mocked = mocker.get_application_names()

        c = LocalClient(db=local_db)
        result = c.get_application_names()
        logger.info("\n── LIB    get_application_names () ──")
        logger.info(json.dumps(result.model_dump(), indent=2))
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/ui/applications/names",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications/names ──")
        logger.info(json.dumps(data, indent=2))
        assert "applications" in data
        assert isinstance(data["applications"], list)
        assert data == result_mocked.model_dump()

    # ── get_applications ─────────────────────────────────────

    def test_get_applications(self, local_db, client) -> None:
        result_mocked = mocker.get_applications()

        c = LocalClient(db=local_db)
        result = c.get_applications()
        logger.info("\n── LIB    get_applications () ──")
        logger.info(json.dumps(result.model_dump(), indent=2))
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/ui/applications",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications ──")
        logger.info(json.dumps(data, indent=2))
        assert "applications" in data
        assert isinstance(data["applications"], list)
        assert data == result_mocked.model_dump()

    # ── test_get_spans ─────────────────────────────────────

    def test_get_spans(self, local_db, client) -> None:
        span_id = "15ddf3bd7d0488b2"

        result_mocked = mocker.get_spans(span_id=span_id)
        c = LocalClient(db=local_db)
        result = c.get_spans(span_id=span_id)
        logger.info(f"\n── LIB get_spans (span_id={span_id}) ──")
        logger.info(json.dumps(result.model_dump(), indent=2))
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(f"{BASE}/spans/{span_id}")
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/spans/{span_id} ──")
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── test_get_session_agent_details ─────────────────────────────────────

    def test_get_session_agent_details(self, local_db, client) -> None:
        # session_id = "4d7b274d-8f3c-4ca5-bbcf-2ca3c319b91d"
        session_id = "e9815583-76e1-479b-9098-ba0c3f066bc8"
        agent_id = "noa-web-surfer"

        result_mocked = mocker.get_session_agent_details(
            session_id=session_id,
            agent_id=agent_id,
        )
        logger.info(
            f"\n── get_session_agent_details (session_id={session_id}, agent_id={agent_id}) ──"
        )
        logger.info(json.dumps(result_mocked.model_dump(), indent=2))
        c = LocalClient(db=local_db)
        result = c.get_session_agent_details(
            session_id=session_id,
            agent_id=agent_id,
        )
        logger.info(
            f"\n── get_session_agent_details (session_id={session_id}, agent_id={agent_id}) ──"
        )
        logger.info(json.dumps(result.model_dump(), indent=2))
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(f"/sessions/{session_id}/agent/{agent_id}/spans/")
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   /sessions/{session_id}/agent/{agent_id}/spans/ ──")
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── get_application_details ───────────────────────────────────────

    def test_get_application_details(self, local_db, client) -> None:
        application_id = "NOA"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_details(
            application_id=application_id,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_details(
            application_id=application_id,
            start_time=start,
            end_time=end,
        )
        logger.info(
            f"\n── LIB get_application_details (application={application_id}) ──"
        )
        logger.info(json.dumps(result.model_dump(), indent=2))
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}",
            params={
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/applications/{application_id} ──")
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump(by_alias=True)

    # ── get_application_agents ────────────────────────────────────────

    def test_get_application_agents(self, local_db, client) -> None:
        application_id = "NOA"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        # result_mocked = mocker.get_application_agents(
        #     application_id=application_id,
        # )

        c = LocalClient(db=local_db)
        result = c.get_application_agents(
            application_id=application_id,
            start_time=start,
            end_time=end,
        )
        logger.info(
            f"\n── LIB get_application_agents (application_id={application_id}) ──"
        )
        logger.info(json.dumps(result.model_dump(), indent=2))
        # assert result.model_dump() == result_mocked.model_dump()

        # result_http = client.get(f"{BASE}/applications/{application_id}/agents", params={
        #     "start_time": start,
        #     "end_time": end,
        # })
        # assert result_http.status_code == 200
        # data = result_http.json()
        # logger.info(f"\n── HTTP   {BASE}/applications/{application_id}/agents ──")
        # logger.info(json.dumps(data, indent=2))
        # assert data == result_mocked.model_dump()

    # ── get_application_sessions ──────────────────────────────────────

    def test_get_application_sessions(self, local_db, client) -> None:
        application_id = "NOA"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_sessions(
            application_id=application_id,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_sessions(
            application_id=application_id,
            start_time=start,
            end_time=end,
        )
        logger.info(
            f"\n── LIB get_application_sessions (application_id={application_id}) ──"
        )
        logger.info(json.dumps(result.model_dump(), indent=2))
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}/sessions",
            params={
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/applications/{application_id}/sessions ──")
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── application_charts general ────────────────────────────────────

    def test_get_application_charts_general(self, local_db, client) -> None:
        application_id = "NOA"
        agent_id = "noa-moderator"
        chart_type = "general"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        # result_mocked = mocker.get_application_charts(
        #     application_id=application_id,
        #     agent_id=agent_id,
        #     chart_type=chart_type,
        # )

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
            start_time=start,
            end_time=end,
        )
        logger.info(
            f"\n── LIB get_application_charts (app={application_id}, agent={agent_id}, chart_type={chart_type}) ──"
        )
        logger.info(json.dumps(result.model_dump(), indent=2))
        # assert result.model_dump() == result_mocked.model_dump()

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

    # ── application_charts quality-and-reasoning ──────────────────────

    def test_get_application_charts_quality_and_reasoning(
        self, local_db, client
    ) -> None:
        application_id = "NOA"
        agent_id = "noa-moderator"
        chart_type = "quality-and-reasoning"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
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
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}/agent/{agent_id}/charts",
            params={
                "chart_type": chart_type,
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/agent/{agent_id}/charts?chart_type={chart_type} ──"
        )
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── application_charts reliability-and-safety ─────────────────────

    def test_get_application_charts_reliability_and_safety(
        self, local_db, client
    ) -> None:
        application_id = "NOA"
        agent_id = "noa-moderator"
        chart_type = "reliability-and-safety"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
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
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}/agent/{agent_id}/charts",
            params={
                "chart_type": chart_type,
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/agent/{agent_id}/charts?chart_type={chart_type} ──"
        )
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── application_charts cost ───────────────────────────────────────

    def test_get_application_charts_cost(self, local_db, client) -> None:
        application_id = "NOA"
        agent_id = "noa-moderator"
        chart_type = "cost"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
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
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}/agent/{agent_id}/charts",
            params={
                "chart_type": chart_type,
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/agent/{agent_id}/charts?chart_type={chart_type} ──"
        )
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── application_charts tools ──────────────────────────────────────

    def test_get_application_charts_tools(self, local_db, client) -> None:
        application_id = "NOA"
        agent_id = "noa-moderator"
        chart_type = "tools"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
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
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}/agent/{agent_id}/charts",
            params={
                "chart_type": chart_type,
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/agent/{agent_id}/charts?chart_type={chart_type} ──"
        )
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── application_charts conversation ───────────────────────────────

    def test_get_application_charts_conversation(self, local_db, client) -> None:
        application_id = "NOA"
        agent_id = "noa-moderator"
        chart_type = "conversation"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
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
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}/agent/{agent_id}/charts",
            params={
                "chart_type": chart_type,
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/agent/{agent_id}/charts?chart_type={chart_type} ──"
        )
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── application_charts llm ────────────────────────────────────────

    def test_get_application_charts_llm(self, local_db, client) -> None:
        application_id = "NOA"
        agent_id = "noa-moderator"
        chart_type = "llm"
        start = to_epoch("2026-01-12 10:09:21")
        end = to_epoch("2026-01-13 19:09:21")

        result_mocked = mocker.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
        )

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
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
        assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(
            f"{BASE}/applications/{application_id}/agent/{agent_id}/charts",
            params={
                "chart_type": chart_type,
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/agent/{agent_id}/charts?chart_type={chart_type} ──"
        )
        logger.info(json.dumps(data, indent=2))
        assert data == result_mocked.model_dump()

    # ── get_applications ─────────────────────────────────────

    def test_get_application_charts_performance(self, local_db, client) -> None:
        c = LocalClient(db=local_db)

        application_id = "noa-trip-planner-mas"
        agent_id = "moderator"
        chart_type = "performance"
        start = to_epoch("2026-02-23 06:00:00")
        end = to_epoch("2026-02-23 12:00:00")

        c = LocalClient(db=local_db)
        result = c.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
            start_time=start,
            end_time=end,
        )
        logger.info(
            f"\n── LIB get_application_charts (app={application_id}, agent={agent_id}, chart_type={chart_type}) ──"
        )
        logger.info(json.dumps(result.model_dump(), indent=2))

    # ── get_application_topology ─────────────────────────────────────

    def test_get_application_topology(self, local_db, client) -> None:
        application_id = "NOA"

        c = LocalClient(db=local_db)
        result = c.get_application_topology(
            application_id=application_id,
        )
        logger.info(
            f"\n── LIB get_application_topology (application={application_id}) ──"
        )
        logger.info(json.dumps(result, indent=2))

        result_http = client.get(
            f"{BASE}/applications/{application_id}/topology", params={}
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/applications/{application_id}/topology ──")
        logger.info(json.dumps(data, indent=2))

    def test_get_session_timeline_waterfall(self, local_db, client) -> None:
        session_id = "70accc97-78db-46f8-9089-a8498f5f05c5"

        # result_mocked = mocker._get_session_timeline_waterfall(
        #     session_id=session_id
        # )

        c = LocalClient(db=local_db)
        result_lib = c.get_session_timeline_waterfall(session_id=session_id)
        logger.info(
            f"\n── LIB _get_session_timeline_waterfall (session_id={session_id}) ──"
        )
        logger.info(json.dumps(result_lib.model_dump(), indent=2))
        # assert result.model_dump() == result_mocked.model_dump()

        result_http = client.get(f"{BASE}/sessions/{session_id}/timeline")
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/sessions/{session_id}/timeline ──")
        logger.info(json.dumps(data, indent=2))
        assert data == result_lib.model_dump()

    def test_get_session_timeline_waterfall_handles_time_only_timestamps(self) -> None:
        class FakeConnector:
            def execute(self, stmt):
                return [
                    (
                        "09:21.7",
                        "span-1",
                        "agent.alpha",
                        "missing-parent-1",
                        "agent",
                        "NOA",
                        2_000_000_000,
                        "",
                    ),
                    (
                        "09:30.0",
                        "span-2",
                        "agent.beta",
                        "missing-parent-2",
                        "agent",
                        "NOA",
                        1_000_000_000,
                        "",
                    ),
                ]

        result = _get_session_timeline_waterfall(
            FakeConnector(),
            Dialect.SQLITE,
            session_id="session-1",
        )

        assert result.duration == 9300
        assert result.startTime == "09:21.7"
        assert result.endTime == "09:31"
        assert result.Spans[0].endTime == "09:23.7"

    def test_get_session_timeline_waterfall_excludes_delayed_session_end_from_root_duration(
        self,
    ) -> None:
        class FakeConnector:
            def execute(self, stmt):
                return [
                    (
                        "2026-03-09T09:02:48.106390",
                        "workflow",
                        "LangGraph.workflow",
                        "",
                        "agent",
                        "NOA",
                        23_782_000_000,
                        "",
                    ),
                    (
                        "2026-03-09T09:04:57.428148",
                        "session-end",
                        "session.end",
                        "",
                        "agent",
                        "NOA",
                        0,
                        "",
                    ),
                ]

        result = _get_session_timeline_waterfall(
            FakeConnector(),
            Dialect.SQLITE,
            session_id="session-2",
        )

        assert result.duration == 23782
        assert result.startTime == "2026-03-09T09:02:48.106390"
        assert result.endTime == "2026-03-09T09:03:11.888390"
        assert len(result.Spans) == 2
        assert result.Spans[1].spanName == "session.end"
