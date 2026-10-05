#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **Metrics** feature domain.

Provides Cypher query builders for session-level and span-level metric
retrieval from Neo4j, with optional sub-graph expansion controlled by
a ``hops`` parameter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _to_iso(value: str) -> str:
    """Normalise a timestamp to ISO-8601 with timezone for Neo4j ``datetime()``.

    Accepts epoch seconds/millis (plain numeric string) or ISO-8601 strings.
    Always returns a timezone-aware ISO string ending with ``+00:00``.
    """
    try:
        numeric = float(value)
        # Heuristic: values > 1e12 are epoch millis, otherwise seconds
        if numeric > 1e12:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
    except ValueError:
        pass
    # Already ISO-8601; ensure it has a timezone suffix for Neo4j
    if value.endswith("Z"):
        return value[:-1] + "+00:00"
    return value


def session_metrics_query(
    session_id: str,
    *,
    hops: int = 1,
) -> tuple[str, dict[str, Any]]:
    """Return metrics for a session, with optional sub-graph of *hops* depth.

    When ``hops`` is 0, only the metrics directly attached to the session node
    are returned.  Each additional hop expands the traversal through related
    nodes (states, spans, embeddings, etc.) and collects any metric nodes
    encountered along the way.
    """
    if hops <= 0:
        query = """
        MATCH (session:Session {sessionId: $session_id})
        OPTIONAL MATCH (session)-[:hasMetric]->(m:Metric)
        RETURN
            session.sessionId AS sessionId,
            collect(DISTINCT {
                name: m.metricName,
                result: m.metricResult,
                value: m.value,
                provider: m.provider,
                metric_id: coalesce(m.metricId, m.metricName),
                source: m.source,
                reasoning: m.reasoning
            }) AS metrics,
            null AS subgraph
        """
    else:
        query = f"""
        MATCH (session:Session {{sessionId: $session_id}})
        OPTIONAL MATCH (session)-[:hasMetric]->(m:Metric)
        WITH session, collect(DISTINCT {{
            name: m.metricName,
            result: m.metricResult,
            value: m.value,
            provider: m.provider,
            metric_id: coalesce(m.metricId, m.metricName),
            source: m.source,
            reasoning: m.reasoning
        }}) AS metrics
        OPTIONAL MATCH path = (session)-[*1..{hops}]-(related)
        WITH session, metrics,
             collect(DISTINCT {{
                 id: elementId(related),
                 labels: labels(related),
                 properties: properties(related)
             }}) AS nodes,
             collect(DISTINCT {{
                 type: type(relationships(path)[-1]),
                 startId: elementId(startNode(relationships(path)[-1])),
                 endId: elementId(endNode(relationships(path)[-1]))
             }}) AS edges
        RETURN
            session.sessionId AS sessionId,
            metrics,
            {{nodes: nodes, edges: edges}} AS subgraph
        """
    return query, {"session_id": session_id}


def span_metrics_query(
    span_id: str,
    *,
    session_id: str | None = None,
    hops: int = 1,
) -> tuple[str, dict[str, Any]]:
    """Return metrics for a span, with optional sub-graph of *hops* depth.

    If *session_id* is also given the match is stricter, but it is not
    required — the query works with ``span_id`` alone.
    """
    # Build the anchor match
    if session_id:
        anchor = (
            "MATCH (session:Session {sessionId: $session_id})"
            "-[:hasSpan]->(span:Span {spanId: $span_id})"
        )
    else:
        anchor = "MATCH (span:Span {spanId: $span_id})"

    if hops <= 0:
        query = f"""
        {anchor}
        OPTIONAL MATCH (span)-[:hasMetric]->(m:Metric)
        RETURN
            span.spanId AS spanId,
            collect(DISTINCT {{
                name: m.metricName,
                result: m.metricResult,
                value: m.value,
                provider: m.provider,
                metric_id: coalesce(m.metricId, m.metricName),
                source: m.source,
                reasoning: m.reasoning
            }}) AS metrics,
            null AS subgraph
        """
    else:
        query = f"""
        {anchor}
        OPTIONAL MATCH (span)-[:hasMetric]->(m:Metric)
        WITH span, collect(DISTINCT {{
            name: m.metricName,
            result: m.metricResult,
            value: m.value,
            provider: m.provider,
            metric_id: coalesce(m.metricId, m.metricName),
            source: m.source,
            reasoning: m.reasoning
        }}) AS metrics
        OPTIONAL MATCH path = (span)-[*1..{hops}]-(related)
        WITH span, metrics,
             collect(DISTINCT {{
                 id: elementId(related),
                 labels: labels(related),
                 properties: properties(related)
             }}) AS nodes,
             collect(DISTINCT {{
                 type: type(relationships(path)[-1]),
                 startId: elementId(startNode(relationships(path)[-1])),
                 endId: elementId(endNode(relationships(path)[-1]))
             }}) AS edges
        RETURN
            span.spanId AS spanId,
            metrics,
            {{nodes: nodes, edges: edges}} AS subgraph
        """

    params: dict[str, Any] = {"span_id": span_id}
    if session_id:
        params["session_id"] = session_id
    return query, params


