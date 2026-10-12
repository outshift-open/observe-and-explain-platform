#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **Metrics** feature domain.

Provides Cypher query builders for session-level and span-level metric
retrieval from Neo4j, with optional sub-graph expansion controlled by
a ``hops`` parameter.

Metrics are read from the ontology model written by
:mod:`oxp.query_builders.metric_graph`::

    (r:MetricResult)-[:ofMetricType]->(d:Metric)   # d is the definition
    (r:MetricResult)-[:measures]->(t)              # Session or execution element

The "span" of the API is the execution element (``LLMCall``, ``ToolCall``,
``AgentCall``...) carrying that ``spanId``.
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


# Execution elements carry the span id (everything but the Session).
_EXECUTION_LABELS = "LLMCall|ToolCall|AgentCall|CapabilityCall|MASCall|ProcessingCall"

# Dict projected for each result in the ``metrics`` list of a session/span lookup.
_METRIC_MAP = """{
                name: d.name,
                result: r.result,
                value: r.result,
                provider: d.metricProvider,
                metric_id: d.name,
                source: d.metricProvider,
                reasoning: r.reasoning
            }"""

# Sub-graph expansion must not walk through a (shared) ``Metric`` definition:
# it links every result of that metric, so it would pull in unrelated sessions.
_NO_DEFINITION = "none(n IN nodes(path) WHERE n:Metric)"


def _metrics_with_subgraph(anchor: str, var: str, key: str, hops: int) -> str:
    """Query returning the results measuring ``var`` plus, if ``hops`` > 0, its sub-graph."""
    if hops <= 0:
        return f"""
        {anchor}
        OPTIONAL MATCH (r:MetricResult)-[:measures]->({var}), (r)-[:ofMetricType]->(d:Metric)
        RETURN
            {var}.{key} AS {key},
            collect(DISTINCT {_METRIC_MAP}) AS metrics,
            null AS subgraph
        """
    return f"""
        {anchor}
        OPTIONAL MATCH (r:MetricResult)-[:measures]->({var}), (r)-[:ofMetricType]->(d:Metric)
        WITH {var}, collect(DISTINCT {_METRIC_MAP}) AS metrics
        OPTIONAL MATCH path = ({var})-[*1..{hops}]-(related)
        WHERE {_NO_DEFINITION}
        WITH {var}, metrics,
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
            {var}.{key} AS {key},
            metrics,
            {{nodes: nodes, edges: edges}} AS subgraph
        """


def session_metrics_query(
    session_id: str,
    *,
    hops: int = 1,
) -> tuple[str, dict[str, Any]]:
    """Return metrics for a session, with optional sub-graph of *hops* depth.

    When ``hops`` is 0, only the results measuring the session node are
    returned.  Each additional hop expands the traversal through related
    nodes (states, calls, embeddings, results...) and returns them as a
    sub-graph; ``Metric`` definitions are not traversed.
    """
    query = _metrics_with_subgraph(
        "MATCH (session:Session {sessionId: $session_id})",
        "session",
        "sessionId",
        hops,
    )
    return query, {"session_id": session_id}


def span_metrics_query(
    span_id: str,
    *,
    session_id: str | None = None,
    hops: int = 1,
) -> tuple[str, dict[str, Any]]:
    """Return metrics for a span, with optional sub-graph of *hops* depth.

    The span is the execution element (call) with that ``spanId``.  If
    *session_id* is also given the match is stricter (the element must belong
    to that session), but it is not required.
    """
    anchor = f"MATCH (span:{_EXECUTION_LABELS} {{spanId: $span_id}})"
    params: dict[str, Any] = {"span_id": span_id}
    if session_id:
        anchor += "\n        WHERE span.sessionId = $session_id"
        params["session_id"] = session_id
    return _metrics_with_subgraph(anchor, "span", "spanId", hops), params


# ── category / application-level read queries ────────────────────────────────

