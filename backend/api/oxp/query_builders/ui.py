#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **UI** feature domain.

All queries use SQLAlchemy Core expressions.  A ``Dialect`` parameter
selects the correct column names / functions for each backend.

Column-name differences between ClickHouse (PascalCase) and SQLite
(snake_case) are handled centrally by :func:`_refs`, which returns a
:class:`_Refs` NamedTuple with the right column expressions for each
backend.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple, Optional

from sqlalchemy import (
    column,
    func,
    literal_column,
    or_,
    select,
    table,
    text,
)

from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)

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
    column("session_id"),
    column("application_id"),
    column("agent_id"),
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
    column("events_attributes"),
    column("scope_name"),
    column("session_id"),
    column("application_id"),
    column("agent_id"),
)

# ── derived_metrics table definitions ────────────────────────────────────────

_ch_derived = table(
    "derived_metrics",
    column("SessionId"),
    column("Metrics"),
)

_sqlite_derived = table(
    "derived_metrics",
    column("session_id"),
    column("metrics"),
)

# ── otel_metrics table definitions (ClickHouse only) ─────────────────────────

_ch_metrics_sum = table(
    "otel_metrics_sum",
    column("MetricName"),
    column("TimeUnix"),
    column("Value"),
)

_ch_metrics_histogram = table(
    "otel_metrics_histogram",
    column("MetricName"),
    column("TimeUnix"),
    column("Count"),
    column("Sum"),
)


# ── unified column references ────────────────────────────────────────────────


class _Refs(NamedTuple):
    """Unified column references for both dialects."""

    tbl: object
    ts: object
    span_name: object
    span_id: object
    span_attributes: object
    status_code: object
    events_attributes: object
    scope_name: object
    session_id: object
    application_id: object
    agent_id: object
    duration: object
    parent_span_id: object
    wrap: object  # func.toString for CH, identity for SQLite


def _identity(expr):
    """No-op wrapper (SQLite doesn't need ``toString`` around aggregates)."""
    return expr


def _refs(dialect: Dialect) -> _Refs:
    """Return a :class:`_Refs` with the correct column expressions for *dialect*."""
    if dialect is Dialect.SQLITE:
        t = _sqlite_otel
        return _Refs(
            tbl=t,
            ts=t.c.timestamp,
            span_name=t.c.span_name,
            span_id=t.c.span_id,
            span_attributes=t.c.span_attributes,
            status_code=t.c.status_code,
            events_attributes=t.c.events_attributes,
            scope_name=t.c.scope_name,
            session_id=t.c.session_id,
            application_id=t.c.application_id,
            agent_id=t.c.agent_id,
            duration=t.c.duration,
            parent_span_id=t.c.parent_span_id,
            wrap=_identity,
        )
    # CLICKHOUSE / SQLALCHEMY
    t = _ch_otel
    return _Refs(
        tbl=t,
        ts=t.c.Timestamp,
        span_name=t.c.SpanName,
        span_id=t.c.SpanId,
        span_attributes=t.c.SpanAttributes,
        status_code=t.c.StatusCode,
        events_attributes=literal_column("Events.Attributes").label(
            "events_attributes"
        ),
        scope_name=t.c.ScopeName,
        session_id=t.c.session_id,
        application_id=t.c.application_id,
        agent_id=t.c.agent_id,
        duration=t.c.Duration,
        parent_span_id=t.c.ParentSpanId,
        wrap=func.toString,
    )


# ── public query builders ────────────────────────────────────────────────────


def sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    app_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Build a query for listing session (trace) summaries.

    Returns columns: ``session_id, application_id, start_time, end_time,
    span_count``.
    """
    r = _refs(dialect)
    r = _refs(dialect)

    stmt = (
        select(
            r.session_id.label("session_id"),
            r.application_id.label("application_id"),
            r.wrap(func.min(r.ts)).label("start_time"),
            r.wrap(func.max(r.ts)).label("end_time"),
            func.count().label("span_count"),
        )
        .select_from(r.tbl)
        .where(r.session_id != "")
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)
    if app_name:
        stmt = stmt.where(r.application_id == app_name)

    stmt = (
        stmt.group_by(r.session_id, r.application_id)
        .order_by(func.min(r.ts).desc())
        .limit(limit)
        .offset(offset)
    )

    return stmt


def session_agents_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Build a query for listing agent IDs seen in a session.

    Returns columns: ``agent_id`` (the span name), ``session_id``.
    """
    r = _refs(dialect)

    stmt = (
        select(r.span_name.label("agent_id"), r.sid.label("session_id"))
        .select_from(r.tbl)
        .where(r.sid != "")
        .where(r.span_name.like("%.agent"))
        .where(r.sid == session_id)
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)

    stmt = stmt.limit(limit).offset(offset)

    return stmt


def session_ids_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Build a query for listing distinct session IDs.

    Returns columns: ``id``, ``start_timestamp``.
    """
    r = _refs(dialect)

    stmt = (
        select(
            r.session_id.label("id"),
            r.wrap(func.min(r.ts)).label("start_timestamp"),
        )
        .select_from(r.tbl)
        .where(r.session_id != "")
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)

    stmt = (
        stmt.group_by(r.session_id)
        .order_by(func.min(r.ts).desc())
        .limit(limit)
        .offset(offset)
    )

    return stmt


def applications_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Build a query for listing applications

    Returns columns: ``application_id, start_time, end_time``.
    """
    r = _refs(dialect)

    stmt = (
        select(
            r.application_id.label("application_id"),
            r.wrap(func.min(r.ts)).label("start_time"),
            r.wrap(func.max(r.ts)).label("end_time"),
        )
        .select_from(r.tbl)
        .where(r.application_id != "")
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)

    stmt = (
        stmt.group_by(r.application_id)
        .order_by(func.min(r.ts).desc())
        .limit(limit)
        .offset(offset)
    )

    return stmt


def applications_with_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    """Build a query for listing applications grouped by (application_id, session_id).

    Returns columns: ``application_id, session_id, max_timestamp``.
    Ordered by max_timestamp descending.
    """
    r = _refs(dialect)

    stmt = (
        select(
            r.application_id.label("application_id"),
            r.session_id.label("session_id"),
            r.wrap(func.max(r.ts)).label("max_timestamp"),
        )
        .select_from(r.tbl)
        .where(r.application_id != "")
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)

    stmt = stmt.group_by(r.application_id, r.session_id).order_by(func.max(r.ts).desc())

    return stmt


def applications_with_sessions_and_tokens_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    """Merged query: sessions, token costs, agents and LLMs in one round-trip.

    ClickHouse only.  Returns one row per ``(application_id, session_id)``
    with columns:

    * ``application_id``
    * ``session_id``
    * ``max_timestamp``
    * ``total_tokens`` — sum of prompt + completion tokens from ``.chat`` spans
      for that session.
    * ``agents`` — array of distinct agent base-names (part before the first
      dot) across **all** sessions of the application.
    * ``llms`` — array of distinct LLM model names across **all** sessions of
      the application.

    ``agents`` and ``llms`` are application-level aggregates repeated on every
    session row for the same application; the caller may read them from any
    row.
    """
    r = _refs(dialect)

    prompt_tokens = literal_column(
        "toFloat64OrZero(SpanAttributes['gen_ai.usage.input_tokens'])"
    )
    completion_tokens = literal_column(
        "toFloat64OrZero(SpanAttributes['gen_ai.usage.output_tokens'])"
    )
    agent_base = literal_column("splitByChar('.', agent_id)[1]")
    llm_expr = literal_column("SpanAttributes['gen_ai.request.model']")

    # CTE 1: per-session timestamps ───────────────────────────────────
    sessions_q = (
        select(
            r.application_id.label("application_id"),
            r.session_id.label("session_id"),
            r.wrap(func.max(r.ts)).label("max_timestamp"),
        )
        .select_from(r.tbl)
        .where(r.application_id != "")
        .where(r.session_id != "")
    )
    if start_time:
        sessions_q = sessions_q.where(r.ts >= start_time)
    if end_time:
        sessions_q = sessions_q.where(r.ts <= end_time)
    sessions_cte = (sessions_q.group_by(r.application_id, r.session_id)).cte(
        "sessions_ts"
    )

    # CTE 2: per-session token sums (only .chat spans, no time range filter,
    # no application_id filter — mirrors token_sum_by_sessions_query exactly:
    # sum ALL .chat spans for a session_id, regardless of application_id or
    # timestamp, so that spans with empty/different application_id are counted) ─
    tokens_q = (
        select(
            r.session_id.label("session_id"),
            func.sum(prompt_tokens + completion_tokens).label("total_tokens"),
        )
        .select_from(r.tbl)
        .where(r.session_id != "")
        .where(r.span_name.like("%.chat"))
    )
    tokens_cte = (tokens_q.group_by(r.session_id)).cte("sessions_tokens")

    # CTE 2: per-application distinct agent base-names ────────────────
    agents_q = (
        select(
            r.application_id.label("application_id"),
            func.groupUniqArray(agent_base).label("agents"),
        )
        .select_from(r.tbl)
        .where(r.application_id != "")
        .where(agent_base != "")
    )
    if start_time:
        agents_q = agents_q.where(r.ts >= start_time)
    if end_time:
        agents_q = agents_q.where(r.ts <= end_time)
    agents_cte = agents_q.group_by(r.application_id).cte("app_agents")

    # CTE 3: per-application distinct LLM model names ─────────────────
    llms_q = (
        select(
            r.application_id.label("application_id"),
            func.groupUniqArray(llm_expr).label("llms"),
        )
        .select_from(r.tbl)
        .where(r.application_id != "")
        .where(llm_expr != "")
        .where(r.span_name.like("%.chat"))
    )
    if start_time:
        llms_q = llms_q.where(r.ts >= start_time)
    if end_time:
        llms_q = llms_q.where(r.ts <= end_time)
    llms_cte = llms_q.group_by(r.application_id).cte("app_llms")

    # Final: join session rows with tokens, agents, and LLMs ─────────
    return (
        select(
            sessions_cte.c.application_id,
            sessions_cte.c.session_id,
            sessions_cte.c.max_timestamp,
            tokens_cte.c.total_tokens,
            agents_cte.c.agents,
            llms_cte.c.llms,
        )
        .select_from(sessions_cte)
        .outerjoin(
            tokens_cte,
            tokens_cte.c.session_id == sessions_cte.c.session_id,
        )
        .outerjoin(
            agents_cte,
            agents_cte.c.application_id == sessions_cte.c.application_id,
        )
        .outerjoin(
            llms_cte,
            llms_cte.c.application_id == sessions_cte.c.application_id,
        )
        .order_by(sessions_cte.c.max_timestamp.desc())
    )


def neo4j_applications_with_sessions_query(
    dialect: Dialect = Dialect.NEO4J,
    *,
    start_epoch: Optional[float] = None,
    end_epoch: Optional[float] = None,
    offset: int = 0,
    limit: int = 50,
):
    """Build a Neo4j Cypher query listing applications with their session IDs.

    Matches ``Session`` nodes connected to ``MAS`` nodes and groups by
    ``name``.  Applies optional epoch-based time filters.

    Returns a ``(cypher_string, params_dict)`` tuple with columns:
    ``application_id, session_ids, min_start``.
    """
    stmt = """
    MATCH (s:Session)-[]-(ma:MAS)
    WHERE ma.id IS NOT NULL
      AND ma.id <> ''
      AND ($start_epoch IS NULL OR toFloat(s.startTime) >= $start_epoch)
      AND ($end_epoch IS NULL OR toFloat(s.startTime) <= $end_epoch)
    WITH
      ma.id AS application_id,
      collect(DISTINCT s.sessionId) AS session_ids,
      min(toFloat(s.startTime)) AS min_start
    WITH
      application_id,
      [sid IN session_ids WHERE sid IS NOT NULL AND sid <> ''] AS session_ids,
      min_start
    WHERE size(session_ids) > 0
    ORDER BY min_start DESC
    SKIP $offset
    LIMIT $limit
    RETURN application_id, session_ids, min_start
    """
    return stmt, {
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "offset": int(offset),
        "limit": int(limit),
    }


