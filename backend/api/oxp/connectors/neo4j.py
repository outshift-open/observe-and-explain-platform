#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Neo4j connector using *neo4j-driver*."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import neo4j.time
from neo4j import GraphDatabase

from oxp.connectors.base import Connector

logger = logging.getLogger(__name__)


SEMANTICGROUP_NODE_CHILDREN_NODES = "childrenNodes"
SEMANTICGROUP_NODE_GROUP_NAME = "groupName"
SEMANTICGROUP_NODE_GROUP_SUMMARY = "groupSummary"
SEMANTICGROUP_NODE_ID = "id"
SEMANTICGROUP_NODE_N_SESSIONS = "nSessions"
SEMANTICGROUP_NODE_SESSION_IDS = "sessionIds"
SEMANTICGROUP_NODE_MEDIOID_SESSION_ID = "medioidSessionId"
SEMANTICGROUP_NODE_SPLIT_DISTANCE = "splitDistance"
SEMANTICGROUP_NODE_SEMANTICGROUP_ID = "semanticgroupId"
SEMANTICGROUP_NODE_OVERALL_QUALITY = "overallQuality"
SEMANTICGROUP_NODE_OVERALL_RELIABILITY = "overallReliability"
SEMANTICGROUP_NODE_OVERALL_PERFORMANCE = "overallPerformance"


def _convert_neo4j_types(value: Any) -> Any:
    """Recursively convert Neo4j temporal types to Python standard types."""
    if isinstance(value, neo4j.time.DateTime):
        return value.to_native()
    if isinstance(value, neo4j.time.Date):
        return date(value.year, value.month, value.day)
    if isinstance(value, neo4j.time.Time):
        return value.to_native()
    if isinstance(value, neo4j.time.Duration):
        return timedelta(
            days=value.months_days_seconds[1],
            seconds=value.months_days_seconds[2],
        )
    if isinstance(value, dict):
        return {k: _convert_neo4j_types(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert_neo4j_types(v) for v in value]
    return value


def _to_cypher_literal(value: Any) -> str:
    """Best-effort literal rendering for debug logs only."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return repr(value.isoformat())
    if isinstance(value, dict):
        parts = ", ".join(f"{k}: {_to_cypher_literal(v)}" for k, v in value.items())
        return "{" + parts + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_to_cypher_literal(v) for v in value) + "]"
    return repr(str(value))


def _render_query_with_params(query: str, params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return query

    rendered_query = query
    for key in sorted(params.keys(), key=len, reverse=True):
        pattern = re.compile(rf"\${re.escape(key)}(?![A-Za-z0-9_])")
        rendered_query = pattern.sub(_to_cypher_literal(params[key]), rendered_query)
    return rendered_query


class Neo4JConnector(Connector):
    """Manages a Neo4J connection via neo4j-driver."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7687,
        username: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database
        self._client: Any = None  # neo4j.Driver

    # ── lifecycle ─────────────────────────────────────────────────────────

    @property
    def _uri(self) -> str:
        """Build the Neo4j bolt URI, handling hosts that already contain a scheme and/or port."""
        host = self._host
        # If host already looks like a full URI (e.g. bolt://host:7687), parse it.
        if "://" in host:
            parsed = urlparse(host)
            scheme = parsed.scheme or "bolt"
            hostname = parsed.hostname or "localhost"
            port = parsed.port or self._port
            return f"{scheme}://{hostname}:{port}"
        return f"bolt://{host}:{self._port}"

    def connect(self) -> None:
        self._client = GraphDatabase.driver(
            self._uri,
            auth=(self._username, self._password),
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.verify_connectivity()
            return True
        except Exception as exc:
            logger.warning("Neo4j connection check failed: %s", exc)
            return False

    # ── query execution ───────────────────────────────────────────────────

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.ensure_connected()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Executing query:\n***********************\n%s",
                _render_query_with_params(query, params),
            )
        with self._client.session(database=self._database) as session:
            result = session.run(query, parameters=params or {})
            return [_convert_neo4j_types(record.data()) for record in result]

    def execute_command(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> None:
        """Execute a write command (CREATE, MERGE, DELETE, etc.)."""
        self.ensure_connected()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Executing command:\n***********************\n%s",
                _render_query_with_params(command, params),
            )
        with self._client.session(database=self._database) as session:
            session.run(command, parameters=params or {}).consume()

    @property
    def driver(self):
        """Return the raw neo4j Driver so providers can open sessions directly."""
        self.ensure_connected()
        return self._client
