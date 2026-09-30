#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **Concepts** feature domain.

Provides Cypher query builders for retrieving neurosymbolic concepts
(symbols) from the knowledge graph, scoped by application and optionally
by session + span.
"""

from __future__ import annotations

from typing import Any


def app_concepts_query(
    app_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return all concepts / symbols for a given application.

    The graph model is expected to have ``(:Application)-[:hasConcept]->(:Concept)``
    edges.  Each ``Concept`` node carries ``name``, ``type`` and arbitrary
    extra properties.
    """
    query = """
    MATCH (app:Application {applicationId: $app_id})-[:hasConcept]->(c:Concept)
    RETURN
        c.name       AS name,
        c.type       AS type,
        properties(c) AS properties
    ORDER BY c.name
    """
    return query, {"app_id": app_id}


def span_concepts_query(
    app_id: str,
    session_id: str,
    span_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return concepts / symbols attached to a specific span.

    Traversal: ``Application -> Session -> Span -> Concept``.
    """
    query = """
    MATCH (app:Application {applicationId: $app_id})
          -[:hasSession]->(session:Session {sessionId: $session_id})
          -[:hasSpan]->(span:Span {spanId: $span_id})
          -[:hasConcept]->(c:Concept)
    RETURN
        c.name        AS name,
        c.type        AS type,
        properties(c) AS properties
    ORDER BY c.name
    """
    return query, {
        "app_id": app_id,
        "session_id": session_id,
        "span_id": span_id,
    }


# ── write queries ─────────────────────────────────────────────────────────────


def write_app_concept_query(
    app_id: str,
    name: str,
    concept_type: str = "",
    properties: dict | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a MERGE query to attach a concept to an application node."""
    query = """
    MERGE (app:Application {applicationId: $app_id})
    MERGE (app)-[:hasConcept]->(c:Concept {name: $name})
    SET c.type = $concept_type
    SET c += $properties
    RETURN c.name AS name
    """
    return query, {
        "app_id": app_id,
        "name": name,
        "concept_type": concept_type,
        "properties": properties or {},
    }


def write_span_concept_query(
    app_id: str,
    session_id: str,
    span_id: str,
    name: str,
    concept_type: str = "",
    properties: dict | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a MERGE query to attach a concept to a span node."""
    query = """
    MERGE (app:Application {applicationId: $app_id})
    MERGE (app)-[:hasSession]->(session:Session {sessionId: $session_id})
    MERGE (session)-[:hasSpan]->(span:Span {spanId: $span_id})
    MERGE (span)-[:hasConcept]->(c:Concept {name: $name})
    SET c.type = $concept_type
    SET c += $properties
    RETURN c.name AS name
    """
    return query, {
        "app_id": app_id,
        "session_id": session_id,
        "span_id": span_id,
        "name": name,
        "concept_type": concept_type,
        "properties": properties or {},
    }