def neo4j_applications_with_metrics_optimized_query(
    dialect: Dialect = Dialect.NEO4J,
    *,
    start_epoch: Optional[float] = None,
    end_epoch: Optional[float] = None,
    offset: int = 0,
    limit: int = 50,
    metric_names: Optional[list[str]] = None,
):
    """Build a single Neo4j query for applications + sessions + enrichments.

    Returns one row per application with these columns:
    ``application_id, session_ids, min_start, total_tokens, agents, llms,
    metric_rows``.

    ``metric_rows`` is a list of maps with keys ``sid``, ``metric_name`` and
    ``metric_result`` used by the caller to compute the final performance score.
    """
    if dialect is not Dialect.NEO4J:
        raise NotImplementedError(
            "neo4j_applications_with_metrics_optimized_query supports Neo4j only"
        )

    stmt = """
        MATCH (s:Session)-[]-(ma:MAS)
        WHERE ma.id IS NOT NULL
            AND ma.id <> ''
            AND ($start_epoch IS NULL OR toFloat(s.startTime) >= $start_epoch)
            AND ($end_epoch IS NULL OR toFloat(s.startTime) <= $end_epoch)
        WITH
            ma.id AS application_id,
            collect(DISTINCT s.sessionId) AS raw_session_ids,
            min(toFloat(s.startTime)) AS min_start
        WITH
            application_id,
            [sid IN raw_session_ids WHERE sid IS NOT NULL AND sid <> ''] AS session_ids,
            min_start
        WHERE size(session_ids) > 0
        ORDER BY min_start DESC
        SKIP $offset
        LIMIT $limit
        CALL {
            WITH session_ids
            MATCH (lc:LLMCall)
            WHERE lc.sessionId IN session_ids
            OPTIONAL MATCH (lc)-[:executesLLM]->(llmNode:LLM)
            RETURN coalesce(
                    sum(coalesce(toFloat(lc.promptTokenCount), 0.0)
                            + coalesce(toFloat(lc.completionTokenCount), 0.0)),
                    0.0
            ) AS total_tokens,
            [
                llm IN collect(DISTINCT llmNode.name)
                WHERE llm IS NOT NULL AND toString(llm) <> ''
                | toString(llm)
            ] AS llms
        }
        CALL {
            WITH session_ids
            MATCH (ac:AgentCall)
            WHERE ac.sessionId IN session_ids
            OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
            RETURN [
                agent IN collect(DISTINCT agentNode.name)
                WHERE agent IS NOT NULL AND toString(agent) <> ''
                | toString(agent)
            ] AS agents
        }
        CALL {
            WITH session_ids
            MATCH (sm:Session)-[:hasMetric]->(m:Metric)
            WHERE sm.sessionId IN session_ids
                AND m.metricName IN $metric_names
            RETURN collect({
                sid: sm.sessionId,
                metric_name: m.metricName,
                metric_result: m.metricResult
            }) AS metric_rows
        }
        RETURN
            application_id,
            session_ids,
            min_start,
            total_tokens,
            agents,
            llms,
            metric_rows
        """
    return stmt, {
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "offset": int(offset),
        "limit": int(limit),
        "metric_names": metric_names or [],
    }


def agents_by_application_and_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    application_id: str,
    session_ids: list[str],
):
    """Build a query for distinct agent base-names for an application.

    The agent base name is the part of ``agent_id`` before the first dot.

    For **Neo4j** returns a ``(cypher_string, params_dict)`` tuple; the
    result row has column ``agents`` (a list).

    Returns column: ``agent_name``.
    """
    if dialect is Dialect.NEO4J:
        stmt = """
        MATCH (ac:AgentCall)-[:executesAgent]->(agentNode:Agent)
        WHERE ac.sessionId IN $session_ids
        WITH DISTINCT agentNode.name AS agent
        WHERE agent IS NOT NULL AND agent <> ''
        RETURN collect(agent) AS agents
        """
        return stmt, {"session_ids": session_ids}

    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        agent_base = func.substr(
            r.agent_id,
            1,
            func.instr(r.agent_id, ".") - 1,
        )
        return (
            select(func.distinct(agent_base).label("agent_name"))
            .select_from(r.tbl)
            .where(r.session_id.in_(session_ids))
            .where(func.lower(r.application_id) == func.lower(application_id))
            .where(r.agent_id != "")
            .where(r.agent_id.like("%.%"))
        )

    agent_base = literal_column("splitByChar('.', agent_id)[1]")
    return (
        select(func.distinct(agent_base).label("agent_name"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(func.lower(r.application_id) == func.lower(application_id))
        .where(agent_base != "")
    )


def llms_by_application_and_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    application_id: str,
    session_ids: list[str],
):
    """Build a query for distinct LLM model names for an application.

    Looks at the ``gen_ai.request.model`` key inside ``span_attributes``
    for ``.chat`` spans.

    For **Neo4j** returns a ``(cypher_string, params_dict)`` tuple; the
    result row has column ``llms`` (a list).

    For **SQLite** the column stores a Python-dict literal, so
    ``json_extract`` cannot be used.  Instead the query returns raw
    ``span_attributes`` rows and the caller must extract model names
    in Python (column: ``span_attributes``).

    For **ClickHouse** the query returns ``llm_name`` directly.
    """
    if dialect is Dialect.NEO4J:
        stmt = """
        MATCH (lc:LLMCall)-[:executesLLM]->(llmNode:LLM)
        WHERE lc.sessionId IN $session_ids
        WITH DISTINCT llmNode.name AS llm
        WHERE llm IS NOT NULL AND llm <> ''
        RETURN collect(llm) AS llms
        """
        return stmt, {"session_ids": session_ids}

    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        # span_attributes is a Python-dict string; return raw values for
        # the caller to parse with ``parse_span_attributes``.
        return (
            select(r.span_attributes.label("span_attributes"))
            .select_from(r.tbl)
            .where(r.session_id.in_(session_ids))
            .where(func.lower(r.application_id) == func.lower(application_id))
            .where(r.span_name.like("%.chat"))
        )

    # ClickHouse: SpanAttributes is a Map — use bracket notation.
    llm_expr = literal_column("SpanAttributes['gen_ai.request.model']")
    return (
        select(func.distinct(llm_expr).label("llm_name"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(func.lower(r.application_id) == func.lower(application_id))
        .where(llm_expr != "")
        .where(r.span_name.like("%.chat"))
    )


def span_details_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    span_id: str,
):
    """Build a query for fetching a single span's details.

    Returns columns: ``span_id, span_name, span_attributes, status_code,
    events_attributes, scope_name``.
    """
    r = _refs(dialect)

    return (
        select(
            r.span_id,
            r.span_name,
            r.span_attributes,
            r.status_code,
            r.events_attributes,
            r.scope_name,
        )
        .select_from(r.tbl)
        .where(r.span_id == span_id)
        .limit(1)
    )


def agent_description_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_id: str,
    agent_id: str,
):
    """Build a query to find the agent description from ``agent_start_event`` rows.

    Searches ``events_attributes`` for a matching ``agent_id`` that starts
    with *agent_id* and a non-empty ``description``.

    Returns columns: ``events_attributes, span_name``.
    """
    r = _refs(dialect)

    return (
        select(r.events_attributes, r.span_name)
        .select_from(r.tbl)
        .where(r.session_id == session_id)
        .where(r.span_name == "agent_start_event")
    )


def agent_spans_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_id: str,
    agent_id: str,
):
    """Build a query for agent spans in a session (by ``agent_id`` column).

    Returns columns: ``span_name, span_attributes``.
    Excludes spans whose name contains ``__init_run``.
    """
    r = _refs(dialect)

    return (
        select(r.span_name, r.span_attributes)
        .select_from(r.tbl)
        .where(r.session_id == session_id)
        .where(r.agent_id == agent_id)
        .where(r.span_name.notlike("%__init_run%"))
    )


def agent_token_aggregates_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_id: str,
    agent_id: str,
):
    """Build a query that returns chat span attributes for an agent.

    Returns columns: ``span_attributes`` for each chat span, so the caller
    can sum tokens and collect LLM names.
    """
    r = _refs(dialect)

    return (
        select(r.span_attributes)
        .select_from(r.tbl)
        .where(r.session_id == session_id)
        .where(r.agent_id == agent_id)
        .where(r.span_name.like("%.chat"))
    )


def session_impact_assessment_query(
    dialect: Dialect = Dialect.NEO4J,
    *,
    session_id: str,
):
    return f"""
    MATCH (s:Session {{sessionId: "{session_id}"}})-[r]-(n:ImpactAssessment)
    RETURN n.metricName AS metricName, n.contributions AS contributions
    """


# ── Monitor Application Level query builders ─────────────────────────────────


def timestamps_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """MIN / MAX timestamps for a set of session IDs (root spans only)."""
    r = _refs(dialect)

    return (
        select(
            r.wrap(func.min(r.ts)).label("min_ts"),
            r.wrap(func.max(r.ts)).label("max_ts"),
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.parent_span_id == "")
    )


def session_ids_with_avgs_graph_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: str,
    given_session_ids: list[str],
):
    """Distinct session IDs from graph spans, with optional app + time filters."""
    r = _refs(dialect)

    stmt = (
        select(
            r.session_id.label("session_id"),
            r.wrap(func.min(r.ts)).label("start_timestamp"),
            r.wrap(func.max(r.ts)).label("end_timestamp"),
        )
        .select_from(r.tbl)
        # Adding the dot, as we have content like: query_graph_database.tool
        .where(r.span_name.like("%.graph%"))
        .where(r.session_id != "")
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)
    if application_id:
        stmt = stmt.where(func.lower(r.application_id) == func.lower(application_id))
    if given_session_ids:
        stmt = stmt.where(r.session_id.in_(given_session_ids))

    return stmt.group_by(r.session_id).order_by(func.min(r.ts).desc())


def topology_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    application_id: str,
):
    """Return the graph JSON for a single graph span of *application_id*."""
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        graph_col = r.span_attributes.label("graph_json")
    else:
        graph_col = literal_column("SpanAttributes['gen_ai.ioa.graph']").label(
            "graph_json"
        )

    stmt = (
        select(graph_col)
        .select_from(r.tbl)
        .where(r.span_name.like("%.graph%"))
        .where(r.session_id != "")
        .where(func.lower(r.application_id) == func.lower(application_id))
        .order_by(r.ts.desc())
        .limit(1)
    )

    return stmt


def topology_query_by_session(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_id: str,
):
    """Return the graph JSON for a single graph span of *session_id*."""
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        graph_col = r.span_attributes.label("graph_json")
    else:
        graph_col = literal_column("SpanAttributes['gen_ai.ioa.graph']").label(
            "graph_json"
        )

    stmt = (
        select(graph_col, r.session_id.label("session_id"))
        .select_from(r.tbl)
        .where(r.span_name.like("%.graph%"))
        .where(r.session_id == session_id)
        .order_by(r.ts.desc())
        .limit(1)
    )

    return stmt


