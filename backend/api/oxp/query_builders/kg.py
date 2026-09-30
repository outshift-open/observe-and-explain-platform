#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **KG** (knowledge-graph) feature domain.

This module contains two groups of builders:

1. **Embedding / similarity** (pre-existing) — ``get_embedding_by_session_id``,
   ``neighbors_query`` — used by the similarity-search endpoints.

2. **KGProvider / DataProvider queries** (added during MCE migration) —
   ``list_sessions_query``, ``list_agents_query``, ``list_llm_calls_query``,
   ``resolve_session_id_queries``, ``fetch_session_query``,
   ``fetch_session_timing_query``, ``fetch_conversation_query``,
   ``fetch_call_content_and_names_query``.

   These were previously Cypher strings inlined in ``providers/neo4j_mce.py``.
   Moving them here keeps all Cypher in one place and makes
   ``OXPMetricsProvider`` free of raw query strings.
"""

from __future__ import annotations

from typing import Any

from oxp.interfaces.models import EdgeFacet

# Canonical type for a single executable query unit (cypher string + params).
# Each KGProvider builder that has ontology / workaround variants returns a
# ``tuple[QueryPair, QueryPair]`` — (ontology_query, workaround_query).
QueryPair = tuple[str, dict[str, Any]]


# ── similarity function map ──────────────────────────────────────────────────

_SIMILARITY_FUNCTIONS: dict[str, str] = {
    "cosine": "vector.similarity.cosine",
    "euclidean": "vector.similarity.euclidean",
}


# ── public query builders ────────────────────────────────────────────────────


def get_state_from_sessionId(id: str) -> str:
    return f'''MATCH (s:State {{sessionId: "{id}"}}) RETURN s'''


def get_embedding_by_session_id(session_id: str) -> QueryPair:
    """Return a Cypher query that fetches the embedding vector for a session."""
    query = """
    MATCH (session:Session {sessionId: $session_id})
          -[:hasInitialState]->(state:State)
    MATCH (emb:Embedding)-[:represents]->(state)
    RETURN emb.embeddingVector AS embedding
    LIMIT 1
    """
    return query, {"session_id": session_id}


def neighbors_query(
    *,
    embedding: list[float],
    max_distance: float = 1.0,
    max_neighbors: int = 10,
    metric_names: list[str] | None = None,
    distance_metric: str = "cosine",
) -> QueryPair:
    """Build a Cypher query to find sessions whose embedding is close to *embedding*.

    Parameters
    ----------
    embedding:
        The reference embedding vector.
    max_distance:
        Maximum distance threshold (1 − similarity) for a session to be
        included.
    max_neighbors:
        Maximum number of neighbor sessions to return.
    metric_names:
        If provided, only include metrics whose ``metricName`` is in this
        list.  *None* or an empty list means "return all metrics".
    distance_metric:
        Which vector similarity function to use (``cosine`` | ``euclidean``).
    """
    similarity_fn = _SIMILARITY_FUNCTIONS.get(
        distance_metric, "vector.similarity.cosine"
    )

    query = f"""
    MATCH (emb:Embedding)
    WITH emb, {similarity_fn}(emb.embeddingVector, $embedding) AS similarity
    WITH emb, (1 - similarity) AS distance
    WHERE distance <= $max_distance
    MATCH (emb)-[:represents]->(state:State)<-[:hasInitialState]-(session:Session)
    OPTIONAL MATCH (session)-[:hasMetric]->(metric:Metric)
    WHERE $metric_names IS NULL
        OR size($metric_names) = 0
        OR metric.metricName IN $metric_names
    RETURN
        session.sessionId AS sessionId,
        distance,
        emb.embeddingVector AS embedding,
        collect(DISTINCT metric {{.*}}) AS metrics
    ORDER BY distance ASC
    LIMIT $max_neighbors
    """

    return query, {
        "embedding": embedding,
        "max_distance": max_distance,
        "max_neighbors": max_neighbors,
        "metric_names": metric_names,
    }


# ── KGProvider query builders ────────────────────────────────────────────────


def list_sessions_query(limit: int = 100) -> QueryPair:
    """List available sessions ordered by most recent first."""
    query = """
    MATCH (s:Session)
    RETURN s.sessionId AS session_id, s.name AS name, s.startTime AS timestamp
    ORDER BY s.startTime DESC
    LIMIT $limit
    """
    return query, {"limit": limit}


def list_sessions_in_interval_query(
    start_time: str | None,
    end_time: str | None,
    limit: int | None = None,
) -> QueryPair:
    """List sessions whose timestamps fall within an optional time interval."""
    query = """
    MATCH (s:Session)
    WHERE ($start_time IS NULL OR s.startTime >= $start_time)
      AND ($end_time IS NULL OR s.startTime <= $end_time)
    RETURN s.sessionId AS session_id, s.startTime AS timestamp
    ORDER BY s.startTime ASC
    """
    if limit is not None:
        query += "\nLIMIT $limit"
    return query, {
        "start_time": start_time,
        "end_time": end_time,
        "limit": limit,
    }


def fetch_session_node_query(session_id: str) -> QueryPair:
    """Fetch the Session node for a single session identifier."""
    query = """
    MATCH (s:Session {sessionId: $session_id})
    RETURN s
    LIMIT 1
    """
    return query, {"session_id": session_id}


def fetch_agent_call_sequence_query(session_id: str) -> QueryPair:
    """Return the ordered AgentCall sequence for a session."""
    query = """
    MATCH (:Session {sessionId: $session_id})-[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)
    RETURN ac AS agent_call
    ORDER BY ac.startTime
    """
    return query, {"session_id": session_id}


def fetch_traversed_nodes_query(
    session_id: str,
    entity_type: str,
    edges: list[EdgeFacet],
    *,
    order_by: list[str] | None = None,
) -> QueryPair:
    """Build a generic traversal query from the session anchor to entity_type,
    following the declared EdgeFacet chain."""
    target_label = _strip_namespace(entity_type)
    params: dict[str, Any] = {"session_id": session_id}

    if target_label == "Session":
        return fetch_session_node_query(session_id)

    edge_chain = _resolve_edge_chain(edges, target_label)

    if not edge_chain:
        raise ValueError(f"No edges provided for traversed entity {entity_type!r}")

    session_alias = "s"
    clauses = [f"MATCH ({session_alias}:Session {{sessionId: $session_id}})"]
    current_alias = session_alias

    for index, edge in enumerate(edge_chain):
        relation = edge.relation_type
        hops = ""
        if edge.min_hops != 1 or edge.max_hops != 1:
            max_hops = "" if edge.max_hops < 0 else str(edge.max_hops)
            hops = f"*{edge.min_hops}..{max_hops}"

        source_label = (
            _strip_namespace(edge.source_entity) if edge.source_entity else None
        )
        target_label_for_edge = (
            _strip_namespace(edge.target_entity) if edge.target_entity else None
        )

        if (
            source_label
            and current_alias == session_alias
            and source_label != "Session"
        ):
            raise ValueError(
                f"Edge chain must start from Session, got source_entity={edge.source_entity!r}"
            )

        target_alias = "n" if index == len(edge_chain) - 1 else f"v{index}"
        target_label_clause = (
            f":{target_label_for_edge}" if target_label_for_edge else ""
        )

        if edge.direction == "in":
            pattern = f"({target_alias}{target_label_clause})-[:{relation}{hops}]->({current_alias})"
        else:
            pattern = f"({current_alias})-[:{relation}{hops}]->({target_alias}{target_label_clause})"

        clauses.append(f"MATCH {pattern}")
        current_alias = target_alias

    if current_alias != "n":
        clauses.append(f"WITH {current_alias} AS n")

    order_clause = _render_node_order_clause(order_by)
    query = "\n".join(clauses + [f"RETURN n AS node{order_clause}"])

    return query, params


def _resolve_edge_chain(edges: list[EdgeFacet], target_label: str) -> list[EdgeFacet]:
    """Resolve the minimal declared edge chain from Session to the target entity.

    Retrieval requests may aggregate edges contributed by several metrics. When that
    happens, the target node should only use the sub-chain that actually reaches its
    entity type rather than blindly traversing every declared edge in order.
    """
    if not edges:
        return []

    indexed_edges: list[tuple[int, EdgeFacet, str, str]] = []
    for index, edge in enumerate(edges):
        source_label = _strip_namespace(edge.source_entity)
        next_label = _strip_namespace(edge.target_entity)
        if not source_label or not next_label:
            return edges
        indexed_edges.append((index, edge, source_label, next_label))

    queue: list[tuple[str, list[EdgeFacet]]] = [("Session", [])]
    seen = {"Session"}

    while queue:
        current_label, chain = queue.pop(0)
        for _, edge, source_label, next_label in indexed_edges:
            if source_label != current_label:
                continue

            next_chain = [*chain, edge]
            if next_label == target_label:
                return next_chain

            if next_label in seen:
                continue
            seen.add(next_label)
            queue.append((next_label, next_chain))

    return edges


def _strip_namespace(entity_type: str | None) -> str:
    if not entity_type:
        return ""
    return entity_type.split(":")[-1]


def _render_node_order_clause(order_by: list[str] | None) -> str:
    if not order_by:
        return ""

    rendered_fields: list[str] = []
    for field in order_by:
        descending = field.startswith("-")
        field_name = field.lstrip("-")
        rendered_fields.append(f"n.{field_name} {'DESC' if descending else 'ASC'}")
    return "\nORDER BY " + ", ".join(rendered_fields)


def list_agents_query(session_id: str) -> QueryPair:
    """Return AgentCall nodes for a session, with their Agent's real name."""
    query = """
    MATCH (s:Session {sessionId: $sid})-[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)
    OPTIONAL MATCH (ac)-[:executesAgent]->(a:Agent)
    RETURN ac.id AS agent_call_id, a.name AS name
    ORDER BY ac.startTime
    """
    return query, {"sid": session_id}


