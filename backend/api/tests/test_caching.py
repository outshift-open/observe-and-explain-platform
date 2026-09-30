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
import time
from datetime import datetime, timezone

import pytest

import fakeredis
import redis as redis_lib
from dotenv import load_dotenv

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.connectors.neo4j import Neo4JConnector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_redis
from fastapi.testclient import TestClient

load_dotenv()

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ── Neo4j connector ──────────────────────────────────────────────────────────

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

        _connector = Neo4JConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )
        _connector.connect()
        logger.info(
            "Using Neo4j connector — %s:%s/%s",
            host,
            port,
            database,
        )
        if not _connector.is_connected():
            raise RuntimeError(
                "Neo4j connection/authentication failed for tests. "
                "Set valid NEO4J_* environment variables."
            )
    return _connector


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialise the Neo4j connector once for the module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture()
def local_db():
    """Provide the shared Neo4JConnector for the test database."""
    return _get_connector()


def _make_redis_client():
    """Return a real Redis client or FakeRedis depending on the environment.

    Set ``CACHE_USE_FAKE_REDIS=true`` (or ``1``) to use an in-process FakeRedis.
    Leave it unset to use the real Redis instance,
    configured via ``CACHE_REDIS_URL`` (default: ``redis://localhost:6379/0``).
    """
    if os.environ.get("CACHE_USE_FAKE_REDIS", "").lower() in ("0", "false", "no"):
        from oxp.core.config import settings

        logger.info("Using real Redis — %s", settings.CACHE_REDIS_URL)
        return redis_lib.Redis.from_url(settings.CACHE_REDIS_URL, decode_responses=True)
    logger.info("Using FakeRedis (in-memory)")
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(local_db):
    """Return a FastAPI ``TestClient`` with the DB and Redis dependencies overridden."""
    redis_client = _make_redis_client()
    app.dependency_overrides[get_db] = lambda: local_db
    app.dependency_overrides[get_redis] = lambda: redis_client
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
    def test_invalidate_cache_with_fake_redis_client(self, client) -> None:
        """DELETE /cache removes all cache:* keys and returns the correct count."""
        redis_client = fakeredis.FakeRedis(decode_responses=True)
        client.delete(f"{BASE}/cache")

        # Pre-populate a few cache keys directly so we have a known state.
        redis_client.set("cache:test:key1", "value1")
        redis_client.set("cache:test:key2", "value2")
        redis_client.set("cache:test:key3", "value3")
        # Also add a non-cache key that must NOT be deleted.
        redis_client.set("other:key", "untouched")

        # Override the Redis dependency to use our pre-populated instance.
        app.dependency_overrides[get_redis] = lambda: redis_client

        response = client.delete(f"{BASE}/cache")
        assert response.status_code == 200, response.text

        data = response.json()
        logger.info("invalidate_cache response: %s", data)
        assert data["deleted"] == 3
        assert "3" in data["message"]

        # All cache keys must be gone.
        assert redis_client.keys("cache:*") == []
        # Non-cache key must still be present.
        assert redis_client.get("other:key") == "untouched"

        # Second call with no cache keys must return deleted=0.
        response2 = client.delete(f"{BASE}/cache")
        assert response2.status_code == 200
        assert response2.json()["deleted"] == 0

    def test_get_applications_with_cache(self, local_db, client) -> None:
        client.delete(f"{BASE}/cache")

        start_ts_01 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_01 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications ──")
        logger.info(json.dumps(data_01, indent=2))
        assert "applications" in data_01
        assert isinstance(data_01["applications"], list)
        elapsed_01 = time.perf_counter() - start_ts_01
        logger.info("test_get_applications took %.3fs", elapsed_01)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_01)

        start_ts_02 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_02 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications/ ──")
        logger.info(json.dumps(data_02, indent=2))
        assert "applications" in data_02
        assert isinstance(data_02["applications"], list)
        elapsed_02 = time.perf_counter() - start_ts_02
        logger.info("test_get_applications took %.3fs", elapsed_02)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_02)

        start_ts_03 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_03 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications/ ──")
        logger.info(json.dumps(data_03, indent=2))
        assert "applications" in data_03
        assert isinstance(data_03["applications"], list)
        elapsed_03 = time.perf_counter() - start_ts_03
        logger.info("test_get_applications took %.3fs", elapsed_03)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_03)

        start_ts_04 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_04 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications/ ──")
        logger.info(json.dumps(data_04, indent=2))
        assert "applications" in data_04
        assert isinstance(data_04["applications"], list)
        elapsed_04 = time.perf_counter() - start_ts_04
        logger.info("test_get_applications took %.3fs", elapsed_04)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_04)

        logger.info("#" * 80)

        # ── Call 5: same params as call 4 → should HIT the cache ─────────────
        start_ts_05 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        result_http.json()
        elapsed_05 = time.perf_counter() - start_ts_05
        logger.info(f"\n── HTTP 05 (expected cache HIT)  {BASE}/ui/applications/ ──")
        logger.info("test_get_applications 05 took %.3fs", elapsed_05)
        assert elapsed_05 < elapsed_04, (
            f"Call 05 ({elapsed_05:.3f}s) should be faster than call 04 ({elapsed_04:.3f}s) — cache HIT expected"
        )

        logger.info("#" * 80)

        # ── Call 6: wait TTL+5s so cache expires, then call → should MISS ────

        wait_seconds = settings.CACHE_TTL_SECONDS + 5
        logger.info(
            "Waiting %ds for cache to expire (TTL=%ds)…",
            wait_seconds,
            settings.CACHE_TTL_SECONDS,
        )
        for i in range(wait_seconds):
            time.sleep(1)
            print(".", end="", flush=True)
        print()  # newline after dots

        start_ts_06 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        result_http.json()
        elapsed_06 = time.perf_counter() - start_ts_06
        logger.info(f"\n── HTTP 06 (expected cache MISS) {BASE}/ui/applications/ ──")
        logger.info("test_get_applications 06 took %.3fs", elapsed_06)
        assert elapsed_06 > elapsed_05, (
            f"Call 06 ({elapsed_06:.3f}s) should be slower than call 05 ({elapsed_05:.3f}s) — cache MISS expected"
        )

        logger.info("#" * 80)

        # ── Call 7: immediately after 06 → cache was just repopulated, HIT ───
        start_ts_07 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        result_http.json()
        elapsed_07 = time.perf_counter() - start_ts_07
        logger.info(f"\n── HTTP 07 (expected cache HIT)  {BASE}/ui/applications/ ──")
        logger.info("test_get_applications 07 took %.3fs", elapsed_07)
        assert elapsed_07 < elapsed_06, (
            f"Call 07 ({elapsed_07:.3f}s) should be faster than call 06 ({elapsed_06:.3f}s) — cache HIT expected"
        )

        logger.info("#" * 80)

        logger.info(
            "test_get_applications 01 took %.3fs (cache MISS — first request)",
            elapsed_01,
        )
        logger.info("test_get_applications 02 took %.3fs (cache HIT)", elapsed_02)
        logger.info("test_get_applications 03 took %.3fs (cache HIT)", elapsed_03)
        logger.info(
            "test_get_applications 04 took %.3fs (cache MISS — request with different params)",
            elapsed_04,
        )
        logger.info("test_get_applications 05 took %.3fs (cache HIT)", elapsed_05)
        logger.info(
            "test_get_applications 06 took %.3fs (cache MISS — expired)", elapsed_06
        )
        logger.info("test_get_applications 07 took %.3fs (cache HIT)", elapsed_07)

        logger.info("#" * 80)

    def test_invalidate_cache(self, client) -> None:
        client.delete(f"{BASE}/cache")

        start_ts_01 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_01 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications ──")
        logger.info(json.dumps(data_01, indent=2))
        assert "applications" in data_01
        assert isinstance(data_01["applications"], list)
        elapsed_01 = time.perf_counter() - start_ts_01
        logger.info("test_get_applications took %.3fs", elapsed_01)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_01)

        start_ts_02 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_02 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications/ ──")
        logger.info(json.dumps(data_02, indent=2))
        assert "applications" in data_02
        assert isinstance(data_02["applications"], list)
        elapsed_02 = time.perf_counter() - start_ts_02
        logger.info("test_get_applications took %.3fs", elapsed_02)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_02)

        start_ts_03 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 10,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_03 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications/ ──")
        logger.info(json.dumps(data_03, indent=2))
        assert "applications" in data_03
        assert isinstance(data_03["applications"], list)
        elapsed_03 = time.perf_counter() - start_ts_03
        logger.info("test_get_applications took %.3fs", elapsed_03)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_03)

        start_ts_04 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        data_04 = result_http.json()
        logger.info(f"\n── HTTP   {BASE}/ui/applications/ ──")
        logger.info(json.dumps(data_04, indent=2))
        assert "applications" in data_04
        assert isinstance(data_04["applications"], list)
        elapsed_04 = time.perf_counter() - start_ts_04
        logger.info("test_get_applications took %.3fs", elapsed_04)

        logger.info("#" * 80)

        logger.info("test_get_applications took %.3fs", elapsed_04)

        logger.info("#" * 80)

        # ── Call 5: same params as call 4 → should HIT the cache ─────────────
        start_ts_05 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        result_http.json()
        elapsed_05 = time.perf_counter() - start_ts_05
        logger.info(f"\n── HTTP 05 (expected cache HIT)  {BASE}/ui/applications/ ──")
        logger.info("test_get_applications 05 took %.3fs", elapsed_05)
        assert elapsed_05 < elapsed_04, (
            f"Call 05 ({elapsed_05:.3f}s) should be faster than call 04 ({elapsed_04:.3f}s) — cache HIT expected"
        )

        logger.info("#" * 80)

        # ── Call 6: wait TTL+5s so cache expires, then call → should MISS ────

        logger.info("Triggering manual cache invalidation!")
        response = client.delete(f"{BASE}/cache")
        assert response.status_code == 200, response.text

        start_ts_06 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        result_http.json()
        elapsed_06 = time.perf_counter() - start_ts_06
        logger.info(f"\n── HTTP 06 (expected cache MISS) {BASE}/ui/applications/ ──")
        logger.info("test_get_applications 06 took %.3fs", elapsed_06)
        assert elapsed_06 > elapsed_05, (
            f"Call 06 ({elapsed_06:.3f}s) should be slower than call 05 ({elapsed_05:.3f}s) — cache MISS expected"
        )

        logger.info("#" * 80)

        # ── Call 7: immediately after 06 → cache was just repopulated, HIT ───
        start_ts_07 = time.perf_counter()
        result_http = client.get(
            f"{BASE}/ui/applications/",
            params={
                "limit": 5,
                "offset": 0,
            },
        )
        assert result_http.status_code == 200
        result_http.json()
        elapsed_07 = time.perf_counter() - start_ts_07
        logger.info(f"\n── HTTP 07 (expected cache HIT)  {BASE}/ui/applications/ ──")
        logger.info("test_get_applications 07 took %.3fs", elapsed_07)
        assert elapsed_07 < elapsed_06, (
            f"Call 07 ({elapsed_07:.3f}s) should be faster than call 06 ({elapsed_06:.3f}s) — cache HIT expected"
        )

        logger.info("#" * 80)

        logger.info(
            "test_get_applications 01 took %.3fs (cache MISS — first request)",
            elapsed_01,
        )
        logger.info("test_get_applications 02 took %.3fs (cache HIT)", elapsed_02)
        logger.info("test_get_applications 03 took %.3fs (cache HIT)", elapsed_03)
        logger.info(
            "test_get_applications 04 took %.3fs (cache MISS — request with different params)",
            elapsed_04,
        )
        logger.info("test_get_applications 05 took %.3fs (cache HIT)", elapsed_05)
        logger.info("Triggered manual cache invalidation!")
        logger.info(
            "test_get_applications 06 took %.3fs (cache MISS — manual invalidation)",
            elapsed_06,
        )
        logger.info("test_get_applications 07 took %.3fs (cache HIT)", elapsed_07)

        logger.info("#" * 80)