def agent_descriptions_by_application_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    application_id: str,
    session_id: Optional[str] = None,
):
    """Return ``agent_start_event`` rows for an application.

    Returns columns: ``events_attributes, span_name``.
    """
    r = _refs(dialect)

    stmt = (
        select(r.events_attributes, r.span_name)
        .select_from(r.tbl)
        .where(r.span_name == "agent_start_event")
    )

    if session_id:
        stmt = stmt.where(r.session_id == session_id)
    else:
        stmt = stmt.where(func.lower(r.application_id) == func.lower(application_id))

    return stmt


def semantic_groups_table_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    application_id: str,
):
    """Return the semantic-groups table query.

    Semantic groups are currently sourced from Neo4j semantic nodes.
    """
    query = """
    MATCH (:MAS {id: $application_id})-[:containsSemanticGroup]->(sg:SemanticGroup {childrenNodes: []})
    // First, gather all consistency reports from the semantic groups
    OPTIONAL MATCH (sg)-[r]-(cr:ConsistencyReport)
    WITH sg, cr.dataType AS rawType, AVG(cr.mean) AS Value
    WITH sg,
      (CASE rawType
        WHEN 'metric' THEN 'MetricConsistency'
        WHEN 'graph' THEN 'GraphConsistency'
        WHEN 'text' THEN 'TextConsistency'
        ELSE rawType END) AS DataType, Value
        // Save consistency per type per semantic group as a JSON (will be reused later)
    WITH sg,
      collect({col1: DataType, col2: Value}) AS consistency
    // Collect sessions attached to the semantic groups
    OPTIONAL MATCH (sg)-[:containsSession]->(s:Session)
    // Collect Metrics associated to the sessions
    OPTIONAL MATCH (s)-[]-(m:Metric)
    WHERE m.metricName IN ["LLMErrorRate",
                    "ToolErrorRate",
                    "IntentRecognitionAccuracy",
                    "Groundedness",
                    "ToolUtilizationAccuracy",
                    "AnswerRelevancy",
                    "ResponseCompleteness",
                    "WorkflowEfficiency",
                    "CyclesCount"
                   ]
    // Metrics manipulation, to compute the 3 overall scores
    WITH sg,
      avg(CASE WHEN m.metricName IN ["IntentRecognitionAccuracy", "Groundedness", "ToolUtilizationAccuracy", "AnswerRelevancy", "ResponseCompleteness"] THEN m.metricResult END) AS overallQuality,
      1 - avg(CASE WHEN m.metricName IN ["LLMErrorRate", "ToolErrorRate"] THEN m.metricResult END) AS completionRate,
      (1 / (1 + avg(CASE WHEN m.metricName = "CyclesCount" THEN m.metricResult END))) AS cycles,
      1 - avg(CASE WHEN m.metricName = "LLMErrorRate" THEN m.metricResult END) AS successLLM,
      1 - avg(CASE WHEN m.metricName = "ToolErrorRate" THEN m.metricResult END) AS successTool,
      avg(CASE WHEN m.metricName = "WorkflowEfficiency" THEN m.metricResult END) AS avgWflwEff, consistency
    // Opening the consistency json
    UNWIND consistency as c
    WITH sg, overallQuality,
      [x IN [cycles, avgWflwEff, successLLM, successTool] WHERE x IS NOT NULL] AS perfValues,
      collect(c.col2) as consistencyValues, completionRate
    WITH sg, overallQuality,
      CASE WHEN size(perfValues) = 0 THEN null
           ELSE reduce(s = 0.0, x IN perfValues | s + x) / size(perfValues)
      END AS overallPerformance,
      consistencyValues, completionRate
    WITH sg, overallQuality, overallPerformance, reduce(s = 0.0, x IN consistencyValues | s + x) as consistencySum, reduce(s = 0, x IN consistencyValues | s + 1) as consistencyEntries, completionRate
    WITH sg, overallQuality, overallPerformance, (consistencySum + completionRate) / (consistencyEntries + 1) AS overallReliability
    RETURN sg, overallQuality, overallPerformance, overallReliability
    """
    return query, {"application_id": application_id}


def semantic_groups_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    application_id: str,
):
    """Return all semantic-group nodes for an application.

    The current Neo4j model stores semantic groups as ``SemanticGroup`` nodes.
    """
    query = """
    MATCH (:MAS {id: $application_id})-[:containsSemanticGroup]->(sg:SemanticGroup)
    // First, gather all consistency reports from the semantic groups
    OPTIONAL MATCH (sg)-[r]-(cr:ConsistencyReport)
    WITH sg, cr.dataType AS rawType, AVG(cr.mean) AS Value
    WITH sg,
      (CASE rawType
        WHEN 'metric' THEN 'MetricConsistency'
        WHEN 'graph' THEN 'GraphConsistency'
        WHEN 'text' THEN 'TextConsistency'
        ELSE rawType END) AS DataType, Value
        // Save consistency per type per semantic group as a JSON (will be reused later)
    WITH sg,
      collect({col1: DataType, col2: Value}) AS consistency
    // Collect sessions attached to the semantic groups
    OPTIONAL MATCH (sg)-[:containsSession*1..]->(s:Session)
    // Collect Metrics associated to the sessions
    OPTIONAL MATCH (s)-[]-(m:Metric)
    WHERE m.metricName IN ["LLMErrorRate",
                    "ToolErrorRate",
                    "IntentRecognitionAccuracy",
                    "Groundedness",
                    "ToolUtilizationAccuracy",
                    "AnswerRelevancy",
                    "ResponseCompleteness",
                    "WorkflowEfficiency",
                    "CyclesCount"
                   ]
    // Metrics manipulation, to compute the 3 overall scores
    WITH sg,
      avg(CASE WHEN m.metricName IN ["IntentRecognitionAccuracy", "Groundedness", "ToolUtilizationAccuracy", "AnswerRelevancy", "ResponseCompleteness"] THEN m.metricResult END) AS overallQuality,
      1 - avg(CASE WHEN m.metricName IN ["LLMErrorRate", "ToolErrorRate"] THEN m.metricResult END) AS completionRate,
      (1 / (1 + avg(CASE WHEN m.metricName = "CyclesCount" THEN m.metricResult END))) AS cycles,
      1 - avg(CASE WHEN m.metricName = "LLMErrorRate" THEN m.metricResult END) AS successLLM,
      1 - avg(CASE WHEN m.metricName = "ToolErrorRate" THEN m.metricResult END) AS successTool,
      avg(CASE WHEN m.metricName = "WorkflowEfficiency" THEN m.metricResult END) AS avgWflwEff, consistency
    // Opening the consistency json
    UNWIND consistency as c
    WITH sg, overallQuality,
      [x IN [cycles, avgWflwEff, successLLM, successTool] WHERE x IS NOT NULL] AS perfValues,
      collect(c.col2) as consistencyValues, completionRate
    WITH sg, overallQuality,
      CASE WHEN size(perfValues) = 0 THEN null
           ELSE reduce(s = 0.0, x IN perfValues | s + x) / size(perfValues)
      END AS overallPerformance,
      consistencyValues, completionRate
    WITH sg, overallQuality, overallPerformance, reduce(s = 0.0, x IN consistencyValues | s + x) as consistencySum, reduce(s = 0, x IN consistencyValues | s + 1) as consistencyEntries, completionRate
    WITH sg, overallQuality, overallPerformance, (consistencySum + completionRate) / (consistencyEntries + 1) AS overallReliability
    RETURN sg, overallQuality, overallPerformance, overallReliability
    """
    return query, {"application_id": application_id}


def semantic_group_impact_assessment_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    application_id: str,
    semanticgroup_id: str,
):
    # TODO: need to find a better way to handle this
    # Currently this is parsing manually a string into a json object and extracting the different fields and values.
    # It works, but it's ugly
    query = """
    MATCH (sg:SemanticGroup {id: $semanticgroup_id})-[:containsSession*1..]->(s:Session)-[:hasImpactAssessment]->(ia:ImpactAssessment)
    WITH ia.metricName AS metricName, ia.contributions AS contributionsStr
    // Remove braces and quotes, then split by comma to get agent-value pairs
    WITH metricName, split(replace(replace(contributionsStr, '{', ''), '}', ''), ',') AS agentValuePairs
    UNWIND agentValuePairs AS pair
    //Split each pair by colon to separate agent and value
    WITH metricName, split(pair, ':') AS parts
    WITH metricName, trim(parts[0]) AS agentRaw, trim(parts[1]) AS valueRaw
    //Remove quotes from agent name
    WITH metricName, replace(agentRaw, '"', '') AS agent, toFloat(valueRaw) AS value
    WITH metricName, agent, avg(value) as avgValue
    WITH metricName, collect({agent: agent, value: avgValue}) AS contributions
    RETURN metricName, contributions
    """
    return query, {"semanticgroup_id": semanticgroup_id}


def session_ids_graph_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: Optional[str] = None,
    given_session_ids: Optional[list[str]] = None,
):
    """Distinct session IDs from graph spans, with optional app + time filters."""
    r = _refs(dialect)

    stmt = (
        select(
            r.session_id.label("session_id"),
            r.wrap(func.min(r.ts)).label("start_timestamp"),
            r.wrap(func.max(r.ts)).label("end_timestamp"),
        )
        .select_from(r.tbl)
        # Adding the dot, as we have content like: query_graph_database.tool
        .where(r.span_name.like("%.graph%"))
        .where(r.session_id != "")
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)
    if application_id:
        stmt = stmt.where(func.lower(r.application_id) == func.lower(application_id))
    if given_session_ids:
        stmt = stmt.where(r.session_id.in_(given_session_ids))

    return stmt.group_by(r.session_id).order_by(func.min(r.ts).desc())


def traces_count_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: Optional[str] = None,
):
    """Count total rows for an application in a time range."""
    r = _refs(dialect)

    stmt = select(func.count().label("cnt")).select_from(r.tbl)

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)
    if application_id:
        stmt = stmt.where(func.lower(r.application_id) == func.lower(application_id))

    return stmt


def conversation_count_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: Optional[str] = None,
):
    """Count distinct (agent_id, session_id) pairs for .chat spans."""
    r = _refs(dialect)

    # COUNT(DISTINCT agent_id || '|' || session_id) works for both dialects.
    distinct_expr = func.count(
        func.distinct(r.agent_id + literal_column("'|'") + r.session_id)
    ).label("cnt")
    distinct_expr = func.count(
        func.distinct(func.concat(r.agent_id, literal_column("'|'"), r.session_id))
    ).label("cnt")

    stmt = (
        select(distinct_expr)
        .select_from(r.tbl)
        .where(r.session_id != "")
        .where(r.span_name.like("%.chat"))
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)
    if application_id:
        stmt = stmt.where(func.lower(r.application_id) == func.lower(application_id))

    return stmt