def list_llm_calls_query(session_id: str) -> QueryPair:
    """Return LLMCall nodes for a session, with their LLM's real name."""
    query = """
    MATCH (s:Session {sessionId: $sid})-[:hasMASCall]->(:MASCall)-[:hasAgentCall]->
          (:AgentCall)-[:hasLLMCall]->(lc:LLMCall)
    OPTIONAL MATCH (lc)-[:executesLLM]->(llm:LLM)
    RETURN lc.id AS id, llm.name AS model, lc.startTime AS start
    ORDER BY start
    """
    return query, {"sid": session_id}


def resolve_session_id_queries(resource_id: str) -> list[QueryPair]:
    """Return a list of Cypher queries to try in order to resolve any resource ID
    to its parent session ID. Each query returns ``sid`` when found.

    1. Direct Session node match.
    2. Any node whose ``id``/``sessionId`` matches -- covers every
       ExecutionElement, which all carry ``sessionId`` directly.
    """
    return [
        (
            "MATCH (s:Session {sessionId: $rid}) RETURN s.sessionId AS sid LIMIT 1",
            {"rid": resource_id},
        ),
        (
            """
            MATCH (n)
            WHERE (n.id = $rid OR n.sessionId = $rid) AND n.sessionId IS NOT NULL
            RETURN n.sessionId AS sid LIMIT 1
            """,
            {"rid": resource_id},
        ),
    ]


