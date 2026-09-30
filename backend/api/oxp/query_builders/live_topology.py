#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **live topology** feature domain."""

from __future__ import annotations

from oxp.query_builders.types import Dialect
from typing import Optional

from sqlalchemy import (
    case,
    column,
    func,
    literal,
    literal_column,
    select,
    table,
    distinct,
)


_SESSION_EVENT_NAMES = (
    "topology.session.started",
    "topology.session.completed",
)

_AGENT_EVENT_NAMES = (
    "topology.node.started",
    "topology.node.completed",
)

_TOOL_EVENT_NAMES = (
    "tool.started",
    "tool.completed",
)

_ch_otel = table(
    "otel_logs",
    column("Timestamp"),
    column("SpanId"),
    column("Body"),
    column("LogAttributes"),
    column("ServiceName"),
    column("Duration"),
    column("ResourceAttributes"),
    column("ScopeName"),
    column("EventName"),
    column("application_id"),
    column("agent_id"),
)

_sqlite_otel = table(
    "otel_logs",
    column("timestamp"),
    column("span_id"),
    column("body"),
    column("log_attributes"),
    column("service_name"),
    column("duration"),
    column("resource_attributes"),
    column("scope_name"),
    column("event_name"),
    column("application_id"),
    column("agent_id"),
)

_ch_traces = table(
    "otel_traces",
    column("session_id"),
    column("application_id"),
)

_sqlite_traces = table(
    "otel_traces",
    column("session_id"),
    column("application_id"),
)


def _identity(expr):
    return expr


def _cols(dialect: str):
    """Return (table, column-mapping) appropriate for *dialect*."""
    if dialect == "sqlite":
        t = _sqlite_otel
        return dict(
            tbl=t,
            ts=t.c.timestamp,
            span_id=t.c.span_id,
            body=t.c.body,
            log_attributes=t.c.log_attributes,
            service_name=t.c.service_name,
            duration=t.c.duration,
            resource_attributes=t.c.resource_attributes,
            scope_name=t.c.scope_name,
            event_name=t.c.event_name,
            session_id=func.json_extract(t.c.log_attributes, literal('$."session.id"')),
            agent_name=func.json_extract(t.c.log_attributes, literal('$."agent.name"')),
            tool_name=func.json_extract(t.c.log_attributes, literal('$."tool.name"')),
            agent_id=t.c.agent_id,
            wrap=_identity,
        )
    else:
        t = _ch_otel
        return dict(
            tbl=t,
            ts=t.c.Timestamp,
            span_id=t.c.SpanId,
            body=t.c.Body,
            log_attributes=t.c.LogAttributes,
            service_name=t.c.ServiceName,
            duration=t.c.Duration,
            resource_attributes=t.c.ResourceAttributes,
            scope_name=t.c.ScopeName,
            event_name=t.c.EventName,
            session_id=literal_column("LogAttributes['session.id']"),
            agent_name=literal_column("LogAttributes['agent.name']"),
            tool_name=literal_column("LogAttributes['tool.name']"),
            agent_id=t.c.agent_id,
            wrap=_identity,
        )


_ALL_TOPOLOGY_EVENT_NAMES = (
    *_SESSION_EVENT_NAMES,
    *_AGENT_EVENT_NAMES,
    *_TOOL_EVENT_NAMES,
    "topology.edge.updated",
)


