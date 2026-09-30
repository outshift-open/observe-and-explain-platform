#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ClickHouse implementation of :class:`OtelRepository`."""

from __future__ import annotations

from typing import Any, Dict, Optional

import oxp.db.database as _db
from oxp.query_builders.types import Dialect
from oxp.repositories.otel_repository import OtelRepository


class ClickHouseOtelRepository(OtelRepository):
    """Queries OTEL traces via clickhouse-connect against a ClickHouse server."""

    @property
    def dialect(self) -> Dialect:
        return Dialect.CLICKHOUSE

    @property
    def _client(self):
        return _db.clickhouse_client

    # ── connection ───────────────────────────────────────────────────────

    def check_connection(self) -> None:
        if self._client is None:
            raise RuntimeError("ClickHouse client is not initialised")
        self._client.query("SELECT 1")

    # ── queries ──────────────────────────────────────────────────────────

    def _grouped_ids(
        self,
        column: str,
        start_dt: Optional[str],
        end_dt: Optional[str],
    ) -> list[dict]:
        conditions = [f"{column} != ''"]
        params: dict[str, str] = {}

        if start_dt is not None:
            conditions.append("Timestamp >= {start_dt:String}")
            params["start_dt"] = start_dt
        if end_dt is not None:
            conditions.append("Timestamp <= {end_dt:String}")
            params["end_dt"] = end_dt

        where = " AND ".join(conditions)
        sql = (
            f"SELECT {column} AS id, MIN(Timestamp) AS start_timestamp "
            f"FROM otel_traces "
            f"WHERE {where} "
            f"GROUP BY {column} "
            f"ORDER BY MIN(Timestamp) DESC"
        )

        result = self._client.query(sql, parameters=params)
        return [
            {"id": row[0], "start_timestamp": str(row[1])} for row in result.result_rows
        ]

    def session_ids(
        self,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
    ) -> list[dict]:
        return self._grouped_ids("session_id", start_dt, end_dt)

    def traces(
        self,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
        app_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["session_id != ''"]
        params: dict[str, Any] = {}

        if start_dt is not None:
            conditions.append("Timestamp >= {start_dt:String}")
            params["start_dt"] = start_dt
        if end_dt is not None:
            conditions.append("Timestamp <= {end_dt:String}")
            params["end_dt"] = end_dt
        if app_name is not None:
            conditions.append("application_id = {app_name:String}")
            params["app_name"] = app_name

        where = " AND ".join(conditions)
        sql = (
            f"SELECT trace_id, application_id, "
            f"MIN(Timestamp) AS start_time, MAX(Timestamp) AS end_time "
            f"FROM otel_traces "
            f"WHERE {where} "
            f"GROUP BY trace_id "
            f"ORDER BY MIN(Timestamp) DESC "
            f"LIMIT {{limit:UInt32}} OFFSET {{offset:UInt32}}"
        )
        params["limit"] = limit
        params["offset"] = offset

        result = self._client.query(sql, parameters=params)
        return [
            {
                "trace_id": row[0],
                "application_id": row[1],
                "start_time": str(row[2]),
                "end_time": str(row[3]),
            }
            for row in result.result_rows
        ]

    def application_ids(
        self,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return self._grouped_ids("application_id", start_dt, end_dt)

    # ── seeding ──────────────────────────────────────────────────────────

    def seed(self, csv_path: str) -> None:
        """No-op — ClickHouse is seeded via its init SQL script."""

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> list:
        """Execute an arbitrary SQL query and return result rows."""
        if self._client is None:
            raise RuntimeError("ClickHouse client is not initialised")
        result = self._client.query(query, parameters=params or {})
        return result.result_rows