_ROW_PROJECTION = """
                s.sessionId    AS sessionId,
                d.name         AS metricName,
                r.result       AS metricResult,
                r.result       AS value,
                d.metricProvider AS provider,
                d.name         AS metricId,
                d.metricProvider AS source,
                r.reasoning    AS reasoning,
                r.timestamp    AS timestamp"""


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
        ``MAS {id} <-[:executesSession]- Session <-[:measures]- MetricResult``
    Traversal (with agent filter), additionally the results measuring the
    calls of that agent in the session:
        ``Session <- AgentCall {agentName} -[:hasLLMCall|hasToolCall*0..1]-> t
        <-[:measures]- MetricResult``

    The definition (name, provider) is reached through ``ofMetricType``.
    """
    time_clauses: list[str] = []
    params: dict[str, Any] = {
        "application_id": application_id,
        "metric_names": metric_names,
    }

    if start_time:
        params["start_time"] = _to_iso(start_time)
        time_clauses.append("r.timestamp >= datetime($start_time)")
    if end_time:
        params["end_time"] = _to_iso(end_time)
        time_clauses.append("r.timestamp <= datetime($end_time)")

    where = ""
    if time_clauses:
        where = "AND " + " AND ".join(time_clauses)

    if agent_id:
        params["agent_id"] = agent_id
        # Return both session-measuring results and results measuring the
        # agent's calls (the agent call itself and its LLM/tool calls).
        query = f"""
        MATCH (s:Session)-[:executesSession]->(:MAS {{id: $application_id}})
        WHERE EXISTS {{
            MATCH (a:AgentCall {{sessionId: s.sessionId, agentName: $agent_id}})
        }}
        CALL (s) {{
            MATCH (s)<-[:measures]-(r:MetricResult)-[:ofMetricType]->(d:Metric)
            WHERE d.name IN $metric_names
            {where}
            RETURN {_ROW_PROJECTION}

            UNION

            MATCH (ac:AgentCall {{sessionId: s.sessionId, agentName: $agent_id}})
                  -[:hasLLMCall|hasToolCall*0..1]->(t)
            MATCH (t)<-[:measures]-(r:MetricResult)-[:ofMetricType]->(d:Metric)
            WHERE d.name IN $metric_names
            {where}
            RETURN {_ROW_PROJECTION}
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
        MATCH (s)<-[:measures]-(r:MetricResult)-[:ofMetricType]->(d:Metric)
        WHERE d.name IN $metric_names
        {where}
        RETURN {_ROW_PROJECTION}
        ORDER BY metricName, timestamp
        """
    return query, params


# ── aggregation queries ──────────────────────────────────────────────────────


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
        "d.name = $metric_id",
        "r.timestamp >= datetime($start)",
        "r.result IS NOT NULL",
    ]
    params: dict[str, Any] = {
        "metric_id": metric_id,
        "start": start.isoformat(),
        "bucket": bucket,
    }
    if end is not None:
        where_parts.append("r.timestamp <= datetime($end)")
        params["end"] = end.isoformat()
    if app_name is not None:
        where_parts.append("s.appName = $app_name")
        params["app_name"] = app_name
    if agent_id is not None:
        where_parts.append(
            "EXISTS { MATCH (:AgentCall {sessionId: s.sessionId, agentName: $agent_id}) }"
        )
        params["agent_id"] = agent_id

    where_clause = "\n  AND ".join(where_parts)
    query = f"""
    MATCH (r:MetricResult)-[:measures]->(s:Session), (r)-[:ofMetricType]->(d:Metric)
    WHERE {where_clause}
    WITH datetime.truncate($bucket, r.timestamp) AS bucket,
         toFloat(r.result) AS v
    RETURN toString(bucket) AS bucket,
           avg(v)          AS avg_value,
           min(v)          AS min_value,
           max(v)          AS max_value,
           count(*)        AS n_sessions
    ORDER BY bucket
    """
    return query, params


def get_application_metrics_timeline(
    application_id: str,
    metrics: list[str],
    start_time: str | None = None,
    end_time: str | None = None,
) -> tuple[str, dict[str, Any]]:
    params = {"application_id": application_id, "metrics": metrics}
    query = """
    MATCH (s:Session)-[:executesSession]->(:MAS {id: $application_id})
    MATCH (s)<-[:measures]-(r:MetricResult)-[:ofMetricType]->(d:Metric)
    WHERE d.name IN $metrics
            AND s.startTime IS NOT NULL
            AND r.result IS NOT NULL
    WITH d.name AS metricName, s.startTime AS startTime, r.result AS metricValue
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
    MATCH (:MAS {id: $application_id})<-[:executesSession]-(s:Session)
        <-[:measures]-(r:MetricResult)-[:ofMetricType]->(d:Metric)
    WHERE d.name IN ['ToolErrorRate', 'LLMErrorRate']
    WITH reliabilityStats, 1 - AVG(r.result) AS CompletionRate

    WITH reliabilityStats + [{col1: "CompletionRate", col2: CompletionRate}] AS finalResults
    UNWIND finalResults AS row
    RETURN row.col1 AS metricName, row.col2 AS metricResult
    """

    return query, params