def distinct_agents_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Return distinct base agent names (part before the first dot) for sessions."""
    r = _refs(dialect)

    # String-splitting differs between SQLite and ClickHouse.
    if dialect is Dialect.SQLITE:
        agent_base = func.substr(
            r.agent_id,
            1,
            func.instr(r.agent_id, ".") - 1,
        ).label("agent_id")
        return (
            select(func.distinct(agent_base).label("agent_id"))
            .select_from(r.tbl)
            .where(r.session_id.in_(session_ids))
            .where(r.agent_id != "")
            .where(r.agent_id.like("%.%"))
        )

    agent_base = literal_column("splitByChar('.', agent_id)[1]")
    return (
        select(func.distinct(agent_base).label("agent_id"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(agent_base != "")
    )


def agent_span_count_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
):
    """Count spans for a specific agent (base name) within given sessions."""
    r = _refs(dialect)

    return (
        select(func.count().label("cnt"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.agent_id == agent_id)
    )


def top_agent_span_count_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Return top-most (agent_id, cnt) computed in a single query.

    Agent identity is normalized to the base name (part before the first dot),
    then ranked by count descending and agent_id ascending for deterministic ties.
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        agent_base = func.substr(
            r.agent_id,
            1,
            func.instr(r.agent_id, ".") - 1,
        )
        cnt_expr = func.count().label("cnt")
        return (
            select(
                agent_base.label("agent_base"),
                cnt_expr,
            )
            .select_from(r.tbl)
            .where(r.session_id.in_(session_ids))
            .where(r.agent_id != "")
            .where(r.agent_id.like("%.%"))
            .group_by(agent_base)
            .order_by(cnt_expr.desc(), literal_column("agent_base").asc())
            .limit(1)
        )

    agent_base = literal_column("splitByChar('.', agent_id)[1]")
    cnt_expr = func.count().label("cnt")
    return (
        select(
            agent_base.label("agent_base"),
            cnt_expr,
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(agent_base != "")
        .group_by(agent_base)
        .order_by(cnt_expr.desc(), literal_column("agent_base").asc())
        .limit(1)
    )


# ── Monitor By Application query builders ─────────────────────────────────


def agent_failure_count_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
):
    """Count error-status spans for a specific agent across sessions.

    Returns columns: ``cnt`` (number of error spans).
    """
    r = _refs(dialect)

    return (
        select(func.count().label("cnt"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.agent_id == agent_id)
        .where(r.status_code == "Error")
    )


def agent_token_costs_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
):
    """Return chat span attributes for an agent across multiple sessions.

    Returns columns: ``span_attributes, session_id`` for ``.chat`` spans
    so the caller can aggregate token counts and compute costs.
    """
    r = _refs(dialect)

    return (
        select(r.span_attributes, r.session_id.label("session_id"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.agent_id == agent_id)
        .where(r.span_name.like("%.chat"))
    )


def agent_active_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
):
    """Return distinct session IDs where a specific agent is present.

    Returns columns: ``session_id``.
    """
    r = _refs(dialect)

    return (
        select(func.distinct(r.session_id).label("session_id"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.agent_id == agent_id)
    )


def agent_avg_duration_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
):
    """Average duration (in nanoseconds) of ``.agent`` spans for a specific
    agent across sessions.

    Returns columns: ``avg_duration``.
    """
    r = _refs(dialect)

    return (
        select(func.avg(r.duration).label("avg_duration"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.agent_id == agent_id)
        .where(r.span_name.like("%.agent"))
    )


def session_avg_duration_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Average session duration across the given sessions.

    Computes ``MAX(timestamp) - MIN(timestamp)`` per session (in seconds),
    then averages across sessions.

    Returns columns: ``avg_duration``.
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        dur_expr = (
            func.julianday(func.max(r.ts)) - func.julianday(func.min(r.ts))
        ) * 86400
    else:
        dur_expr = (
            func.toUnixTimestamp64Nano(func.max(r.ts))
            - func.toUnixTimestamp64Nano(func.min(r.ts))
        ) / literal_column("1000000000")

    sub = (
        select(dur_expr.label("sess_dur"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.session_id != "")
        .group_by(r.session_id)
    ).subquery()

    return select(func.avg(column("sess_dur")).label("avg_duration")).select_from(sub)


def llm_calls_count_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Count total ``.chat`` spans (LLM calls) across sessions.

    Returns columns: ``cnt``.
    """
    r = _refs(dialect)
    return (
        select(func.count().label("cnt"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.span_name.like("%.chat"))
    )


def tool_calls_count_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Count total ``.tool`` spans (tool calls) across sessions.

    Returns columns: ``cnt``.
    """
    r = _refs(dialect)
    return (
        select(func.count().label("cnt"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.span_name.like("%.tool"))
    )


def error_count_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Count spans with status ``Error`` across sessions.

    Returns columns: ``cnt``.
    """
    r = _refs(dialect)
    return (
        select(func.count().label("cnt"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.status_code == "Error")
    )


def token_sum_by_sessions_query(
    *,
    session_ids: list[str],
):
    """Sum total tokens (prompt + completion) for a set of sessions via Neo4j.

    Sums ``promptTokenCount`` + ``completionTokenCount`` on ``LLMCall`` nodes
    and returns a ``(cypher_string, params_dict)`` tuple with a single-row
    result column ``total_tokens``.
    """
    stmt = """
    MATCH (lc:LLMCall)
    WHERE lc.sessionId IN $session_ids
    RETURN coalesce(
        sum(coalesce(toFloat(lc.promptTokenCount), 0.0)
            + coalesce(toFloat(lc.completionTokenCount), 0.0)),
        0.0
    ) AS total_tokens
    """
    return stmt, {"session_ids": session_ids}


def token_sum_by_sessions_clickhouse_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Sum total tokens (prompt + completion) for ClickHouse/SQLite backends.

    For **SQLite** returns raw ``span_attributes`` rows for Python-side
    parsing.  For **ClickHouse** returns a single ``total_tokens`` value.
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        return (
            select(r.span_attributes.label("span_attributes"))
            .select_from(r.tbl)
            .where(r.session_id.in_(session_ids))
            .where(r.span_name.like("%.chat"))
        )

    prompt_tokens = literal_column(
        "toFloat64OrZero(SpanAttributes['gen_ai.usage.input_tokens'])"
    )
    completion_tokens = literal_column(
        "toFloat64OrZero(SpanAttributes['gen_ai.usage.output_tokens'])"
    )
    return (
        select(func.sum(prompt_tokens + completion_tokens).label("total_tokens"))
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.span_name.like("%.chat"))
    )


# ── Collect By Application query builders ─────────────────────────────────


def collect_page_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: Optional[str] = None,
):
    """Build a query for collect page sessions grouped by session_id.

    Returns columns: ``session_id, start_timestamp, end_timestamp``.
    """
    _refs(dialect)

    # TODO: add support for time range here
    if dialect is Dialect.NEO4J:
        stmt = """
        MATCH (s:Session)-[:executesSession]->(ma:MAS) WHERE ma.id = $application_id
        OPTIONAL MATCH (s) - [] - (m:Metric) WHERE m.metricName = 'Cost'
        OPTIONAL MATCH (s)-[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)
        OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
        OPTIONAL MATCH (ac)-[:hasLLMCall]->(l:LLMCall)
        RETURN
            s.sessionId AS sessionId,
            s.startTime as startTime,
            s.duration as duration,
            m.metricResult as cost,
            collect(DISTINCT agentNode.name) As agents,
            sum(l.completionTokenCount + l.promptTokenCount) as tokens
        """
        return stmt, {"application_id": application_id}


def collect_page_sessions_with_stateful_eval_query_multi_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: Optional[str] = None,
):
    """Build a query for collect page sessions including stateful eval metrics.

    Returns a Cypher string for Neo4j that also collects any session-attached
    metrics named `trajectory_score` or `statefulEval` as `statefulEvals`.
    """
    # Only Neo4j currently supports attached Metric nodes for stateful eval
    if dialect is Dialect.NEO4J:
        stmt = """
        MATCH (s:Session)-[:executesSession]->(ma:MAS) WHERE ma.id = $application_id
        OPTIONAL MATCH (s) - [] - (m:Metric) WHERE m.metricName = 'Cost'
        OPTIONAL MATCH (s)-[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)
        OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
        OPTIONAL MATCH (ac)-[:hasLLMCall]->(l:LLMCall)
        OPTIONAL MATCH (s)-[:hasMetric]->(se:Metric)
            WHERE se.metricName IN ['trajectory_score','statefulEval']
        RETURN
            s.sessionId AS sessionId,
            s.startTime as startTime,
            s.duration as duration,
            m.metricResult as cost,
            collect(DISTINCT agentNode.name) As agents,
            sum(l.completionTokenCount + l.promptTokenCount) as tokens,
            collect(DISTINCT {
                name: se.metricName,
                result: se.metricResult,
                value: se.value,
                provider: se.provider,
                metric_id: coalesce(se.metricId, se.metricName),
                source: se.source,
                reasoning: se.reasoning
            }) AS statefulEvals
        """
        return stmt, {"application_id": application_id}

    # Fallback to existing collect_page_sessions_query behaviour for SQL
    return collect_page_sessions_query(
        dialect=dialect,
        start_time=start_time,
        end_time=end_time,
        application_id=application_id,
    )


def collect_page_sessions_with_stateful_eval_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: Optional[str] = None,
    semantic_group_id: Optional[str] = None,
):
    """Build a single Neo4j query returning sessions, stateful eval, and metrics.

    Returns one row per session with:
    ``sessionId, startTime, duration, cost, agents, tokens, statefulEvals, sessionMetrics``.

    When ``semantic_group_id`` is provided, only sessions that belong to the
    given ``SemanticGroup`` (keyed by its ``id`` property) are returned.
    """
    # For debugging, add:
    # MATCH (s:Session) - [] -(ma:MAS) WHERE ma.id = $application_id
    # WITH DISTINCT s
    # LIMIT 5

    # WHERE clause filters on s.startTime using NULL-guards ($start_time IS NULL OR s.startTime >= $start_time
    # the same for end_time, so when a bound isn't supplied no filtering is applied.
    # The same NULL-guard pattern is used for $semantic_group_id: when it is
    # supplied, only sessions linked to that SemanticGroup are kept.
    # Only Neo4j currently supports attached Metric nodes in this shape.
    if dialect is Dialect.NEO4J:
        # logger.warning(
        #     "\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        #     "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        #     "ERROR\n"
        #     "WARNING: DEBUG is enabled: returning only 5 sessions in "
        #     "collect_page_sessions_with_stateful_eval_query.\n"
        #     "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        #     "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n"
        # )
        stmt = """
        MATCH (s:Session)-[:executesSession]->(ma:MAS) WHERE ma.id = $application_id
        WITH DISTINCT s
        WHERE ($start_time IS NULL OR s.startTime >= $start_time)
          AND ($end_time IS NULL OR s.startTime <= $end_time)
          AND ($semantic_group_id IS NULL OR EXISTS {
                MATCH (sg:SemanticGroup {id: $semantic_group_id})-[:containsSession*1..]->(s)
          })
        OPTIONAL MATCH (s) - [] - (mCost:Metric) WHERE mCost.metricName = 'Cost'
        WITH s, head(collect(DISTINCT mCost.metricResult)) AS cost
        OPTIONAL MATCH (s) - [] - (mDuration:Metric) WHERE mDuration.metricName = 'Duration'
        WITH s, cost, head(collect(DISTINCT mDuration.metricResult)) AS duration
        OPTIONAL MATCH (s)-[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)
        OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
        OPTIONAL MATCH (ac)-[:hasLLMCall]->(l:LLMCall)
        WITH
            s,
            cost,
            duration,
            [a IN collect(DISTINCT agentNode.name) WHERE a IS NOT NULL] AS agents,
            coalesce(sum(coalesce(l.completionTokenCount, 0) + coalesce(l.promptTokenCount, 0)), 0) AS tokens
        OPTIONAL MATCH (s)-[:hasMetric]->(se:Metric)
            WHERE se.metricName IN ['trajectory_score','statefulEval']
        WITH
            s,
            cost,
            duration,
            agents,
            tokens,
            [x IN collect(DISTINCT {
                name: se.metricName,
                result: se.metricResult,
                value: se.value,
                provider: se.provider,
                metric_id: coalesce(se.metricId, se.metricName),
                source: se.source,
                reasoning: se.reasoning
            }) WHERE x.name IS NOT NULL] AS statefulEvals
        OPTIONAL MATCH (s)-[:hasMetric]->(sm:Metric)
        WITH
            s,
            cost,
            duration,
            agents,
            tokens,
            statefulEvals,
            [x IN collect(DISTINCT {
                name: sm.metricName,
                result: sm.metricResult,
                value: sm.value,
                provider: sm.provider,
                metric_id: coalesce(sm.metricId, sm.metricName),
                source: sm.source,
                reasoning: sm.reasoning
            }) WHERE x.name IS NOT NULL] AS sessionMetrics
        RETURN
            s.sessionId AS sessionId,
            s.startTime AS startTime,
            duration,
            cost,
            agents,
            tokens,
            statefulEvals,
            sessionMetrics
        """
        return stmt, {
            "application_id": application_id,
            "start_time": start_time,
            "end_time": end_time,
            "semantic_group_id": semantic_group_id,
        }

    return collect_page_sessions_with_stateful_eval_query_multi_query(
        dialect=dialect,
        start_time=start_time,
        end_time=end_time,
        application_id=application_id,
    )


