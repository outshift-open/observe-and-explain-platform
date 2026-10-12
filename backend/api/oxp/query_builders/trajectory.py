#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Cypher query builders for a session's normalized trajectory.

The trajectory is the session's ``LLMCall``/``ToolCall``/``AgentCall`` nodes, each with the
``Transition`` it corresponds to and the ``State`` text going in and out. Each
builder returns a ``(query_str, params_dict)`` tuple for
:py:meth:`~oxp.connectors.base.Connector.execute`.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def trajectory_steps_query(session_id: str) -> tuple[str, dict[str, Any]]:
    """The session's LLM, tool and agent calls in execution order.

    Each row carries the call, its Transition, the raw text of its initial and
    final State, the model, tool or agent it executes, and the agent call that
    owns it.
    """
    query = """
    MATCH (c)-[:correspondsToTransition]->(t:Transition)
    WHERE c.sessionId = $session_id AND (c:LLMCall OR c:ToolCall OR c:AgentCall)
    MATCH (c)-[:hasInitialState]->(i:State)
    MATCH (c)-[:hasFinalState]->(f:State)
    OPTIONAL MATCH (c)-[:executesLLM|executesTool|executesAgent]->(s)
    OPTIONAL MATCH (a:AgentCall)-[:hasLLMCall|hasToolCall]->(c)
    OPTIONAL MATCH (a)-[:executesAgent]->(ag:Agent)
    RETURN t.id AS transition_id,
           c.id AS call_id,
           CASE WHEN c:LLMCall THEN 'llm' WHEN c:ToolCall THEN 'tool' ELSE 'agent' END AS kind,
           coalesce(s.name, c.name) AS name,
           s.description AS description,
           CASE WHEN c:AgentCall THEN s.name ELSE ag.name END AS agent,
           a.id AS parent_id,
           c.success AS success,
           c.startTime AS start_time,
           c.duration AS duration_ms,
           i.content AS input_text,
           f.content AS output_text
    ORDER BY c.startTime
    """
    return query, {"session_id": session_id}


def write_transition_metric_query(
    session_id: str,
    transition_id: str,
    metric_name: str,
    metric_value: float | None,
    provider: str = "API",
    metric_id: str = "",
    source: str = "",
    reasoning: str = "",
) -> tuple[str, dict[str, Any]]:
    """MERGE a metric onto an existing ``Transition`` (nothing if it is missing)."""
    query = """
    MATCH (t:Transition {id: $transition_id, sessionId: $session_id})
    MERGE (t)-[:hasMetric]->(m:Metric {metricName: $metric_name, resourceId: $transition_id})
    SET m.metricResult = $metric_value,
        m.value        = $metric_value,
        m.provider     = $provider,
        m.metricId     = $metric_id,
        m.source       = $source,
        m.reasoning    = $reasoning,
        m.timestamp    = datetime($timestamp)
    RETURN m.metricName AS metricName
    """
    return query, {
        "session_id": session_id,
        "transition_id": transition_id,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "provider": provider,
        "metric_id": metric_id,
        "source": source,
        "reasoning": reasoning,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def trajectory_context_id(transition_id: str) -> str:
    """Id of the ``TrajectoryContext`` node of a transition (one per transition)."""
    return "context:" + hashlib.sha1(transition_id.encode("utf-8")).hexdigest()[:12]


def write_transition_context_query(
    session_id: str, transition_id: str, properties: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """MERGE a ``TrajectoryContext`` node onto an existing ``Transition``.

    ``properties`` are all the node's properties, ``id`` included; they replace
    whatever the node held, so a re-run leaves no stale constituent behind.
    Nothing is written if the transition is missing.
    """
    query = """
    MATCH (t:Transition {id: $transition_id, sessionId: $session_id})
    MERGE (c:TrajectoryContext {id: $context_id})
    SET c = $properties
    MERGE (t)-[:hasContext]->(c)
    RETURN c.id AS id
    """
    return query, {
        "session_id": session_id,
        "transition_id": transition_id,
        "context_id": properties["id"],
        "properties": properties,
    }
