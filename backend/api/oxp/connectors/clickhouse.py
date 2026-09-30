#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ClickHouse connector using *clickhouse-connect*."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from oxp.connectors.base import Connector

logger = logging.getLogger(__name__)


class ClickHouseConnector(Connector):
    """Manages a ClickHouse connection via clickhouse-connect."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "",
        database: str = "default",
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database
        self._client: Any = None  # clickhouse_connect.Client

    # ── lifecycle ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        import clickhouse_connect

        self._client = clickhouse_connect.get_client(
            host=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            database=self._database,
            autogenerate_session_id=False,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.query("SELECT 1")
            return True
        except Exception as exc:
            logger.warning("ClickHouse connection check failed: %s", exc)
            return False

    # ── query execution ───────────────────────────────────────────────────

    def execute(self, query: Any, params: Optional[Dict[str, Any]] = None) -> Any:
        self.ensure_connected()

        # If the query is a SQLAlchemy Select/TextClause, compile it to a
        # plain SQL string with all bind parameters inlined.
        if not isinstance(query, str):
            from sqlalchemy.dialects import postgresql  # closest to ClickHouse syntax

            try:
                compiled = query.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
                query = str(compiled)
            except Exception:
                query = str(query)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Executing query: \n***********************\n%s",
                query,
            )

        result = self._client.query(query, parameters=params or {})
        return result.result_rows

    def execute_command(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> None:
        """Execute a DDL/DML command (INSERT, DELETE, etc.)."""
        self.ensure_connected()
        self._client.command(command, parameters=params or {})