def collect_agents_per_session_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Return distinct (session_id, agent_base_name) pairs for given sessions.

    The agent base name is the part of ``agent_id`` before the first dot.

    Returns columns: ``session_id, agent_id``.
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        agent_base = func.substr(
            r.agent_id,
            1,
            func.instr(r.agent_id, ".") - 1,
        ).label("agent_id")
        return (
            select(
                r.session_id.label("session_id"),
                agent_base,
            )
            .select_from(r.tbl)
            .where(r.session_id.in_(session_ids))
            .where(r.agent_id != "")
            .where(r.agent_id.like("%.%"))
            .group_by(r.session_id, agent_base)
        )

    agent_base = literal_column("splitByChar('.', agent_id)[1]")
    return (
        select(
            r.session_id.label("session_id"),
            agent_base.label("agent_id"),
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(agent_base != "")
        .group_by(r.session_id, r.agent_id)
    )


def collect_chat_spans_for_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Return chat span data for given sessions.

    Returns columns: ``session_id, span_attributes`` for spans that
    represent LLM calls.  Matches ``.chat`` span names *and* any span
    that carries token-usage attributes (covers non-LangChain
    instrumentations).
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        llm_filter = or_(
            r.span_name.like("%.chat"),
            r.span_attributes.like("%llm.usage.total_tokens%"),
            r.span_attributes.like("%gen_ai.usage.input_tokens%"),
            r.span_attributes.like("%gen_ai.usage.prompt_tokens%"),
        )
    else:
        llm_filter = or_(
            r.span_name.like("%.chat"),
            literal_column("SpanAttributes['gen_ai.usage.prompt_tokens']") != "",
            literal_column("SpanAttributes['gen_ai.usage.input_tokens']") != "",
            literal_column("SpanAttributes['llm.usage.total_tokens']") != "",
        )

    exact = ", ".join(f"'{s}'" for s in session_ids)

    if dialect is Dialect.SQLITE:
        sess_filter = text(f"(session_id IN ({exact}))")
    else:
        # Chat spans may store the session id only in the SpanAttributes
        # map (often prefixed with the app name, e.g. "app_<uuid>").
        # Check both the session_id column AND SpanAttributes['session.id'].
        attr_col = "SpanAttributes['session.id']"
        like_col = " OR ".join(f"session_id LIKE '%\\_{s}'" for s in session_ids)
        like_attr = " OR ".join(f"{attr_col} LIKE '%\\_{s}'" for s in session_ids)
        sess_filter = text(
            f"(session_id IN ({exact}) OR {attr_col} IN ({exact})"
            f" OR {like_col} OR {like_attr})"
        )

    return (
        select(
            r.session_id.label("session_id"),
            r.span_attributes,
        )
        .select_from(r.tbl)
        .where(sess_filter)
        .where(llm_filter)
    )


# ── Application General Charts query builders ─────────────────────────────────


def session_ids_by_app_and_agent_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    application_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    given_session_ids: Optional[list[str]] = None,
):
    """Return distinct session IDs filtered by agent base name.

    The agent base name is the part of ``agent_id`` before the first dot
    (e.g. ``noa-moderator`` from ``noa-moderator.invoke``).

    Returns columns: ``session_id``.
    """
    r = _refs(dialect)

    stmt = (
        select(func.distinct(r.session_id).label("session_id"))
        .select_from(r.tbl)
        .where(r.session_id != "")
    )

    if start_time:
        stmt = stmt.where(r.ts >= start_time)
    if end_time:
        stmt = stmt.where(r.ts <= end_time)
    if application_id:
        stmt = stmt.where(func.lower(r.application_id) == func.lower(application_id))
    if agent_id:
        stmt = stmt.where(r.agent_id == agent_id)
    if given_session_ids:
        stmt = stmt.where(r.session_id.in_(given_session_ids))

    return stmt.order_by(r.session_id.desc())


# ── Application Tools Charts query builders ───────────────────────────────────


def tool_details_by_sessions_and_agent_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
):
    """Return per-tool aggregates for tool spans in the given sessions.

    For each distinct tool name (prefix of ``SpanName`` before the first
    dot in ``.tool`` spans), computes:
    * ``Success`` – average success rate (1 for OK, 0 for Error)
    * ``SessionCount`` – number of distinct sessions using the tool
    * ``Duration`` – average duration in milliseconds

    Returns columns: ``tool_name, success, session_count, duration``.
    """

    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        tool_name_expr = func.substr(
            r.span_name,
            1,
            func.instr(r.span_name, ".") - 1,
        )
        success_expr = func.avg(func.iif(r.status_code == "Error", 0, 1))
    else:
        tool_name_expr = literal_column("splitByChar('.', SpanName)[1]")
        success_expr = func.avg(func.if_(r.status_code == "Error", 0, 1))

    return (
        select(
            tool_name_expr.label("tool_name"),
            success_expr.label("success"),
            func.count(func.distinct(r.session_id)).label("session_count"),
            func.avg(r.duration / literal_column("1000000")).label("duration"),
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.span_name.like("%.tool"))
        .group_by(tool_name_expr)
    )


def tool_detail_for_tool_name_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
    tool_name: str,
):
    """Return the average duration (ms) for a specific tool in given sessions.

    Returns columns: ``tool_name, duration``.
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        tool_name_expr = func.substr(
            r.span_name,
            1,
            func.instr(r.span_name, ".") - 1,
        )
    else:
        tool_name_expr = literal_column("splitByChar('.', SpanName)[1]")

    return (
        select(
            tool_name_expr.label("tool_name"),
            func.avg(r.duration / literal_column("1000000")).label("duration"),
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.span_name.like("%.tool"))
        .where(tool_name_expr == tool_name)
        .group_by(tool_name_expr)
    )


# ── Timeline (Waterfall) query builders ───────────────────────────────────────


def traces_by_session_id_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_id: str,
):
    """Return all trace spans for a given session, ordered by timestamp.

    Returns columns: ``timestamp, span_id, span_name,
    parent_span_id, agent_id, application_id, duration, status_code``.
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        agent_base = func.substr(
            r.agent_id,
            1,
            func.instr(r.agent_id, ".") - 1,
        )
    else:
        agent_base = literal_column("splitByChar('.', agent_id)[1]")

    return (
        select(
            r.wrap(r.ts).label("timestamp"),
            r.span_id.label("span_id"),
            r.span_name.label("span_name"),
            r.parent_span_id.label("parent_span_id"),
            agent_base.label("agent_id"),
            r.application_id.label("application_id"),
            r.duration.label("duration"),
            r.status_code.label("status_code"),
        )
        .select_from(r.tbl)
        .where(r.session_id == session_id)
        .order_by(r.ts)
    )


_LEVEL_TO_LABELS = {
    "session": ["Session"],
    "mas": ["MASCall"],
    "agent": ["AgentCall"],
    "tool": ["ToolCall"],
    "llm": ["LLMCall"],
    "processing": ["ProcessingCall"],
    # The UI groups all three capability call types into a single "Calls" row
    # (see ExecutionTimeline.tsx's HIERARCHY_LEVELS / sessions.py's level_order,
    # both of which use "call", never "llm"/"tool"/"processing" individually).
    "call": ["ToolCall", "LLMCall", "ProcessingCall"],
}


