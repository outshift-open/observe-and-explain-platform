#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared FastAPI dependencies for the OXP API."""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Generator
from urllib.parse import urlparse

try:
    from fastapi import Path as _FastAPIPath
except ModuleNotFoundError:
    _FastAPIPath = None  # type: ignore[assignment]

try:
    import redis as redis_lib
except ModuleNotFoundError:
    redis_lib = None

from oxp.connectors.base import Connector
from oxp.connectors.clickhouse import ClickHouseConnector
from oxp.connectors.neo4j import Neo4JConnector
from oxp.connectors.sqlalchemy import SQLAlchemyConnector
from oxp.core.config import settings

logger = logging.getLogger(__name__)

if _FastAPIPath is not None:
    ApplicationName = Annotated[
        str,
        _FastAPIPath(
            description="MAS application name (slug)",
            pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$",
        ),
    ]
else:
    ApplicationName = str  # type: ignore[misc]

# ── Singleton connectors ─────────────────────────────────────────────────────
# One engine/driver is created on first use and reused across all requests.
# This avoids the overhead of creating and disposing a full SQLAlchemy Engine
# (thread pool, dialect, connection pool) on every single HTTP request.

# _db_connector: ClickHouseConnector | None = None
_db_connector: SQLAlchemyConnector | None = None
_neo4j_connector: Neo4JConnector | None = None
_redis_client: Any | None = None


def _normalize_neo4j_host_port(host: str, port: int) -> tuple[str, int]:
    """Accept host values with optional scheme/port and return normalized parts."""
    if "://" in host:
        parsed = urlparse(host)
        return parsed.hostname or "localhost", parsed.port or port
    if ":" in host:
        hostname, _, port_str = host.rpartition(":")
        try:
            return hostname or "localhost", int(port_str)
        except ValueError:
            return host, port
    return host, port


def _get_db_singleton() -> ClickHouseConnector:
    """Return the singleton ClickHouse connector, creating it on first call."""
    global _db_connector
    if _db_connector is None:
        _db_connector = ClickHouseConnector(
            host=os.getenv("CLICKHOUSE_HOST", settings.CLICKHOUSE_HOST),
            port=int(os.getenv("CLICKHOUSE_PORT", str(settings.CLICKHOUSE_PORT))),
            username=(os.getenv("CLICKHOUSE_USERNAME") or settings.CLICKHOUSE_USERNAME),
            password=os.getenv("CLICKHOUSE_PASSWORD", settings.CLICKHOUSE_PASSWORD),
            database=os.getenv("CLICKHOUSE_DATABASE", settings.CLICKHOUSE_DATABASE),
        )
        _db_connector.connect()
        logger.info("ClickHouse singleton connector initialised")
    return _db_connector


def _get_neo4j_singleton() -> Neo4JConnector:
    """Return the singleton Neo4j connector, creating it on first call."""
    global _neo4j_connector
    if _neo4j_connector is None:
        host_raw = (
            os.getenv("NEO4J_URI") or os.getenv("NEO4J_HOST") or settings.NEO4J_HOST
        )
        try:
            default_port = int(os.getenv("NEO4J_PORT", ""))
        except ValueError:
            default_port = settings.NEO4J_PORT

        host, port = _normalize_neo4j_host_port(host_raw, default_port)
        _neo4j_connector = Neo4JConnector(
            host=host,
            port=port,
            username=(os.getenv("NEO4J_USERNAME") or settings.NEO4J_USERNAME),
            password=(os.getenv("NEO4J_PASSWORD") or settings.NEO4J_PASSWORD),
            database=(os.getenv("NEO4J_DATABASE") or settings.NEO4J_DATABASE),
        )
        _neo4j_connector.connect()
        logger.info("Neo4j singleton connector initialised")
    return _neo4j_connector


def _get_redis_singleton() -> Any:
    """Return the singleton Redis client, creating it on first call."""
    global _redis_client
    if redis_lib is None:
        raise RuntimeError(
            "Redis dependency is not installed. Install 'redis' to use get_redis()."
        )
    if _redis_client is None:
        _redis_client = redis_lib.Redis.from_url(
            settings.CACHE_REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
        )
        logger.info("Redis singleton client initialised — %s", settings.CACHE_REDIS_URL)
    return _redis_client


def get_db() -> Generator[Connector, None, None]:
    """FastAPI dependency that provides the shared SQLAlchemy connector."""
    yield _get_db_singleton()


def get_neo4j_db() -> Generator[Connector, None, None]:
    """FastAPI dependency that provides the shared Neo4j connector."""
    yield _get_neo4j_singleton()


def get_neo4j_connector() -> Connector:
    """Return the shared Neo4j connector configured from API settings/env."""
    return _get_neo4j_singleton()


def get_redis() -> Any:
    """FastAPI dependency that provides the shared Redis client."""
    return _get_redis_singleton()


def close_all() -> None:
    """Dispose singleton connectors (call during app shutdown)."""
    global _db_connector, _neo4j_connector, _redis_client
    if _db_connector is not None:
        _db_connector.close()
        _db_connector = None
        logger.info("ClickHouse singleton connector closed")
    if _neo4j_connector is not None:
        _neo4j_connector.close()
        _neo4j_connector = None
        logger.info("Neo4j singleton connector closed")
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
        logger.info("Redis singleton client closed")
