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
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import fakeredis
from dotenv import load_dotenv
from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.connectors.clickhouse import ClickHouseConnector
from oxp.connectors.sqlalchemy import SQLAlchemyConnector
from oxp.dependencies import get_db, get_redis
from oxp.repositories.sqlite_repository import SqliteOtelRepository
from fastapi.testclient import TestClient

# Load API .env for test-only environment defaults.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Path to CSV data shipped with the repo
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "csv", "otel_traces.csv")


# ── Connector type flag ──────────────────────────────────────────────────────
# Set CONNECTOR_TYPE=CLICKHOUSE to use a remote ClickHouse server,
# or CONNECTOR_TYPE=SQLITE (default) to use a local SQLite file.

CONNECTOR_TYPE = os.environ.get("CONNECTOR_TYPE", "CLICKHOUSE").upper()

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
            logger.info(
                "Using ClickHouse connector — %s:%s/%s",
                host,
                port,
                database,
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

    def test_get_applications_from_clickhouse(self, local_db, client) -> None:
        """Retrieve the list of applications from ClickHouse."""
        if CONNECTOR_TYPE == "CLICKHOUSE":
            endpoint = f"{BASE}/ui/applications-from-clickhouse"
            result_http = client.get(endpoint)
        else:
            logger.info(
                "test_get_applications_from_clickhouse requires CONNECTOR_TYPE=CLICKHOUSE, got CONNECTOR_TYPE=%s",
                CONNECTOR_TYPE,
            )
            return

        assert result_http.status_code == 200

        data = result_http.json()
        assert data is not None
        logger.info(f"\n── HTTP   {endpoint} ──")
        logger.info(json.dumps(data, indent=2))

    def test_get_application_sessions(self, local_db, client) -> None:
        application_id = "noa-trip-planner-mas"
        # start = to_epoch("2026-01-12 10:09:21")
        # end = to_epoch("2026-01-13 19:09:21")

        result_http = client.get(
            f"{BASE}/applications/{application_id}/sessions",
            params={
                # "start_time": start,
                # "end_time": end,
            },
        )
        assert result_http.status_code == 200
        data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/applications/{application_id}/sessions ──")
        logger.info(json.dumps(data, indent=2))

    def test_get_application_sessions_and_metrics(self, local_db, client) -> None:
        """Get sessions for an application, then fetch metrics for each session."""

        start_ts = time.perf_counter()
        application_id = "noa-trip-planner-mas"

        # Get all sessions for the application
        result_http = client.get(
            f"{BASE}/applications/{application_id}/sessions", params={}
        )
        assert result_http.status_code == 200
        sessions_data = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/applications/{application_id}/sessions ──")
        logger.info(json.dumps(sessions_data, indent=2))

        # Extract session IDs and fetch metrics for each
        sessions = (
            sessions_data.get("sessionList", [])
            if isinstance(sessions_data, dict)
            else sessions_data
        )
        logger.info(
            f"\n── Found {len(sessions)} sessions, fetching metrics for each ──"
        )

        # For brevity, only fetch metrics for the first few sessions
        for session in sessions[:3]:
            # Sessions returned by the endpoint use `sessionId` as the key.
            # Be defensive: accept dicts with `sessionId`, `id`, or `session_id`,
            # and also accept the session being a bare ID string.
            if isinstance(session, dict):
                session_id = (
                    session.get("sessionId")
                    or session.get("id")
                    or session.get("session_id")
                )
            else:
                session_id = session

            if not session_id:
                logger.warning(f"Session has no ID field: {session}")
                continue

            # Fetch metrics for this session
            metrics_response = client.get(f"{BASE}/metrics/sessions/{session_id}")
            assert metrics_response.status_code == 200
            metrics_data = metrics_response.json()
            logger.info(f"\n── Metrics for session {session_id} ──")
            logger.info(json.dumps(metrics_data, indent=2))

        elapsed = time.perf_counter() - start_ts
        logger.info("test_get_application_sessions took %.3fs", elapsed)

    def test_get_application_sessions_and_metrics_with_stateful_eval(
        self, local_db, client
    ) -> None:
        """Get sessions for an application, then fetch metrics for each session."""

        start_ts = time.perf_counter()
        application_id = "noa-trip-planner-mas"

        # Get all sessions for the application
        result_http = client.get(
            f"{BASE}/applications/{application_id}/sessions_with_stateful_eval",
            params={},
        )
        assert result_http.status_code == 200
        sessions_data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/sessions_with_stateful_eval ──"
        )
        logger.info(json.dumps(sessions_data, indent=2))

        # Extract session IDs and fetch metrics for each
        sessions = (
            sessions_data.get("sessionList", [])
            if isinstance(sessions_data, dict)
            else sessions_data
        )
        logger.info(
            f"\n── Found {len(sessions)} sessions, fetching metrics for each ──"
        )

        # Assert that at least one returned session contains a statefulEval
        found_stateful = False
        if isinstance(sessions, list):
            for sess in sessions:
                if isinstance(sess, dict):
                    se = sess.get("statefulEval")
                    if isinstance(se, dict) and se.get("name") == "trajectory_score":
                        found_stateful = True
                        break

        assert found_stateful, (
            "Expected at least one session with statefulEval.name == 'trajectory_score'"
        )

        elapsed = time.perf_counter() - start_ts
        logger.info(
            "test_get_application_sessions_with_stateful_eval took %.3fs",
            elapsed,
        )

    def test_get_application_sessions_and_metrics_with_stateful_eval_with_time_range(
        self, local_db, client
    ) -> None:
        """Same as the simple test, but passing a valid start/end time range.

        The endpoint accepts ``start_time``/``end_time`` as Unix-epoch strings.
        A tight window is used so only a handful of sessions fall inside the
        range, while still exercising the time-range filtering path and keeping
        the ``statefulEval`` assertion valid.
        """

        start_ts = time.perf_counter()
        application_id = "noa-trip-planner-mas"

        # Tight 3-minute window that brackets a small cluster of sessions, all
        # of which carry a ``trajectory_score`` stateful eval.
        start = to_epoch("2025-12-19 17:02:00")
        end = to_epoch("2025-12-19 17:05:00")

        result_http = client.get(
            f"{BASE}/applications/{application_id}/sessions_with_stateful_eval",
            params={
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        sessions_data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/sessions_with_stateful_eval"
            f" (start={start}, end={end}) ──"
        )
        logger.info(json.dumps(sessions_data, indent=2))

        # Extract session IDs and fetch metrics for each
        sessions = (
            sessions_data.get("sessionList", [])
            if isinstance(sessions_data, dict)
            else sessions_data
        )
        logger.info(
            f"\n── Found {len(sessions)} sessions, fetching metrics for each ──"
        )

        # The tight window should return only a few sessions, not the full set.
        assert isinstance(sessions, list)
        assert 0 < len(sessions) <= 10, (
            f"Expected only a few sessions in the time range, got {len(sessions)}"
        )

        # Assert that at least one returned session contains a statefulEval
        found_stateful = False
        if isinstance(sessions, list):
            for sess in sessions:
                if isinstance(sess, dict):
                    se = sess.get("statefulEval")
                    if isinstance(se, dict) and se.get("name") == "trajectory_score":
                        found_stateful = True
                        break

        assert found_stateful, (
            "Expected at least one session with statefulEval.name == 'trajectory_score'"
        )

        elapsed = time.perf_counter() - start_ts
        logger.info(
            "test_get_application_sessions_with_stateful_eval_with_time_range took %.3fs",
            elapsed,
        )

    def test_get_application_sessions_and_metrics_with_stateful_eval_with_time_range_02(
        self, local_db, client
    ) -> None:
        """Exercise the ``sessions_with_stateful_eval`` endpoint with a specific time range."""

        start_ts = time.perf_counter()
        application_id = "noa-trip-planner-mas"

        start = "1767285027"
        end = "1782830720"

        result_http = client.get(
            f"{BASE}/applications/{application_id}/sessions_with_stateful_eval",
            params={
                "start_time": start,
                "end_time": end,
            },
        )
        assert result_http.status_code == 200
        sessions_data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/sessions_with_stateful_eval"
            f" (start={start}, end={end}) ──"
        )
        logger.info(json.dumps(sessions_data, indent=2))

        # Extract session IDs and fetch metrics for each
        sessions = (
            sessions_data.get("sessionList", [])
            if isinstance(sessions_data, dict)
            else sessions_data
        )
        logger.info(
            f"\n── Found {len(sessions)} sessions, fetching metrics for each ──"
        )

        # Assert that at least one returned session contains a statefulEval
        found_stateful = False
        if isinstance(sessions, list):
            for sess in sessions:
                if isinstance(sess, dict):
                    se = sess.get("statefulEval")
                    if isinstance(se, dict) and se.get("name") == "trajectory_score":
                        found_stateful = True
                        break

        assert found_stateful, (
            "Expected at least one session with statefulEval.name == 'trajectory_score'"
        )

        elapsed = time.perf_counter() - start_ts
        logger.info(
            "test_get_application_sessions_with_stateful_eval_with_time_range took %.3fs",
            elapsed,
        )

    def test_get_application_sessions_and_metrics_with_stateful_eval_with_semantic_group(
        self, local_db, client
    ) -> None:
        """Same as the single-query test, but scoped to a single semantic group.

        The endpoint accepts ``semantic_group_id`` (the ``id`` property of a
        ``SemanticGroup``). When provided, only sessions that belong to that
        group are returned, so the result must be a strict subset of the
        unfiltered call while still containing ``trajectory_score`` evals.
        """

        start_ts = time.perf_counter()
        application_id = "noa-trip-planner-mas"
        semantic_group_id = "sg_internal_2736_c296fa14"

        # Baseline: unfiltered call returns the full set of sessions.
        unfiltered_http = client.get(
            f"{BASE}/applications/{application_id}/sessions_with_stateful_eval",
            params={},
        )
        assert unfiltered_http.status_code == 200
        unfiltered_data = unfiltered_http.json()
        unfiltered_sessions = (
            unfiltered_data.get("sessionList", [])
            if isinstance(unfiltered_data, dict)
            else unfiltered_data
        )

        # Filtered call: scoped to a single semantic group.
        result_http = client.get(
            f"{BASE}/applications/{application_id}/sessions_with_stateful_eval",
            params={
                "semantic_group_id": semantic_group_id,
            },
        )
        assert result_http.status_code == 200
        sessions_data = result_http.json()
        logger.info(
            f"\n── HTTP   {BASE}/applications/{application_id}/sessions_with_stateful_eval"
            f" (semantic_group_id={semantic_group_id}) ──"
        )
        logger.info(json.dumps(sessions_data, indent=2))

        # Extract session IDs and fetch metrics for each
        sessions = (
            sessions_data.get("sessionList", [])
            if isinstance(sessions_data, dict)
            else sessions_data
        )
        logger.info(
            f"\n── Found {len(sessions)} sessions, fetching metrics for each ──"
        )

        # Filtering by semantic group must return a non-empty, strict subset of
        # the unfiltered result.
        assert isinstance(sessions, list)
        assert 0 < len(sessions) < len(unfiltered_sessions), (
            f"Expected the semantic-group filter to return a strict subset, got "
            f"{len(sessions)} of {len(unfiltered_sessions)} sessions"
        )

        # Assert that at least one returned session contains a statefulEval
        found_stateful = False
        if isinstance(sessions, list):
            for sess in sessions:
                if isinstance(sess, dict):
                    se = sess.get("statefulEval")
                    if isinstance(se, dict) and se.get("name") == "trajectory_score":
                        found_stateful = True
                        break

        assert found_stateful, (
            "Expected at least one session with statefulEval.name == 'trajectory_score'"
        )

        elapsed = time.perf_counter() - start_ts
        logger.info(
            "test_get_application_sessions_with_stateful_eval_with_semantic_group took %.3fs",
            elapsed,
        )

    def test_get_application_sessions_with_stateful_eval_cache_impact(
        self, local_db, client
    ) -> None:
        """Call the single-query endpoint three times to inspect cache impact."""

        application_id = "noa-trip-planner-mas"
        endpoint = f"{BASE}/applications/{application_id}/sessions_with_stateful_eval"

        start_ts_01 = time.perf_counter()
        result_http_01 = client.get(endpoint, params={})
        elapsed_01 = time.perf_counter() - start_ts_01
        assert result_http_01.status_code == 200
        data_01 = result_http_01.json()
        logger.info(f"\n── HTTP 01 (expected cache MISS) {endpoint} ──")
        logger.info(json.dumps(data_01, indent=2))
        logger.info(
            "test_get_application_sessions_with_stateful_eval 01 took %.3fs",
            elapsed_01,
        )

        start_ts_02 = time.perf_counter()
        result_http_02 = client.get(endpoint, params={})
        elapsed_02 = time.perf_counter() - start_ts_02
        assert result_http_02.status_code == 200
        data_02 = result_http_02.json()
        logger.info(f"\n── HTTP 02 (expected cache HIT)  {endpoint} ──")
        logger.info(json.dumps(data_02, indent=2))
        logger.info(
            "test_get_application_sessions_with_stateful_eval 02 took %.3fs",
            elapsed_02,
        )

        start_ts_03 = time.perf_counter()
        result_http_03 = client.get(endpoint, params={})
        elapsed_03 = time.perf_counter() - start_ts_03
        assert result_http_03.status_code == 200
        data_03 = result_http_03.json()
        logger.info(f"\n── HTTP 03 (expected cache HIT)  {endpoint} ──")
        logger.info(json.dumps(data_03, indent=2))
        logger.info(
            "test_get_application_sessions_with_stateful_eval 03 took %.3fs",
            elapsed_03,
        )

        sessions_01 = data_01.get("sessionList", [])
        sessions_02 = data_02.get("sessionList", [])
        sessions_03 = data_03.get("sessionList", [])

        assert isinstance(sessions_01, list)
        assert isinstance(sessions_02, list)
        assert isinstance(sessions_03, list)

        # Response payload should be stable across cached and uncached calls.
        assert data_01 == data_02 == data_03

        # The average cached calls should be faster than the first uncached call.
        avg_cached = (elapsed_02 + elapsed_03) / 2
        assert avg_cached < elapsed_01, (
            f"Average cached time ({avg_cached:.3f}s) should be lower than first "
            f"uncached call ({elapsed_01:.3f}s)"
        )

        logger.info("#" * 80)
        logger.info(
            "test_get_application_sessions_with_stateful_eval 01 took %.3fs",
            elapsed_01,
        )
        logger.info(
            "test_get_application_sessions_with_stateful_eval 02 took %.3fs",
            elapsed_02,
        )
        logger.info(
            "test_get_application_sessions_with_stateful_eval 03 took %.3fs",
            elapsed_03,
        )
        logger.info("#" * 80)