def state_machine_graph_query(
    *,
    session_id: str,
    level: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the Cypher query for the session execution graph.

    ``hierarchyLevel`` is a per-class constant in the ontology (not a
    queryable Neo4j property with per-instance values), so "which level"
    a Transition belongs to is determined by the label of the node its
    ``representsExecution`` edge points to, not a ``t.hierarchyLevel``
    property.

    Likewise, a State's initial/final role is not a property on
    ``State`` itself (which only carries ``content``) -- the ontology
    models it relationally via ``Session -[:hasInitialState]-> State``
    and ``Session -[:hasFinalState]-> State``, so those boundary states
    must be matched explicitly to tag ``fromType``/``toType``.

    The trajectory is *not* a single flat chain hanging off ``Session``:
    every ``ExecutionElement`` (``AgentCall``, ``LLMCall``, ``ToolCall``,
    ``ProcessingCall``, ``MASCall``) has its own nested ``hasState``
    sub-trajectory, so walking only ``Session -[:hasState]-> State``
    reaches just the session's two boundary states and misses the rest
    of the execution tree entirely. ``Transition``/``State`` are
    ``TrajectoryElement``s and carry ``sessionId`` directly, so the walk
    is scoped by that property instead of by containment under Session.

    ``level`` filtering must act as a genuine row filter, applied after
    ``e`` (and ``structural``) are fully resolved via a ``WITH`` boundary.
    A bare ``WHERE`` placed directly after an ``OPTIONAL MATCH`` only
    qualifies *that* optional pattern -- rows outside the requested
    levels would still be returned, just with ``e`` (and therefore
    ``duration``/``entityName``/``hierarchyLevel``/``spanId``/
    ``executionId``) silently nulled out instead of the row being
    excluded.
    """
    labels: list[str] = []
    for item in level.split(",") if level else []:
        labels.extend(_LEVEL_TO_LABELS.get(item.strip(), []))
    labels = list(dict.fromkeys(labels))
    level_filter = (
        "WHERE any(lbl IN $levelLabels WHERE lbl IN labels(e))" if labels else ""
    )

    query = f"""
        MATCH (s:Session {{sessionId: $sessionId}})
        OPTIONAL MATCH (s)-[:hasInitialState]->(initialState:State)
        OPTIONAL MATCH (s)-[:hasFinalState]->(finalState:State)
        MATCH (from:State)-[:inputTo]->(t:Transition {{sessionId: $sessionId}})-[:leadsTo]->(to:State)
        OPTIONAL MATCH (t)-[:representsExecution]->(e)
        OPTIONAL MATCH (e)-[:executesAgent|executesTool|executesLLM|executesProcessing|executesMAS|executesSession]->(structural)
        WITH from, to, t, e, structural, initialState, finalState
        {level_filter}
        RETURN DISTINCT
            from.id as fromStateId,
            from.content as fromContent,
            CASE
                WHEN from.id = initialState.id THEN 'initial'
                WHEN from.id = finalState.id THEN 'final'
                ELSE 'intermediate'
            END as fromType,
            to.id as toStateId,
            to.content as toContent,
            CASE
                WHEN to.id = initialState.id THEN 'initial'
                WHEN to.id = finalState.id THEN 'final'
                ELSE 'intermediate'
            END as toType,
            t.id as transitionId,
            e.duration as duration,
            structural.name as entityName,
            CASE
                WHEN 'AgentCall' IN labels(e) THEN 'agent'
                WHEN 'LLMCall' IN labels(e) THEN 'call'
                WHEN 'ToolCall' IN labels(e) THEN 'call'
                WHEN 'ProcessingCall' IN labels(e) THEN 'call'
                WHEN 'MASCall' IN labels(e) THEN 'mas'
                WHEN 'Session' IN labels(e) THEN 'session'
                ELSE null
            END as hierarchyLevel,
            CASE
                WHEN 'ToolCall' IN labels(e) THEN 'tool'
                WHEN 'LLMCall' IN labels(e) THEN 'llm'
                WHEN 'ProcessingCall' IN labels(e) THEN 'processing'
                ELSE null
            END as callType,
            e.spanId as spanId,
            e.id as executionId
        ORDER BY from.id
    """

    params: dict[str, Any] = {"sessionId": session_id}
    if labels:
        params["levelLabels"] = labels
    return query, params


def latent_space_query(
    *,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build the Cypher query for state embeddings at the agent hierarchy level.

    Returns state nodes with their embeddings and transitions between them,
    matching the agent-level portion of the state machine graph.
    """
    query = """
        MATCH (s:Session {sessionId: $sessionId})-[:hasState]->(state:State)
            -[:inputTo]->(t:Transition)-[:leadsTo]->(toState:State)
        OPTIONAL MATCH (t)-[:representsExecution]->(e)
        WHERE 'AgentCall' IN labels(e)
        OPTIONAL MATCH (emb:Embedding)-[:represents]->(state)
        OPTIONAL MATCH (toEmb:Embedding)-[:represents]->(toState)
        OPTIONAL MATCH (e)-[:executesAgent]->(agent:Agent)
        RETURN DISTINCT
            state.id AS stateId,
            state.content AS content,
            emb.embeddingVector AS embedding,
            toState.id AS toStateId,
            toState.content AS toContent,
            toEmb.embeddingVector AS toEmbedding,
            t.id AS transitionId,
            e.duration AS duration,
            agent.name AS entityName,
            'agent' AS entityType
        ORDER BY state.id
    """
    return query, {"sessionId": session_id}


def execution_hierarchy_session_state_query(
    *,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build the Cypher query for session-level input/output state content."""
    query = """
        MATCH (s:Session {sessionId: $sessionId})
        OPTIONAL MATCH (s)-[:hasInitialState]->(initial:State)
        OPTIONAL MATCH (s)-[:hasFinalState]->(final:State)
        RETURN initial.content as inputContent, final.content as outputContent
    """
    return query, {"sessionId": session_id}


def execution_hierarchy_mas_query(
    *,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build the Cypher query for MAS-level transitions.

    Scoped by ``Transition.sessionId`` rather than by ``Session
    -[:hasState]->`` (see ``state_machine_graph_query``'s docstring):
    the latter only reaches the session's two boundary states, missing
    every MAS/agent/call nested further down the trajectory tree.
    """
    query = """
        MATCH (inputState:State)-[:inputTo]->(t:Transition {sessionId: $sessionId})
            -[:representsExecution]->(mc:MASCall)
        OPTIONAL MATCH (t)-[:leadsTo]->(outputState:State)
        RETURN t.id as transitionId,
               mc.startTime as timestamp,
               mc.duration as duration,
               inputState.content as inputContent,
               outputState.content as outputContent
        ORDER BY mc.startTime
    """
    return query, {"sessionId": session_id}


def execution_hierarchy_agent_query(
    *,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build the Cypher query for agent-level transitions.

    Scoped by ``Transition.sessionId`` rather than by ``Session
    -[:hasState]->`` -- see ``execution_hierarchy_mas_query``.
    """
    query = """
        MATCH (inputState:State)-[:inputTo]->(t:Transition {sessionId: $sessionId})
            -[:representsExecution]->(ac:AgentCall)
        OPTIONAL MATCH (ac)-[:executesAgent]->(agent:Agent)
        OPTIONAL MATCH (t)-[:leadsTo]->(outputState:State)
        RETURN t.id as transitionId,
               ac.startTime as timestamp,
               ac.duration as duration,
               agent.name as agentName,
               ac.id as executionId,
               inputState.content as inputContent,
               outputState.content as outputContent
        ORDER BY ac.startTime
    """
    return query, {"sessionId": session_id}


def execution_hierarchy_tool_call_query(
    *,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build the Cypher query for tool call-level transitions.

    Scoped by ``Transition.sessionId`` rather than by ``Session
    -[:hasState]->`` -- see ``execution_hierarchy_mas_query``.
    """
    query = """
        MATCH (inputState:State)-[:inputTo]->(t:Transition {sessionId: $sessionId})
            -[:representsExecution]->(tc:ToolCall)
        OPTIONAL MATCH (tc)-[:executesTool]->(tool:Tool)
        OPTIONAL MATCH (ac:AgentCall)-[:hasToolCall]->(tc)
        OPTIONAL MATCH (t)-[:leadsTo]->(outputState:State)
        RETURN t.id as transitionId,
               tc.startTime as timestamp,
               tc.duration as duration,
               tool.name as toolName,
               tc.id as executionId,
               tc.spanId as spanId,
               ac.id as parentAgentExecId,
               inputState.content as inputContent,
               outputState.content as outputContent
        ORDER BY tc.startTime
    """
    return query, {"sessionId": session_id}


def execution_hierarchy_llm_call_query(
    *,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Build the Cypher query for LLM call-level transitions.

    Scoped by ``Transition.sessionId`` rather than by ``Session
    -[:hasState]->`` -- see ``execution_hierarchy_mas_query``.
    """
    query = """
        MATCH (inputState:State)-[:inputTo]->(t:Transition {sessionId: $sessionId})
            -[:representsExecution]->(lc:LLMCall)
        OPTIONAL MATCH (lc)-[:executesLLM]->(llm:LLM)
        OPTIONAL MATCH (ac:AgentCall)-[:hasLLMCall]->(lc)
        OPTIONAL MATCH (ac)-[:executesAgent]->(agent:Agent)
        OPTIONAL MATCH (t)-[:leadsTo]->(outputState:State)
        RETURN t.id as transitionId,
               lc.startTime as timestamp,
               lc.duration as duration,
               llm.name as modelName,
               llm.provider as provider,
               lc.promptTokenCount as promptTokens,
               lc.completionTokenCount as completionTokens,
               lc.totalTokenCount as totalTokens,
               lc.cacheReadTokenCount as cacheReadTokens,
               lc.temperature as temperature,
               lc.finishReason as finishReason,
               lc.id as executionId,
               agent.name as agentName,
               ac.id as parentAgentExecId,
               inputState.content as inputContent,
               outputState.content as outputContent
        ORDER BY lc.startTime
    """
    return query, {"sessionId": session_id}


# ── Derived-metrics query builders ───────────────────────────────────────────


def _derived_session_filter(session_ids: list[str], dialect: Dialect) -> str:
    """Return a SQL WHERE fragment that matches ``derived_metrics`` rows for the
    given *session_ids*.

    ``derived_metrics.SessionId`` may be stored either as the bare UUID
    (e.g. ``d58b4e48-…``) **or** with an application-name prefix
    (e.g. ``noa-trip-planner-mas_d58b4e48-…``).  Both forms are matched by
    combining an exact ``IN (…)`` clause with a ``LIKE '%_<uuid>'``
    suffix-match per ID.

    The column name differs by dialect:
    * ClickHouse → ``SessionId``
    * SQLite     → ``session_id``
    """
    col = "SessionId" if dialect is Dialect.CLICKHOUSE else "session_id"
    exact = ", ".join(f"'{s}'" for s in session_ids)
    like_clauses = " OR ".join(f"{col} LIKE '%_{s}'" for s in session_ids)
    return f"({col} IN ({exact}) OR {like_clauses})"


def passive_eval_app_avg_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Average ``PassiveEvalApp`` metric fields across sessions.

    The ``Metrics`` column for these rows has the shape::

        {
          "metric_name": "PassiveEvalApp",
          "value": {
            "eval.app.tool_calls": <int>,
            "eval.app.tool_fails": <int>,
            "eval.app.llm_calls": <int>,
            "eval.app.llm_fails": <int>,
            "eval.app.llm_cost": <float>,
            "eval.app.duration": <float>,
            "eval.app.graph_determinism": <float>,
            "eval.app.graph_dynamism": <float>,
            ...
          },
          "category": "application",
          ...
        }

    Returns a single row with columns:
    ``tool_calls, tool_fails, llm_calls, llm_fails, llm_cost,
    duration, graph_determinism, graph_dynamism``.
    """
    sess_filter = _derived_session_filter(session_ids, dialect)

    if dialect is Dialect.SQLITE:
        raw = (
            f"SELECT "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.tool_calls\"') AS REAL)) AS tool_calls, "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.tool_fails\"') AS REAL)) AS tool_fails, "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.llm_calls\"')  AS REAL)) AS llm_calls, "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.llm_fails\"')  AS REAL)) AS llm_fails, "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.llm_cost\"')   AS REAL)) AS llm_cost, "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.duration\"')   AS REAL)) AS duration, "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.graph_determinism\"') AS REAL)) AS graph_determinism, "
            f"  AVG(CAST(json_extract(metrics, '$.value.\"eval.app.graph_dynamism\"')    AS REAL)) AS graph_dynamism "
            f"FROM derived_metrics "
            f"WHERE {sess_filter} "
            f"  AND json_extract(metrics, '$.metric_name') = 'PassiveEvalApp'"
        )
        return text(raw)

    # ClickHouse — value is a nested JSON object
    raw = (
        f"SELECT "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.tool_calls'))        AS tool_calls, "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.tool_fails'))        AS tool_fails, "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.llm_calls'))         AS llm_calls, "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.llm_fails'))         AS llm_fails, "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.llm_cost'))          AS llm_cost, "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.duration'))          AS duration, "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.graph_determinism')) AS graph_determinism, "
        f"  AVG(JSONExtractFloat(Metrics, 'value', 'eval.app.graph_dynamism'))    AS graph_dynamism "
        f"FROM derived_metrics "
        f"WHERE {sess_filter} "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') = 'PassiveEvalApp'"
    )
    return text(raw)