def get_topology_events_by_session(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_id: str,
):
    """Return all topology events for *session_id* ordered by timestamp ascending.

        Returns columns:
                ``(event_name, agent_name, tool_name, source_agent, target_agent,
                    edge_id, edge_kind, snapshot_version, timestamp, agent_input, tool_input,
                    tool_output)``

    Covers all event types needed to reconstruct the full runtime topology graph:
    - ``topology.session.started/completed`` — session lifecycle
    - ``topology.node.started/completed``    — agent execution
    - ``topology.edge.updated``              — agent handoffs (edges)
    - ``tool.started/completed``             — tool invocations
    """
    c = _cols(dialect)

    if dialect is Dialect.SQLITE:
        t = c["tbl"]
        source_agent = func.json_extract(
            t.c.log_attributes, literal('$."source.agent"')
        )
        target_agent = func.json_extract(
            t.c.log_attributes, literal('$."target.agent"')
        )
        edge_id = func.json_extract(t.c.log_attributes, literal('$."topology.edge.id"'))
        edge_kind = func.json_extract(
            t.c.log_attributes, literal('$."topology.edge.kind"')
        )
        snapshot_version = func.json_extract(
            t.c.log_attributes, literal('$."snapshot.version"')
        )
        agent_input = func.json_extract(t.c.log_attributes, literal('$."agent.input"'))
        tool_input = func.json_extract(t.c.log_attributes, literal('$."tool.input"'))
        tool_output = func.json_extract(t.c.log_attributes, literal('$."tool.output"'))
    else:
        source_agent = literal_column("LogAttributes['source.agent']")
        target_agent = literal_column("LogAttributes['target.agent']")
        edge_id = literal_column("LogAttributes['topology.edge.id']")
        edge_kind = literal_column("LogAttributes['topology.edge.kind']")
        snapshot_version = literal_column("LogAttributes['snapshot.version']")
        agent_input = literal_column("LogAttributes['agent.input']")
        tool_input = literal_column("LogAttributes['tool.input']")
        tool_output = literal_column("LogAttributes['tool.output']")

    stmt = (
        select(
            c["event_name"].label("event_name"),  # 0
            c["agent_name"].label("agent_name"),  # 1
            c["tool_name"].label("tool_name"),  # 2
            source_agent.label("source_agent"),  # 3
            target_agent.label("target_agent"),  # 4
            edge_id.label("edge_id"),  # 5
            edge_kind.label("edge_kind"),  # 6
            snapshot_version.label("snapshot_version"),  # 7
            c["ts"].label("timestamp"),  # 8
            agent_input.label("agent_input"),  # 9
            tool_input.label("tool_input"),  # 10
            tool_output.label("tool_output"),  # 11
        )
        .select_from(c["tbl"])
        .where(c["event_name"].in_(_ALL_TOPOLOGY_EVENT_NAMES))
        .where(c["session_id"] == session_id)
        .order_by(c["ts"].asc())
    )

    return stmt


