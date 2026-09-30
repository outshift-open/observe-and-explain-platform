#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""SQLite (SQLAlchemy) implementation of :class:`OtelRepository`."""

from __future__ import annotations

import csv
from typing import Any, Dict, Optional

from sqlalchemy import func, text

from oxp.connectors.sqlalchemy import SQLAlchemyConnector
from oxp.models.otel_traces import OXPBaseModel, OtelTrace
from oxp.query_builders.types import Dialect
from oxp.repositories.otel_repository import OtelRepository


def _get_engine(connector: SQLAlchemyConnector | None = None):
    """Return the SQLAlchemy engine from *connector* or the global default."""
    if connector is not None:
        return connector.engine
    from oxp.db.database import get_engine

    return get_engine()


def _get_session(connector: SQLAlchemyConnector | None = None):
    """Return a new SQLAlchemy session from *connector* or the global default."""
    if connector is not None:
        return connector.get_session()
    from oxp.db.database import get_session

    return get_session()


# ── Column name mapping: CSV header → OtelTrace model field ──────────────────

_CSV_FIELD_MAP = {
    "Timestamp": "timestamp",
    "TraceId": "trace_id",
    "SpanId": "span_id",
    "ParentSpanId": "parent_span_id",
    "TraceState": "trace_state",
    "SpanName": "span_name",
    "SpanKind": "span_kind",
    "ServiceName": "service_name",
    "ResourceAttributes": "resource_attributes",
    "ScopeName": "scope_name",
    "ScopeVersion": "scope_version",
    "SpanAttributes": "span_attributes",
    "Duration": "duration",
    "StatusCode": "status_code",
    "StatusMessage": "status_message",
    "Events.Timestamp": "events_timestamp",
    "Events.Name": "events_name",
    "Events.Attributes": "events_attributes",
    "Links.TraceId": "links_trace_id",
    "Links.SpanId": "links_span_id",
    "Links.TraceState": "links_trace_state",
    "Links.Attributes": "links_attributes",
    "session_id": "session_id",
    "agent_id": "agent_id",
    "application_id": "application_id",
}


class SqliteOtelRepository(OtelRepository):
    """Queries OTEL traces via SQLAlchemy against a local SQLite database."""

    @property
    def dialect(self) -> Dialect:
        return Dialect.SQLITE

    # ── connection ───────────────────────────────────────────────────────

    def check_connection(self) -> None:
        session = _get_session()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()

    # ── queries ──────────────────────────────────────────────────────────

    def _grouped_ids(
        self,
        column: str,
        start_dt: Optional[str],
        end_dt: Optional[str],
    ) -> list[dict]:
        col_attr = getattr(OtelTrace, column)
        session = _get_session()
        try:
            query = session.query(
                col_attr.label("id"),
                func.min(OtelTrace.timestamp).label("start_timestamp"),
            ).filter(col_attr != "")
            if start_dt is not None:
                query = query.filter(OtelTrace.timestamp >= start_dt)
            if end_dt is not None:
                query = query.filter(OtelTrace.timestamp <= end_dt)

            query = query.group_by(col_attr).order_by(
                func.min(OtelTrace.timestamp).desc()
            )

            return [
                {"id": row.id, "start_timestamp": row.start_timestamp}
                for row in query.all()
            ]
        finally:
            session.close()

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
        session = _get_session()
        try:
            query = session.query(
                OtelTrace.trace_id.label("trace_id"),
                OtelTrace.application_id.label("application_id"),
                func.min(OtelTrace.timestamp).label("start_time"),
                func.max(OtelTrace.timestamp).label("end_time"),
            ).filter(OtelTrace.session_id != "")
            if start_dt is not None:
                query = query.filter(OtelTrace.timestamp >= start_dt)
            if end_dt is not None:
                query = query.filter(OtelTrace.timestamp <= end_dt)
            if app_name is not None:
                query = query.filter(OtelTrace.application_id == app_name)

            query = (
                query.group_by(OtelTrace.trace_id)
                .order_by(func.min(OtelTrace.timestamp).desc())
                .limit(limit)
                .offset(offset)
            )

            return [
                {
                    "trace_id": row.trace_id,
                    "application_id": row.application_id,
                    "start_time": str(row.start_time),
                    "end_time": str(row.end_time),
                }
                for row in query.all()
            ]
        finally:
            session.close()

    def application_ids(
        self,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return self._grouped_ids("application_id", start_dt, end_dt)

    # ── seeding ──────────────────────────────────────────────────────────

    def seed(
        self, csv_path: str, *, connector: SQLAlchemyConnector | None = None
    ) -> None:
        engine = _get_engine(connector)
        OXPBaseModel.metadata.create_all(engine)

        session = _get_session(connector)
        try:
            if session.query(OtelTrace).count() > 0:
                return

            with open(csv_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows: list[dict] = []
                for i, raw_row in enumerate(reader):
                    # Row 0 after header is the ClickHouse type-hint row — skip it
                    if i == 0:
                        continue
                    row = {}
                    for csv_col, model_field in _CSV_FIELD_MAP.items():
                        value = raw_row.get(csv_col, "")
                        if model_field == "duration":
                            value = int(value) if value else 0
                        row[model_field] = value
                    rows.append(row)

            session.bulk_insert_mappings(OtelTrace, rows)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> list:
        """Execute an arbitrary SQL query and return result rows."""
        session = _get_session()
        try:
            result = session.execute(text(query), params or {})
            return result.fetchall()
        finally:
            session.close()