def passive_eval_agents_metrics_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Return raw ``PassiveEvalAgents`` rows from ``derived_metrics``.

    Returns columns ``session_id`` and ``metrics`` (or ClickHouse variants)
    so callers can parse the nested ``value.agents`` payload in Python.
    """
    sess_filter = _derived_session_filter(session_ids, dialect)

    if dialect is Dialect.SQLITE:
        raw = (
            f"SELECT session_id, metrics "
            f"FROM derived_metrics "
            f"WHERE {sess_filter} "
            f"  AND json_extract(metrics, '$.metric_name') = 'PassiveEvalAgents'"
        )
        return text(raw)

    raw = (
        f"SELECT SessionId, Metrics "
        f"FROM derived_metrics "
        f"WHERE {sess_filter} "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') = 'PassiveEvalAgents'"
    )
    return text(raw)


def derived_metric_mce_avg_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    metric_name: str,
    session_ids: list[str],
    with_category: bool = True,
):
    """Average an MCE metric across sessions from ``derived_metrics``.

    Mirrors the Go helpers
    ``GetDerivedMetricMCEAggregatedAvgBySessionIDs`` (when
    *with_category* is True) and
    ``GetDerivedMetricMCEAggregatedAvgBySessionIDsNoCategory`` (when
    *with_category* is False).

    The query first averages per session, then averages across sessions.

    ``derived_metrics.SessionId`` may carry an application-name prefix;
    :func:`_derived_session_filter` handles both bare UUIDs and prefixed forms.

    Returns a single row with column ``metric_avg``.
    """
    sess_filter = _derived_session_filter(session_ids, dialect)

    if dialect is Dialect.SQLITE:
        cat_filter = (
            "AND json_extract(metrics, '$.category') = 'agent'" if with_category else ""
        )
        raw = (
            f"SELECT CASE WHEN count(*) > 0 THEN AVG(MetricValuesAggregated) ELSE 0 END AS metric_avg "
            f"FROM ( "
            f"  SELECT session_id, "
            f"    CASE WHEN count(*) > 0 "
            f"      THEN AVG(CAST(json_extract(metrics, '$.value') AS REAL)) "
            f"      ELSE 0 END AS MetricValuesAggregated "
            f"  FROM derived_metrics "
            f"  WHERE {sess_filter} "
            f"    {cat_filter} "
            f"    AND json_extract(metrics, '$.metric_name') = '{metric_name}' "
            f"  GROUP BY session_id "
            f")"
        )
        return text(raw)

    # ClickHouse
    cat_filter = (
        "AND JSONExtract(Metrics, 'category', 'String') = 'agent'"
        if with_category
        else ""
    )
    raw = (
        f"SELECT if(count() > 0, AVG(MetricValuesAggregated), 0) AS metric_avg "
        f"FROM ( "
        f"  SELECT SessionId, "
        f"    if(count() > 0, AVG(JSONExtract(Metrics, 'value', 'Float64')), 0) AS MetricValuesAggregated "
        f"  FROM derived_metrics "
        f"  WHERE {sess_filter} "
        f"    {cat_filter} "
        f"    AND JSONExtract(Metrics, 'metric_name', 'String') = '{metric_name}' "
        f"  GROUP BY SessionId "
        f")"
    )
    return text(raw)


def session_metrics_by_name_query(
    dialect: Dialect = Dialect.NEO4J,
    *,
    session_ids: list[str],
    metric_names: list[str],
):
    """Build a Neo4j Cypher query for per-session ``Metric`` nodes by name.

    Matches ``Session`` nodes that have ``hasMetric`` relationships to
    ``Metric`` nodes whose ``metricName`` is in *metric_names*.

    Returns a ``(cypher_string, params_dict)`` tuple.  Each result row
    has columns: ``sid, metric_name, metric_results``.
    """
    if dialect is not Dialect.NEO4J:
        raise NotImplementedError(
            f"session_metrics_by_name_query: dialect {dialect!r} not supported"
        )
    stmt = """
    MATCH (s:Session)-[:hasMetric]->(m:Metric)
    WHERE s.sessionId IN $session_ids
      AND m.metricName IN $metric_names
    WITH s.sessionId AS sid, m.metricName AS metric_name,
         collect(m.metricResult) AS metric_results
    RETURN sid, metric_name, metric_results
    """
    return stmt, {"session_ids": session_ids, "metric_names": metric_names}


def all_mce_metrics_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
):
    """Fetch all five MCE performance metrics for a set of sessions in one query.

    ClickHouse only.  Returns one row per ``SessionId`` with columns:
    ``session_id, workflow_efficiency, app_groundedness, answer_relevancy,
    response_completeness, tool_utilization_accuracy``.

    Each column holds the per-session average value for that metric (0 when the
    session has no rows for that metric).  The caller is responsible for
    aggregating across sessions to produce a per-application average.

    The five metrics and their ``with_category`` semantics:
    * ``WorkflowEfficiency``     — category = 'agent'
    * ``GroundednessMetric``     — category = 'agent'
    * ``AnswerRelevancyMetric``  — no category filter
    * ``ResponseCompleteness``   — category = 'agent'
    * ``ToolUtilizationAccuracy``— no category filter
    """
    sess_filter = _derived_session_filter(session_ids, dialect)

    def _cond_avg(metric: str, with_cat: bool) -> str:
        """Build a ``if(countIf(…) > 0, avgIf(…), NULL)`` fragment.

        Returns NULL (not 0) when the session has no rows for this metric so
        that sessions lacking a particular metric are excluded from the
        per-metric average in the caller — matching the behaviour of the
        non-optimised ``derived_metric_mce_avg_by_sessions_query``.
        """
        name_cond = f"JSONExtract(Metrics, 'metric_name', 'String') = '{metric}'"
        cat_cond = (
            " AND JSONExtract(Metrics, 'category', 'String') = 'agent'"
            if with_cat
            else ""
        )
        val = "JSONExtract(Metrics, 'value', 'Float64')"
        full_cond = f"{name_cond}{cat_cond}"
        return f"if(countIf({full_cond}) > 0, avgIf({val}, {full_cond}), NULL)"

    raw = (
        f"SELECT "
        f"  SessionId AS session_id, "
        f"  {_cond_avg('WorkflowEfficiency', True)} AS workflow_efficiency, "
        f"  {_cond_avg('GroundednessMetric', True)} AS app_groundedness, "
        f"  {_cond_avg('AnswerRelevancyMetric', False)} AS answer_relevancy, "
        f"  {_cond_avg('ResponseCompleteness', True)} AS response_completeness, "
        f"  {_cond_avg('ToolUtilizationAccuracy', False)} AS tool_utilization_accuracy "
        f"FROM derived_metrics "
        f"WHERE {sess_filter} "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') IN ("
        f"    'WorkflowEfficiency', 'GroundednessMetric', 'AnswerRelevancyMetric', "
        f"    'ResponseCompleteness', 'ToolUtilizationAccuracy'"
        f"  ) "
        f"GROUP BY SessionId"
    )
    return text(raw)


def derived_metric_sdk_avg_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    metric_name: str,
    session_ids: list[str],
):
    """Average an SDK metric across sessions from ``derived_metrics``.

    Mirrors the Go helper ``GetDerivedMetricSDKAggregatedAvgBySessionIDs``.

    SDK metrics have ``metric_name = 'PassiveEvalApp'`` and the
    ``value`` field is a JSON **string** containing nested keys such as
    ``eval.app.llm_cost``, ``eval.app.llm_calls``, etc.

    Returns a single row with column ``metric_avg``.
    """
    ids_literal = ", ".join(f"'{s}'" for s in session_ids)

    if dialect is Dialect.SQLITE:
        raw = (
            f"SELECT CASE WHEN count(*) > 0 "
            f"  THEN AVG(CAST(json_extract(json_extract(metrics, '$.value'), '$.{metric_name}') AS REAL)) "
            f"  ELSE 0 END AS metric_avg "
            f"FROM derived_metrics "
            f"WHERE session_id IN ({ids_literal}) "
            f"  AND json_extract(metrics, '$.metric_name') = 'PassiveEvalApp' "
            f"  AND json_extract(json_extract(metrics, '$.value'), '$.{metric_name}') IS NOT NULL"
        )
        return text(raw)

    # ClickHouse
    raw = (
        f"SELECT if(count() > 0, "
        f"  AVG(JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{metric_name}', 'Float64')), 0) "
        f"  AS metric_avg "
        f"FROM derived_metrics "
        f"WHERE SessionId IN ({ids_literal}) "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') = 'PassiveEvalApp' "
        f"  AND JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{metric_name}', 'Float64') IS NOT NULL"
    )
    return text(raw)


def derived_metric_sdk_sum_fails_by_sessions_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    llm_fails_key: str = "eval.app.llm_fails",
    tool_fails_key: str = "eval.app.tool_fails",
):
    """Sum LLM and tool failure counts from SDK metrics.

    Mirrors the Go helper ``GetDerivedMetricSDKAggregatedSumOfFailsBySessionIDs``.

    Returns a single row with columns ``llm_fails`` and ``tool_fails``.
    """
    ids_literal = ", ".join(f"'{s}'" for s in session_ids)

    if dialect is Dialect.SQLITE:
        raw = (
            f"SELECT "
            f"  CASE WHEN count(*) > 0 "
            f"    THEN COALESCE(SUM(CAST(json_extract(json_extract(metrics, '$.value'), '$.{llm_fails_key}') AS REAL)), 0) "
            f"    ELSE 0 END AS llm_fails, "
            f"  CASE WHEN count(*) > 0 "
            f"    THEN COALESCE(SUM(CAST(json_extract(json_extract(metrics, '$.value'), '$.{tool_fails_key}') AS REAL)), 0) "
            f"    ELSE 0 END AS tool_fails "
            f"FROM derived_metrics "
            f"WHERE session_id IN ({ids_literal}) "
            f"  AND json_extract(metrics, '$.metric_name') = 'PassiveEvalApp'"
        )
        return text(raw)

    # ClickHouse
    raw = (
        f"SELECT "
        f"  if(count() > 0, SUM(JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{llm_fails_key}', 'Float64')), 0) AS llm_fails, "
        f"  if(count() > 0, SUM(JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{tool_fails_key}', 'Float64')), 0) AS tool_fails "
        f"FROM derived_metrics "
        f"WHERE SessionId IN ({ids_literal}) "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') = 'PassiveEvalApp'"
    )
    return text(raw)


def most_frequent_errors_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    top_n: int = 3,
):
    """Return the *top_n* most frequent error span names for the given sessions.

    Mirrors the Go helper ``GetMostFrequentErrorsBySessionIDs``.

    Returns rows with columns ``error_name`` and ``cnt``.
    """
    r = _refs(dialect)

    status_col = r.status_code
    # Use status_message for error name when available, fall back to span_name
    if dialect is Dialect.SQLITE:
        error_name_expr = func.coalesce(
            column("status_message"),
            r.span_name,
        )
    else:
        error_name_expr = func.coalesce(
            column("StatusMessage"),
            r.span_name,
        )

    return (
        select(
            error_name_expr.label("error_name"),
            func.count().label("cnt"),
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(status_col == "Error")
        .where(error_name_expr != "")
        .group_by(error_name_expr)
        .order_by(func.count().desc())
        .limit(top_n)
    )


def derived_metric_sdk_avg_by_sessions_and_agent_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    metric_name: str,
    session_ids: list[str],
    agent_id: str,
):
    """Average an SDK metric across sessions filtered by agent.

    Like :func:`derived_metric_sdk_avg_by_sessions_query` but additionally
    filters rows where the ``agent_id`` column matches *agent_id*.

    Returns a single row with column ``metric_avg``.
    """
    ids_literal = ", ".join(f"'{s}'" for s in session_ids)

    if dialect is Dialect.SQLITE:
        raw = (
            f"SELECT CASE WHEN count(*) > 0 "
            f"  THEN AVG(CAST(json_extract(json_extract(metrics, '$.value'), '$.{metric_name}') AS REAL)) "
            f"  ELSE 0 END AS metric_avg "
            f"FROM derived_metrics "
            f"WHERE session_id IN ({ids_literal}) "
            f"  AND json_extract(metrics, '$.metric_name') = 'PassiveEvalApp' "
            f"  AND json_extract(json_extract(metrics, '$.value'), '$.{metric_name}') IS NOT NULL "
            f"  AND agent_id = '{agent_id}'"
        )
        return text(raw)

    # ClickHouse
    raw = (
        f"SELECT if(count() > 0, "
        f"  AVG(JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{metric_name}', 'Float64')), 0) "
        f"  AS metric_avg "
        f"FROM derived_metrics "
        f"WHERE SessionId IN ({ids_literal}) "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') = 'PassiveEvalApp' "
        f"  AND JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{metric_name}', 'Float64') IS NOT NULL "
        f"  AND agent_id = '{agent_id}'"
    )
    return text(raw)


def derived_metric_sdk_sum_by_sessions_and_agent_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    metric_name: str,
    session_ids: list[str],
    agent_id: str,
):
    """Sum an SDK metric across sessions filtered by agent.

    Like the avg variant but uses ``SUM`` instead of ``AVG``.

    Returns a single row with column ``metric_sum``.
    """
    ids_literal = ", ".join(f"'{s}'" for s in session_ids)

    if dialect is Dialect.SQLITE:
        raw = (
            f"SELECT CASE WHEN count(*) > 0 "
            f"  THEN COALESCE(SUM(CAST(json_extract(json_extract(metrics, '$.value'), '$.{metric_name}') AS REAL)), 0) "
            f"  ELSE 0 END AS metric_sum "
            f"FROM derived_metrics "
            f"WHERE session_id IN ({ids_literal}) "
            f"  AND json_extract(metrics, '$.metric_name') = 'PassiveEvalApp' "
            f"  AND json_extract(json_extract(metrics, '$.value'), '$.{metric_name}') IS NOT NULL "
            f"  AND agent_id = '{agent_id}'"
        )
        return text(raw)

    # ClickHouse
    raw = (
        f"SELECT if(count() > 0, "
        f"  COALESCE(SUM(JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{metric_name}', 'Float64')), 0), 0) "
        f"  AS metric_sum "
        f"FROM derived_metrics "
        f"WHERE SessionId IN ({ids_literal}) "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') = 'PassiveEvalApp' "
        f"  AND JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{metric_name}', 'Float64') IS NOT NULL "
        f"  AND agent_id = '{agent_id}'"
    )
    return text(raw)


def derived_metric_sdk_sum_fails_by_sessions_and_agent_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
    llm_fails_key: str = "eval.app.llm_fails",
    tool_fails_key: str = "eval.app.tool_fails",
):
    """Sum LLM and tool failure counts from SDK metrics, filtered by agent.

    Returns a single row with columns ``llm_fails`` and ``tool_fails``.
    """
    ids_literal = ", ".join(f"'{s}'" for s in session_ids)

    if dialect is Dialect.SQLITE:
        raw = (
            f"SELECT "
            f"  CASE WHEN count(*) > 0 "
            f"    THEN COALESCE(SUM(CAST(json_extract(json_extract(metrics, '$.value'), '$.{llm_fails_key}') AS REAL)), 0) "
            f"    ELSE 0 END AS llm_fails, "
            f"  CASE WHEN count(*) > 0 "
            f"    THEN COALESCE(SUM(CAST(json_extract(json_extract(metrics, '$.value'), '$.{tool_fails_key}') AS REAL)), 0) "
            f"    ELSE 0 END AS tool_fails "
            f"FROM derived_metrics "
            f"WHERE session_id IN ({ids_literal}) "
            f"  AND json_extract(metrics, '$.metric_name') = 'PassiveEvalApp' "
            f"  AND agent_id = '{agent_id}'"
        )
        return text(raw)

    # ClickHouse
    raw = (
        f"SELECT "
        f"  if(count() > 0, SUM(JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{llm_fails_key}', 'Float64')), 0) AS llm_fails, "
        f"  if(count() > 0, SUM(JSONExtract(JSONExtract(Metrics, 'value', 'String'), '{tool_fails_key}', 'Float64')), 0) AS tool_fails "
        f"FROM derived_metrics "
        f"WHERE SessionId IN ({ids_literal}) "
        f"  AND JSONExtract(Metrics, 'metric_name', 'String') = 'PassiveEvalApp' "
        f"  AND agent_id = '{agent_id}'"
    )
    return text(raw)


def derived_metric_mce_avg_by_sessions_and_agent_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    metric_name: str,
    session_ids: list[str],
    agent_id: str,
    with_category: bool = True,
):
    """Average an MCE metric across sessions filtered by agent.

    Like :func:`derived_metric_mce_avg_by_sessions_query` but additionally
    filters rows where the ``agent_id`` column matches *agent_id*.

    Returns a single row with column ``metric_avg``.
    """
    sess_filter = _derived_session_filter(session_ids, dialect)

    if dialect is Dialect.SQLITE:
        cat_filter = (
            "AND json_extract(metrics, '$.category') = 'agent'" if with_category else ""
        )
        raw = (
            f"SELECT CASE WHEN count(*) > 0 THEN AVG(MetricValuesAggregated) ELSE 0 END AS metric_avg "
            f"FROM ( "
            f"  SELECT session_id, "
            f"    CASE WHEN count(*) > 0 "
            f"      THEN AVG(CAST(json_extract(metrics, '$.value') AS REAL)) "
            f"      ELSE 0 END AS MetricValuesAggregated "
            f"  FROM derived_metrics "
            f"  WHERE {sess_filter} "
            f"    {cat_filter} "
            f"    AND json_extract(metrics, '$.metric_name') = '{metric_name}' "
            f"    AND agent_id = '{agent_id}' "
            f"  GROUP BY session_id "
            f")"
        )
        return text(raw)

    # ClickHouse
    cat_filter = (
        "AND JSONExtract(Metrics, 'category', 'String') = 'agent'"
        if with_category
        else ""
    )
    raw = (
        f"SELECT if(count() > 0, AVG(MetricValuesAggregated), 0) AS metric_avg "
        f"FROM ( "
        f"  SELECT SessionId, "
        f"    if(count() > 0, AVG(JSONExtract(Metrics, 'value', 'Float64')), 0) AS MetricValuesAggregated "
        f"  FROM derived_metrics "
        f"  WHERE {sess_filter} "
        f"    {cat_filter} "
        f"    AND JSONExtract(Metrics, 'metric_name', 'String') = '{metric_name}' "
        f"    AND agent_id = '{agent_id}' "
        f"  GROUP BY SessionId "
        f")"
    )
    return text(raw)


def agent_durations_sorted_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
):
    """Return sorted durations (ms) for ``.agent`` spans, for percentile computation.

    Returns rows with column ``duration_ms``, ordered ascending.
    """
    r = _refs(dialect)

    return (
        select(
            (r.duration / literal_column("1000000")).label("duration_ms"),
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.agent_id == agent_id)
        .where(r.span_name.like("%.agent"))
        .order_by(r.duration.asc())
    )


def most_frequent_errors_by_agent_query(
    dialect: Dialect = Dialect.CLICKHOUSE,
    *,
    session_ids: list[str],
    agent_id: str,
    top_n: int = -1,
):
    """Return the most frequent error span names for a specific agent.

    When *top_n* is ``-1`` (default), all errors are returned (no limit).

    Returns rows with columns ``error_name`` and ``cnt``.
    """
    r = _refs(dialect)

    if dialect is Dialect.SQLITE:
        error_name_expr = func.coalesce(
            column("status_message"),
            r.span_name,
        )
    else:
        error_name_expr = func.coalesce(
            column("StatusMessage"),
            r.span_name,
        )

    stmt = (
        select(
            error_name_expr.label("error_name"),
            func.count().label("cnt"),
        )
        .select_from(r.tbl)
        .where(r.session_id.in_(session_ids))
        .where(r.agent_id == agent_id)
        .where(r.status_code == "Error")
        .where(error_name_expr != "")
        .group_by(error_name_expr)
        .order_by(func.count().desc())
    )

    if top_n > 0:
        stmt = stmt.limit(top_n)

    return stmt


# ── SLIM / agentic-protocols metrics (ClickHouse only) ───────────────────────

_SLIM_AGENT_ATTR = literal_column("Attributes['agent']")


def slim_agent_names_sum_query(
    *,
    app_prefix: str,
    metric_name: str,
    start_time: str,
    end_time: str,
):
    """Return distinct agent names from ``otel_metrics_sum`` for *app_prefix*.

    Columns: ``agent``.
    """
    return (
        select(func.distinct(_SLIM_AGENT_ATTR).label("agent"))
        .select_from(_ch_metrics_sum)
        .where(_SLIM_AGENT_ATTR.like(app_prefix + "%"))
        .where(_ch_metrics_sum.c.MetricName == metric_name)
        .where(_ch_metrics_sum.c.TimeUnix >= start_time)
        .where(_ch_metrics_sum.c.TimeUnix <= end_time)
    )


def slim_sum_values_by_agent_query(
    *,
    agent_name: str,
    metric_name: str,
    start_time: str,
    end_time: str,
):
    """Return ordered distinct ``Value`` rows from ``otel_metrics_sum`` for one agent.

    Columns: ``value``.
    """
    return (
        select(func.distinct(_ch_metrics_sum.c.Value).label("value"))
        .select_from(_ch_metrics_sum)
        .where(_SLIM_AGENT_ATTR == agent_name)
        .where(_ch_metrics_sum.c.MetricName == metric_name)
        .where(_ch_metrics_sum.c.TimeUnix >= start_time)
        .where(_ch_metrics_sum.c.TimeUnix <= end_time)
        .order_by(_ch_metrics_sum.c.TimeUnix.asc())
    )


def slim_agent_names_histogram_query(
    *,
    app_prefix: str,
    metric_name: str,
    start_time: str,
    end_time: str,
):
    """Return distinct agent names from ``otel_metrics_histogram`` for *app_prefix*.

    Columns: ``agent``.
    """
    return (
        select(func.distinct(_SLIM_AGENT_ATTR).label("agent"))
        .select_from(_ch_metrics_histogram)
        .where(_SLIM_AGENT_ATTR.like(app_prefix + "%"))
        .where(_ch_metrics_histogram.c.MetricName == metric_name)
        .where(_ch_metrics_histogram.c.TimeUnix >= start_time)
        .where(_ch_metrics_histogram.c.TimeUnix <= end_time)
    )


def slim_histogram_values_by_agent_query(
    *,
    agent_name: str,
    metric_name: str,
    start_time: str,
    end_time: str,
):
    """Return ordered distinct ``(Count, Sum)`` rows from ``otel_metrics_histogram`` for one agent.

    Columns: ``count``, ``sum``.
    """
    return (
        select(
            func.distinct(_ch_metrics_histogram.c.Count).label("count"),
            _ch_metrics_histogram.c.Sum.label("sum"),
        )
        .select_from(_ch_metrics_histogram)
        .where(_SLIM_AGENT_ATTR == agent_name)
        .where(_ch_metrics_histogram.c.MetricName == metric_name)
        .where(_ch_metrics_histogram.c.TimeUnix >= start_time)
        .where(_ch_metrics_histogram.c.TimeUnix <= end_time)
        .order_by(_ch_metrics_histogram.c.TimeUnix.asc())
    )
