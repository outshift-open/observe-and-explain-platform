#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **Sessions** feature domain.

Provides SQL queries (via SQLAlchemy Core) for the session-level
endpoints: session listing and span retrieval by session / type.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import column, func, select, table

from oxp.query_builders.types import Dialect

# ── per-backend table definitions ────────────────────────────────────────────

_ch_otel = table(
    "otel_traces",
    column("Timestamp"),
    column("SpanId"),
    column("SpanName"),
    column("SpanAttributes"),
    column("StatusCode"),
    column("Duration"),
    column("ParentSpanId"),
    column("ScopeName"),
    column("ServiceName"),
    column("session_id"),
    column("application_id"),
    column("agent_id"),
    column("Links.TraceId"),
    column("Links.SpanId"),
    column("Links.TraceState"),
    column("Links.Attributes"),
)

_sqlite_otel = table(
    "otel_traces",
    column("timestamp"),
    column("span_id"),
    column("span_name"),
    column("span_attributes"),
    column("status_code"),
    column("duration"),
    column("parent_span_id"),
    column("scope_name"),
    column("service_name"),
    column("session_id"),
    column("application_id"),
    column("agent_id"),
    column("links_trace_id"),
    column("links_span_id"),
    column("links_trace_state"),
    column("links_attributes"),
)


# ── helper ────────────────────────────────────────────────────────────────────


def _identity(expr):
    return expr


def _cols(dialect: Dialect):
    """Return (table, column-mapping) appropriate for *dialect*."""
    if dialect is Dialect.SQLITE:
        t = _sqlite_otel
        return dict(
            tbl=t,
            ts=t.c.timestamp,
            span_id=t.c.span_id,
            span_name=t.c.span_name,
            span_attributes=t.c.span_attributes,
            status_code=t.c.status_code,
            duration=t.c.duration,
            parent_span_id=t.c.parent_span_id,
            scope_name=t.c.scope_name,
            service_name=t.c.service_name,
            session_id=t.c.session_id,
            application_id=t.c.application_id,
            links_trace_id=t.c.links_trace_id,
            links_span_id=t.c.links_span_id,
            links_trace_state=t.c.links_trace_state,
            links_attributes=t.c.links_attributes,
            wrap=_identity,
        )
    t = _ch_otel
    return dict(
        tbl=t,
        ts=t.c.Timestamp,
        span_id=t.c.SpanId,
        span_name=t.c.SpanName,
        span_attributes=t.c.SpanAttributes,
        status_code=t.c.StatusCode,
        duration=t.c.Duration,
        parent_span_id=t.c.ParentSpanId,
        scope_name=t.c.ScopeName,
        service_name=t.c.ServiceName,
        session_id=t.c.session_id,
        application_id=t.c.application_id,
        links_trace_id=t.c["Links.TraceId"],
        links_span_id=t.c["Links.SpanId"],
        links_trace_state=t.c["Links.TraceState"],
        links_attributes=t.c["Links.Attributes"],
        wrap=func.toString,
    )


# ── public query builders ────────────────────────────────────────────────────


def list_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return ``(session_id, first_timestamp)`` for each session.

    Sorted by most-recent first.
    """
    c = _cols(dialect)

    stmt = (
        select(
            c["session_id"].label("session_id"),
            c["wrap"](func.min(c["ts"])).label("timestamp"),
        )
        .select_from(c["tbl"])
        .where(c["session_id"] != "")
        .group_by(c["session_id"])
        .order_by(func.min(c["ts"]).desc())
        .limit(limit)
        .offset(offset)
    )

    if start_time:
        stmt = stmt.where(c["ts"] >= start_time)
    if end_time:
        stmt = stmt.where(c["ts"] <= end_time)

    return stmt


def session_spans_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str] | None = None,
    span_types: list[str] | None = None,
    limit: int = 500,
    offset: int = 0,
    order: str = "asc",
):
    """Return all span attributes + metadata for given session(s) and/or type(s).

    *span_types* filters on the last segment of ``span_name`` (after the
    last ``"."``) — e.g. ``"llm"``, ``"tool"``, ``"agent"``, ``"chat"``.
    """
    c = _cols(dialect)

    wrap = c["wrap"]

    stmt = (
        select(
            c["span_id"].label("span_id"),
            c["session_id"].label("session_id"),
            c["span_name"].label("span_name"),
            wrap(c["ts"]).label("timestamp"),
            c["duration"].label("duration"),
            c["status_code"].label("status_code"),
            c["parent_span_id"].label("parent_span_id"),
            c["service_name"].label("service_name"),
            c["span_attributes"].label("span_attributes"),
            c["links_trace_id"].label("links_trace_id"),
            c["links_span_id"].label("links_span_id"),
            c["links_trace_state"].label("links_trace_state"),
            c["links_attributes"].label("links_attributes"),
        )
        .select_from(c["tbl"])
        .where(c["session_id"] != "")
    )

    if session_ids:
        stmt = stmt.where(c["session_id"].in_(session_ids))

    if span_types:
        # Filter spans whose name ends with one of the requested types.
        # e.g. span_name LIKE '%.llm' OR span_name LIKE '%.tool'
        type_conditions = [c["span_name"].like(f"%.{t}") for t in span_types]
        from sqlalchemy import or_

        stmt = stmt.where(or_(*type_conditions))

    col = c["ts"]
    stmt = (
        stmt.order_by(
            col.desc() if order == "desc" else col.asc(),
            c["span_id"].desc() if order == "desc" else c["span_id"].asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return stmt