def get_live_topology_sessions(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return ``(session_id, application_id, timestamp)`` for each session.

    Only rows with a session event name are considered.
    Sorted by most-recent session start first.
    """
    c = _cols(dialect)

    stmt = (
        select(
            c["session_id"].label("session_id"),
            c["wrap"](func.min(c["ts"])).label("timestamp"),
            func.sum(
                case(
                    (c["event_name"] == "topology.session.completed", 1),
                    else_=0,
                )
            ).label("has_completed"),
            c["wrap"](
                func.min(
                    case(
                        (c["event_name"] == "topology.session.completed", c["ts"]),
                        else_=None,
                    )
                )
            ).label("end_time"),
        )
        .select_from(c["tbl"])
        .where(c["session_id"] != "")
        .where(c["event_name"].in_(_SESSION_EVENT_NAMES))
        .group_by(c["session_id"])
        .order_by(func.min(c["ts"]).desc())
        .limit(limit)
        .offset(offset)
    )

    if start_time:
        stmt = stmt.where(c["ts"] >= start_time)
    if end_time:
        stmt = stmt.where(c["ts"] <= end_time)
    if application_name:
        if dialect == Dialect.SQLITE:
            stmt = stmt.where(_sqlite_otel.c.application_id == application_name)
        else:
            app_sessions = select(distinct(_ch_traces.c.session_id)).where(
                _ch_traces.c.application_id == application_name
            )
            stmt = stmt.where(c["session_id"].in_(app_sessions))

    return stmt


def get_orphan_live_topology_sessions(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    limit: int = 200,
):
    """Return candidate orphan sessions and their latest activity timestamp.

    Returns columns:
    ``(session_id, last_activity, started_count, completed_count)``

    A session is considered an orphan candidate when it has at least one
    ``topology.session.started`` event and no ``topology.session.completed`` event.

    ``last_activity`` is computed only from topology-domain events so unrelated
    session-scoped telemetry cannot keep a dead session artificially "recent".
    """
    c = _cols(dialect)

    started_count = func.sum(
        case(
            (c["event_name"] == "topology.session.started", 1),
            else_=0,
        )
    )
    completed_count = func.sum(
        case(
            (c["event_name"] == "topology.session.completed", 1),
            else_=0,
        )
    )

    return (
        select(
            c["session_id"].label("session_id"),
            c["wrap"](func.max(c["ts"])).label("last_activity"),
            started_count.label("started_count"),
            completed_count.label("completed_count"),
        )
        .select_from(c["tbl"])
        .where(c["session_id"] != "")
        .where(c["event_name"].in_(_ALL_TOPOLOGY_EVENT_NAMES))
        .group_by(c["session_id"])
        .having(started_count > 0)
        .having(completed_count == 0)
        .order_by(func.max(c["ts"]).desc())
        .limit(limit)
    )


def get_live_topology_agents(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return per-agent live execution aggregates.

    Returns columns:
    ``(agent_name, latest_start_time, started_count, completed_count, latest_end_time)``

    An agent is currently active when ``started_count > completed_count``.
    """
    c = _cols(dialect)

    stmt = (
        select(
            c["agent_name"].label("agent_name"),
            c["wrap"](
                func.max(
                    case(
                        (c["event_name"] == "topology.node.started", c["ts"]),
                        else_=None,
                    )
                )
            ).label("start_time"),
            func.sum(
                case(
                    (c["event_name"] == "topology.node.started", 1),
                    else_=0,
                )
            ).label("started_count"),
            func.sum(
                case(
                    (c["event_name"] == "topology.node.completed", 1),
                    else_=0,
                )
            ).label("completed_count"),
            c["wrap"](
                func.max(
                    case(
                        (c["event_name"] == "topology.node.completed", c["ts"]),
                        else_=None,
                    )
                )
            ).label("end_time"),
        )
        .select_from(c["tbl"])
        .where(c["agent_name"] != "")
        .where(c["event_name"].in_(_AGENT_EVENT_NAMES))
        .group_by(c["agent_name"])
        .order_by(func.max(c["ts"]).desc())
        .limit(limit)
        .offset(offset)
    )

    if start_time:
        stmt = stmt.where(c["ts"] >= start_time)
    if end_time:
        stmt = stmt.where(c["ts"] <= end_time)

    return stmt


def get_live_topology_tools(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return per-tool live execution aggregates.

    Returns columns:
    ``(tool_name, latest_start_time, started_count, completed_count, latest_end_time)``

    A tool is currently active when ``started_count > completed_count``.
    """
    c = _cols(dialect)

    stmt = (
        select(
            c["tool_name"].label("tool_name"),
            c["wrap"](
                func.max(
                    case(
                        (c["event_name"] == "tool.started", c["ts"]),
                        else_=None,
                    )
                )
            ).label("start_time"),
            func.sum(
                case(
                    (c["event_name"] == "tool.started", 1),
                    else_=0,
                )
            ).label("started_count"),
            func.sum(
                case(
                    (c["event_name"] == "tool.completed", 1),
                    else_=0,
                )
            ).label("completed_count"),
            c["wrap"](
                func.max(
                    case(
                        (c["event_name"] == "tool.completed", c["ts"]),
                        else_=None,
                    )
                )
            ).label("end_time"),
        )
        .select_from(c["tbl"])
        .where(c["tool_name"] != "")
        .where(c["event_name"].in_(_TOOL_EVENT_NAMES))
        .group_by(c["tool_name"])
        .order_by(func.max(c["ts"]).desc())
        .limit(limit)
        .offset(offset)
    )

    if start_time:
        stmt = stmt.where(c["ts"] >= start_time)
    if end_time:
        stmt = stmt.where(c["ts"] <= end_time)

    return stmt


def get_live_topology_tool_inference_events(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Return recent agent events with payloads for tool inference fallback.

    Returns columns:
    ``(agent_name, timestamp, agent_input)``
    """
    c = _cols(dialect)

    if dialect is Dialect.SQLITE:
        agent_input = func.json_extract(
            c["tbl"].c.log_attributes, literal('$."agent.input"')
        )
    else:
        agent_input = literal_column("LogAttributes['agent.input']")

    stmt = (
        select(
            c["agent_name"].label("agent_name"),
            c["ts"].label("timestamp"),
            agent_input.label("agent_input"),
        )
        .select_from(c["tbl"])
        .where(c["agent_name"] != "")
        .where(c["event_name"].in_(_AGENT_EVENT_NAMES))
        .order_by(c["ts"].desc())
        .limit(limit)
        .offset(offset)
    )

    if start_time:
        stmt = stmt.where(c["ts"] >= start_time)
    if end_time:
        stmt = stmt.where(c["ts"] <= end_time)

    return stmt