# ── write queries ─────────────────────────────────────────────────────────────


def write_session_metric_query(
    session_id: str,
    metric_name: str,
    metric_value: float | None,
    provider: str = "API",
    metric_id: str = "",
    source: str = "",
    reasoning: str = "",
) -> tuple[str, dict[str, Any]]:
    """Build a MERGE query to attach a metric to a session node."""
    now = datetime.now(timezone.utc).isoformat()
    query = """
    MERGE (session:Session {sessionId: $session_id})
    MERGE (session)-[:hasMetric]->(m:Metric {metricName: $metric_name, resourceId: $session_id})
    SET m.metricResult = $metric_result,
        m.value        = $metric_value,
        m.provider     = $provider,
        m.metricId     = $metric_id,
        m.source       = $source,
        m.reasoning    = $reasoning,
        m.timestamp    = datetime($timestamp)
    RETURN session.sessionId AS sessionId, m.metricName AS metricName
    """
    return query, {
        "session_id": session_id,
        "metric_name": metric_name,
        "metric_result": metric_value,
        "metric_value": metric_value,
        "provider": provider,
        "metric_id": metric_id,
        "source": source,
        "reasoning": reasoning,
        "timestamp": now,
    }


def write_span_metric_query(
    session_id: str,
    span_id: str,
    metric_name: str,
    metric_value: float | None,
    provider: str = "API",
    metric_id: str = "",
    source: str = "",
    reasoning: str = "",
) -> tuple[str, dict[str, Any]]:
    """Build a MERGE query to attach a metric to a span node."""
    now = datetime.now(timezone.utc).isoformat()
    query = """
    MERGE (session:Session {sessionId: $session_id})
    MERGE (session)-[:hasSpan]->(span:Span {spanId: $span_id})
    MERGE (span)-[:hasMetric]->(m:Metric {metricName: $metric_name, resourceId: $span_id})
    SET m.metricResult = $metric_result,
        m.value        = $metric_value,
        m.provider     = $provider,
        m.metricId     = $metric_id,
        m.source       = $source,
        m.reasoning    = $reasoning,
        m.timestamp    = datetime($timestamp)
    RETURN span.spanId AS spanId, m.metricName AS metricName
    """
    return query, {
        "session_id": session_id,
        "span_id": span_id,
        "metric_name": metric_name,
        "metric_result": metric_value,
        "metric_value": metric_value,
        "provider": provider,
        "metric_id": metric_id,
        "source": source,
        "reasoning": reasoning,
        "timestamp": now,
    }


# ── category / application-level read queries ────────────────────────────────