def fetch_session_query(session_id: str) -> QueryPair:
    """Fetch full session data: the Session node plus its AgentCall/LLMCall/
    ToolCall/ProcessingCall descendants."""
    query = """
    MATCH (s:Session {sessionId: $session_id})
    OPTIONAL MATCH (s)-[:hasMASCall]->(:MASCall)-[:hasAgentCall]->(ac:AgentCall)
    OPTIONAL MATCH (ac)-[:hasLLMCall]->(lc:LLMCall)
    OPTIONAL MATCH (ac)-[:hasToolCall]->(tc:ToolCall)
    OPTIONAL MATCH (ac)-[:hasProcessingCall]->(pc:ProcessingCall)
    RETURN s,
           collect(DISTINCT ac) as agent_calls,
           collect(DISTINCT lc) as llm_calls,
           collect(DISTINCT tc) as tool_calls,
           collect(DISTINCT pc) as processing_calls
    """
    return query, {"session_id": session_id}


def fetch_session_timing_query(session_id: str) -> QueryPair:
    """Fetch Session timing directly (``startTime``/``duration`` are always
    present on every ExecutionElement)."""
    query = """
    MATCH (s:Session {sessionId: $session_id})
    RETURN s.startTime AS startTime, s.duration AS duration
    LIMIT 1
    """
    return query, {"session_id": session_id}


def fetch_conversation_query(session_id: str) -> QueryPair:
    """Fetch the session's own conversation: its Session node's initial/final
    State content -- what `execution_hierarchy_session_state_query` (ui.py)
    already does, reused here as the source of "the whole session's query
    and response"."""
    query = """
    MATCH (s:Session {sessionId: $session_id})
    OPTIONAL MATCH (s)-[:hasInitialState]->(initial:State)
    OPTIONAL MATCH (s)-[:hasFinalState]->(final:State)
    RETURN initial.content AS input, final.content AS output
    """
    return query, {"session_id": session_id}


def fetch_call_content_and_names_query(call_ids: list[str]) -> QueryPair:
    """Batch-fetch, for a list of call-node ids of any ExecutionElement type,
    their own initial/final State content plus their structural node's name
    (and provider, for LLM) -- the two things no property lookup on the call
    node itself can ever supply directly, no matter its type.

    One combined round trip for a whole session's worth of calls rather than
    one query per call: the alternation in the second OPTIONAL MATCH
    resolves to whichever specific edge applies to that call's type (a call
    only ever has one of executesAgent/executesTool/executesLLM/
    executesProcessing).
    """
    query = """
    UNWIND $call_ids AS call_id
    MATCH (call {id: call_id})
    OPTIONAL MATCH (call)-[:executesAgent|executesTool|executesLLM|executesProcessing]->(structural)
    OPTIONAL MATCH (call)-[:hasInitialState]->(initial:State)
    OPTIONAL MATCH (call)-[:hasFinalState]->(final:State)
    RETURN call.id AS id,
           structural.name AS name,
           structural.provider AS provider,
           initial.content AS inputContent,
           final.content AS outputContent
    """
    return query, {"call_ids": call_ids}