def metrics_query(
    application_id: str,
    metric_names: list[str],
    *,
    agent_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return metrics for an application filtered by a list of metric names.

    Traversal (no agent filter):
        ``Session -[:executesSession]-> MAS {id}``
        ``Session -[:hasMetric|measuresCall]- Metric``
    Traversal (with agent filter):
        ``Session -[:executesSession]-> MAS {id}``
        ``Session -[:hasSpan]-> Span {agentId} -[:hasMetric|measuresCall]- Metric``

    Both ``hasMetric`` (Session→Metric) and ``measuresCall``
    (Metric→Session) relationship directions are supported.
    """
    time_clauses: list[str] = []
    params: dict[str, Any] = {
        "application_id": application_id,
        "metric_names": metric_names,
    }

    if start_time:
        params["start_time"] = _to_iso(start_time)
        time_clauses.append("m.timestamp >= datetime($start_time)")
    if end_time:
        params["end_time"] = _to_iso(end_time)
        time_clauses.append("m.timestamp <= datetime($end_time)")

    where = ""
    if time_clauses:
        where = "AND " + " AND ".join(time_clauses)

    span_metric_filter = ""

    if agent_id:
        params["agent_id"] = agent_id
        # Filter to sessions where the named agent participated.
        # Return both session-attached metrics and span-attached metrics
        # for spans associated with the requested agent.
        query = f"""
        MATCH (s:Session)-[:executesSession]->(:MAS {{id: $application_id}})
        WHERE EXISTS {{
            MATCH (a:AgentCall {{sessionId: s.sessionId, agentName: $agent_id}})
        }}
        CALL (s) {{
            MATCH (s)-[:hasMetric|measuresCall]-(m:Metric)
            WHERE m.metricName IN $metric_names
            {where}
            RETURN
                s.sessionId    AS sessionId,
                m.metricName   AS metricName,
                m.metricResult AS metricResult,
                m.value        AS value,
                m.provider     AS provider,
                coalesce(m.metricId, m.metricName) AS metricId,
                m.source       AS source,
                m.reasoning    AS reasoning,
                m.timestamp    AS timestamp

            UNION

            MATCH (s)-[:hasSpan]->(span:Span)-[:hasMetric|measuresCall]-(m:Metric)
            WHERE m.metricName IN $metric_names
                        {span_metric_filter}
                            AND (
                                coalesce(span.agentId, span.agentName, span.agent_id) = $agent_id
                                OR EXISTS {{
                                        MATCH (ac:AgentCall {{sessionId: s.sessionId, agentName: $agent_id}})
                                        WHERE coalesce(ac.spanId, ac.span_id) = span.spanId
                                }}
                                OR EXISTS {{
                                        MATCH (ac:AgentCall {{sessionId: s.sessionId, agentName: $agent_id}})-[:invokesTool|invokesLLM]->(exec)
                                        WHERE coalesce(exec.spanId, exec.span_id) = span.spanId
                                }}
                            )
            {where}
            RETURN
                s.sessionId    AS sessionId,
                m.metricName   AS metricName,
                m.metricResult AS metricResult,
                m.value        AS value,
                m.provider     AS provider,
                coalesce(m.metricId, m.metricName) AS metricId,
                m.source       AS source,
                m.reasoning    AS reasoning,
                m.timestamp    AS timestamp
        }}
        RETURN DISTINCT
            sessionId,
            metricName,
            metricResult,
            value,
            provider,
            metricId,
            source,
            reasoning,
            timestamp
        ORDER BY metricName, timestamp
        """
    else:
        query = f"""
        MATCH (s:Session)-[:executesSession]->(:MAS {{id: $application_id}})
        MATCH (s)-[:hasMetric|measuresCall]-(m:Metric)
        WHERE m.metricName IN $metric_names
        {where}
        RETURN
            s.sessionId    AS sessionId,
            m.metricName   AS metricName,
            m.metricResult AS metricResult,
            m.value        AS value,
            m.provider     AS provider,
            coalesce(m.metricId, m.metricName) AS metricId,
            m.source       AS source,
            m.reasoning    AS reasoning,
            m.timestamp    AS timestamp
        ORDER BY m.metricName, m.timestamp
        """
    return query, params


# ── delete / aggregation queries ─────────────────────────────────────────────


def clean_metrics_query(session_id: str | None) -> tuple[str, dict[str, Any]]:
    """Build a DELETE query for metric nodes.

    When *session_id* is given only the metrics attached to that session
    (and its child nodes) are deleted.  When *None* all Metric nodes are
    removed.
    """
    if session_id:
        return (
            """
            MATCH (r)-[:hasMetric]->(m:Metric)
            WHERE r.sessionId = $sid OR (r:Session AND r.sessionId = $sid)
            DETACH DELETE m
            RETURN count(m) AS deleted
            """,
            {"sid": session_id},
        )
    return (
        "MATCH (m:Metric) DETACH DELETE m RETURN count(m) AS deleted",
        {},
    )


def metrics_over_time_query(
    metric_id: str,
    start: datetime,
    end: datetime | None,
    bucket: str,
    app_name: str | None,
    agent_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """Build a time-bucketed aggregation query for a single metric.

    Returns per-bucket avg/min/max/count over all sessions in the range.
    ``bucket`` must be a valid ``datetime.truncate`` unit (minute / hour / day).
    """
    where_parts = [
        "m.timestamp >= datetime($start)",
        "m.value IS NOT NULL",
    ]
    params: dict[str, Any] = {
        "metric_id": metric_id,
        "start": start.isoformat(),
        "bucket": bucket,
    }
    if end is not None:
        where_parts.append("m.timestamp <= datetime($end)")
        params["end"] = end.isoformat()
    if app_name is not None:
        where_parts.append("s.appName = $app_name")
        params["app_name"] = app_name
    if agent_id is not None:
        where_parts.append(
            "EXISTS { MATCH (s)-[:hasSpan]->(:Span {agentId: $agent_id}) }"
        )
        params["agent_id"] = agent_id

    where_clause = "\n  AND ".join(where_parts)
    query = f"""
    MATCH (s:Session)-[:hasMetric]->(m:Metric {{metricName: $metric_id}})
    WHERE {where_clause}
    WITH datetime.truncate($bucket, m.timestamp) AS bucket,
         toFloat(m.value) AS v
    RETURN toString(bucket) AS bucket,
           avg(v)          AS avg_value,
           min(v)          AS min_value,
           max(v)          AS max_value,
           count(*)        AS n_sessions
    ORDER BY bucket
    """
    return query, params


def write_generic_metric_query(
    resource_id: str,
    metric_name: str,
    metric_value: float | None,
    provider: str = "API",
    metric_id: str = "",
    source: str = "",
    reasoning: str = "",
) -> tuple[str, dict[str, Any]]:
    """Build a MERGE query to attach a metric to a Session OR Span node.

    This handles both Session nodes (sessionId) and Span nodes (spanId)
    without forcing the creation of a restricted :Session node when the ID
    actually belongs to a Span.
    """
    now = datetime.now(timezone.utc).isoformat()

    query = """
    OPTIONAL MATCH (s:Session {sessionId: $resource_id})
    OPTIONAL MATCH (p:Span {spanId: $resource_id})
    WITH coalesce(s, p) as node
    WHERE node IS NOT NULL
    MERGE (node)-[:hasMetric]->(m:Metric {metricName: $metric_name, resourceId: $resource_id})
    SET m.metricResult = $metric_result,
        m.value        = $metric_value,
        m.provider     = $provider,
        m.metricId     = $metric_id,
        m.source       = $source,
        m.reasoning    = $reasoning,
        m.timestamp    = datetime($timestamp)
    RETURN elementId(node) as nodeId, m.metricName AS metricName
    """
    return query, {
        "resource_id": resource_id,
        "metric_name": metric_name,
        "metric_result": metric_value,
        "metric_value": metric_value,
        "provider": provider,
        "metric_id": metric_id,
        "source": source,
        "reasoning": reasoning,
        "timestamp": now,
    }


# Needed for demo
# TODO fix


def get_application_metrics_timeline(
    application_id: str,
    metrics: list[str],
    start_time: str | None = None,
    end_time: str | None = None,
) -> tuple[str, dict[str, Any]]:
    params = {"application_id": application_id, "metrics": metrics}
    query = """
    MATCH (s:Session)-[]-(mas:MAS {id: $application_id})
        MATCH (s)-[]-(m:Metric)
    WHERE m.metricName IN $metrics
            AND m.metricName IS NOT NULL
            AND s.startTime IS NOT NULL
            AND m.metricResult IS NOT NULL
    WITH m.metricName AS metricName, s.startTime AS startTime, m.metricResult AS metricValue
    ORDER BY s.startTime
    RETURN
        metricName,
        collect([startTime, metricValue]) AS dataPoints
    """

    return query, params


def reliability_metrics(
    application_id: str,
    start_time: str | None = None,
    end_time: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Reliability sub-scores for the application's health score.

    ``ConsistencyReport`` isn't linked to ``MAS`` directly -- it's scoped
    to the application via the ``SemanticGroup`` whose sessions it was
    computed over (``ConsistencyReport -[:ofSemanticGroup]-> SemanticGroup
    -[:containsSession]-> Session -[:executesSession]-> MAS``), so that
    walk is used instead of matching ``ConsistencyReport`` globally across
    every application.
    """
    params = {"application_id": application_id}
    query = """
    // Consistency (scoped to this application via its semantic groups' sessions)
    MATCH (cr:ConsistencyReport)-[:ofSemanticGroup]->(:SemanticGroup)
        -[:containsSession]->(:Session)-[:executesSession]->(:MAS {id: $application_id})
    WITH DISTINCT cr
    WITH cr.dataType AS rawType, AVG(cr.mean) AS Reliability
    WITH (CASE rawType
        WHEN 'metric' THEN 'MetricConsistency'
        WHEN 'graph'  THEN 'GraphConsistency'
        WHEN 'text'   THEN 'TextConsistency'
        ELSE rawType END) AS DataType, Reliability
    WITH collect({col1: DataType, col2: Reliability}) AS reliabilityStats

    // Completion Rate
    MATCH (m:Metric)-[]-(s:Session)-[]-(mas:MAS {id:$application_id})
    WHERE m.metricName IN ['ToolErrorRate', 'LLMErrorRate']
    WITH reliabilityStats, 1 - AVG(m.metricResult) AS CompletionRate

    WITH reliabilityStats + [{col1: "CompletionRate", col2: CompletionRate}] AS finalResults
    UNWIND finalResults AS row
    RETURN row.col1 AS metricName, row.col2 AS metricResult
    """

    return query, params
