#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Cypher query builders for the DAL (Data Access Layer).

Each builder returns a ``(query_str, params_dict)`` tuple that can be
passed directly to :py:meth:`~oxp.connectors.base.Connector.execute`.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

_STATE_NODE_LABEL = "State"

_HIERARCHICAL_GROUPING_LOCK_QUERY = """
OPTIONAL MATCH (lock:SystemLock {id: "hierarchical_grouping"})
WITH lock, timestamp() AS now
RETURN lock IS NOT NULL
   AND coalesce(lock.locked, false)
   AND coalesce(lock.expiresAt, 0) >= now AS is_locked
"""


def build_state_content_query(
    filters_eq: Dict[str, str],
    filters_neq: Dict[str, str],
) -> tuple[str, Dict[str, object]]:
    """Build a Cypher query that matches ``State`` nodes with the given filters.

    Mirrors the logic of ``Neo4jConnector.get_nodes`` in *oxp-lib*.

    Returns
    -------
    tuple[str, dict]
        The parameterised Cypher query string and its parameter mapping.
    """
    query = f"MATCH (n:{_STATE_NODE_LABEL})"
    where_clauses: list[str] = []
    params: Dict[str, object] = {}

    for i, (key, value) in enumerate(filters_eq.items()):
        param_key = f"eq_{i}"
        where_clauses.append(f"n.{key} = ${param_key}")
        params[param_key] = value

    for i, (key, value) in enumerate(filters_neq.items()):
        param_key = f"neq_{i}"
        where_clauses.append(f"n.{key} <> ${param_key}")
        params[param_key] = value

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " RETURN n"
    return query, params


def build_session_io_query(edge: str) -> tuple[str, Dict[str, object]]:
    """Build a Cypher query that traverses Session -[edge]-> State.

    Mirrors the path traversal performed by ``Neo4jDBHandler.get_session_io``
    in *oxp-lib* via ``get_nodes_by_path``.

    Returns
    -------
    tuple[str, dict]
        The parameterised Cypher query string (with ``$session_id``) and an
        empty params dict (caller fills in ``session_id``).
    """
    query = (
        f"MATCH (s:Session)-[:{edge}]->(n:State)"
        " WHERE s.sessionId = $session_id"
        " RETURN n"
    )
    return query, {"session_id": None}


def build_session_group_query(
    session_id: str,
    embedding_model: str,
    max_distance: float,
) -> tuple[str, Dict[str, object]]:
    """Build a Cypher query that finds the closest semantic group for a session.

    Mirrors the query used by ``Neo4jDBHandler.get_session_group`` in
    *oxp-lib*: performs a cosine-similarity search against medioid
    embeddings of leaf ``SemanticGroup`` nodes and returns the nearest one
    within *max_distance*.

    Returns
    -------
    tuple[str, dict]
        The parameterised Cypher query string and its parameter mapping.
    """
    query = """
    MATCH (mas:MAS)<-[:executesSession]-(:Session {sessionId: $session_id})-[:hasInitialState]->(:State)<-[:represents]-(te:Embedding {embeddingModel: $embedding_model})
    WITH te.embeddingVector AS target_embedding

    MATCH (sg:SemanticGroup)-[:hasMedioidSession]->(medioid_session:Session)-[:executesSession]->(mas)
    WHERE NOT EXISTS { MATCH (sg)-[:containsSession]->(:SemanticGroup) }
    MATCH (medioid_session)-[:hasInitialState]->(:State)<-[:represents]-(medioid_embedding:Embedding {embeddingModel: $embedding_model})

    WITH sg, 1 - vector.similarity.cosine(medioid_embedding.embeddingVector, target_embedding) AS distance

    WHERE distance <= $max_distance
    ORDER BY distance ASC
    LIMIT 1

    RETURN sg.id AS group_id, sg.nodeHash AS node_hash
    """
    params: Dict[str, object] = {
        "session_id": session_id,
        "embedding_model": embedding_model,
        "max_distance": max_distance,
    }
    return query, params


def build_hierarchical_grouping_lock_query() -> tuple[str, Dict[str, object]]:
    """Return the Cypher query that checks the hierarchical-grouping lock.

    Mirrors the query used by ``Neo4jDBHandler.is_hierarchical_grouping_locked``
    in *oxp-lib*.

    Returns
    -------
    tuple[str, dict]
        The Cypher query string and an empty parameter mapping (no params
        required).
    """
    return _HIERARCHICAL_GROUPING_LOCK_QUERY, {}


def build_acquire_hierarchical_grouping_lock_query(
    owner: str,
    ttl_seconds: int,
) -> tuple[str, Dict[str, object]]:
    """Build a Cypher query that atomically acquires the hierarchical-grouping lock.

    Mirrors the query used by ``Neo4jDBHandler.acquire_hierarchical_grouping_lock``
    in *oxp-lib*: uses ``MERGE`` to create the lock node if absent, then
    conditionally claims it when it is either unlocked or expired.

    Returns
    -------
    tuple[str, dict]
        The parameterised Cypher query string and its parameter mapping.
    """
    query = """
    MERGE (lock:SystemLock {id: "hierarchical_grouping"})
    ON CREATE SET lock.locked = false, lock.owner = "", lock.expiresAt = 0
    WITH lock, timestamp() AS now
    WHERE coalesce(lock.locked, false) = false
       OR coalesce(lock.expiresAt, 0) < now
       OR lock.owner = $owner
    SET lock.locked = true,
        lock.owner = $owner,
        lock.expiresAt = now + $ttl_ms
    RETURN true AS acquired
    """
    params: Dict[str, object] = {
        "owner": owner,
        "ttl_ms": int(ttl_seconds * 1000),
    }
    return query, params


def build_attach_session_fetch_query(
    group_id: str,
    node_hash: str,
) -> tuple[str, Dict[str, object]]:
    """Build the first query used by ``attach_session_to_group``.

    Retrieves the current direct and transitive session IDs of a
    ``SemanticGroup`` so the caller can compute the new hash before writing.

    Returns
    -------
    tuple[str, dict]
        The parameterised Cypher query string and its parameter mapping.
    """
    query = """
    MATCH (sg:SemanticGroup {id: $group_id})
    WHERE $node_hash = "" OR sg.nodeHash = $node_hash
    WITH sg, coalesce(sg.sessionIds, []) AS direct_session_ids

    OPTIONAL MATCH (sg)-[:containsSession*0..]->(child:Session)
    WITH direct_session_ids, child.sessionId AS sid
    ORDER BY sid
    WITH direct_session_ids, collect(DISTINCT sid) AS raw_all_session_ids

    RETURN
    [x IN raw_all_session_ids WHERE x IS NOT NULL] AS all_session_ids,
    direct_session_ids
    """
    params: Dict[str, object] = {"group_id": group_id, "node_hash": node_hash}
    return query, params


def build_attach_session_update_query(
    session_id: str,
    group_id: str,
    node_hash: str,
    new_session_ids: list,
    new_group_hash: str,
) -> tuple[str, Dict[str, object]]:
    """Build the second (write) query used by ``attach_session_to_group``.

    Conditionally creates the ``containsSession`` relationship and
    updates the group's session list and hash, guarded by *node_hash* to
    detect concurrent modifications.

    Returns
    -------
    tuple[str, dict]
        The parameterised Cypher query string and its parameter mapping.
    """
    query = """
    MATCH (sg:SemanticGroup {id: $group_id})
    WHERE $node_hash = "" OR sg.nodeHash = $node_hash
    MATCH (s:Session {sessionId: $session_id})
    MERGE (sg)-[:containsSession]->(s)
    SET sg.sessionIds = $new_session_ids,
        sg.nodeHash = $new_group_hash
    RETURN sg.id AS group_id
    """
    params: Dict[str, object] = {
        "session_id": session_id,
        "group_id": group_id,
        "node_hash": node_hash,
        "new_session_ids": new_session_ids,
        "new_group_hash": new_group_hash,
    }
    return query, params


def build_release_hierarchical_grouping_lock_query(
    owner: str,
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that releases the hierarchical-grouping lock.

    Mirrors ``Neo4jDBHandler.release_hierarchical_grouping_lock`` in *oxp-lib*.
    """
    query = """
    MATCH (lock:SystemLock {id: "hierarchical_grouping"})
    WHERE lock.owner = $owner
    SET lock.locked = false,
        lock.owner = "",
        lock.expiresAt = 0
    RETURN true AS released
    """
    return query, {"owner": owner}


def build_all_session_input_embeddings_query(
    application_id: str,
    embedding_model: str,
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that retrieves all input embeddings for an application.

    Mirrors ``Neo4jDBHandler.get_all_session_input_embeddings`` in *oxp-lib*.
    """
    query = """
    MATCH (in_emb {embeddingModel: $embedding_model})-[:represents]->(in_state:State)<-[:hasInitialState]-(s:Session)-[:executesSession]->(m:MAS {id: $application_id})
    RETURN
        s.sessionId as session_id,
        in_state.content as input_query,
        in_emb.embeddingVector as input_embedding
    """
    return query, {"application_id": application_id, "embedding_model": embedding_model}


def build_semantic_group_hierarchy_query(
    embedding_model: str,
    application_id: str,
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that returns the semantic group hierarchy for an application.

    Mirrors ``Neo4jDBHandler.get_semantic_group_hierarchy`` in *oxp-lib*.
    """
    query = """
    MATCH (:MAS {id: $application_id})-[:containsSemanticGroup]->(sg:SemanticGroup {embeddingModel: $embedding_model})
    RETURN sg
    ORDER BY sg.nSessions DESC
    """
    return query, {"embedding_model": embedding_model, "application_id": application_id}


def build_update_semantic_group_names_query(
    groups: list,
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher UNWIND query that updates SemanticGroup name/summary fields.

    Each entry in *groups* must have ``"id"``, ``"groupName"``, and ``"groupSummary"``.

    Mirrors ``Neo4jDBHandler.update_semantic_group_names_and_summaries`` in *oxp-lib*.
    """
    query = """
    UNWIND $groups AS group
    MATCH (n:SemanticGroup {id: group.id})
    SET n.groupName = group.groupName,
        n.groupSummary = group.groupSummary
    """
    return query, {"groups": groups}


def build_semantic_groups_needing_analysis_query(
    embedding_model: str,
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher query for leaf groups missing at least one analysis report.

    Mirrors ``Neo4jDBHandler.get_semantic_groups_needing_analysis`` in *oxp-lib*.
    """
    query = """
    MATCH (sg:SemanticGroup {embeddingModel: $embedding_model})
    WHERE sg.nodeHash IS NOT NULL
        AND NOT EXISTS { MATCH (sg)-[:containsSession]->(:SemanticGroup) }
       OPTIONAL MATCH (sg)-[:hasAnomalyReport]->(ar:AnomalyReport)
       OPTIONAL MATCH (sg)-[:hasConsistencyReport]->(cr:ConsistencyReport)
       OPTIONAL MATCH (sg)-[:hasNormalBehaviourReport]->(nr:NormalBehaviourReport)
    WITH sg,
           count(DISTINCT ar) > 0 AS has_anomaly,
           count(DISTINCT cr) > 0 AS has_consistency,
           count(DISTINCT nr) > 0 AS has_normal_behaviour
    WHERE NOT (has_anomaly AND has_consistency AND has_normal_behaviour)
    RETURN sg.id AS group_id, sg.nodeHash AS group_hash
    """
    return query, {"embedding_model": embedding_model}


# Valid report types and their corresponding edge names (mirrors Nodes/Edges enums).
_REPORT_TYPE_TO_EDGE: Dict[str, str] = {
    "ConsistencyReport": "hasConsistencyReport",
    "AnomalyReport": "hasAnomalyReport",
    "NormalBehaviourReport": "hasNormalBehaviourReport",
}
_VALID_REPORT_TYPES = frozenset(_REPORT_TYPE_TO_EDGE)


def build_analysis_pre_check_query(
    report_type: str,
    with_session_id: bool,
) -> tuple[str, Dict[str, object]]:
    """Build the dynamic Cypher query used by ``analysis_pre_check``.

    *report_type* must be one of ``ConsistencyReport``, ``AnomalyReport``, or
    ``NormalBehaviourReport``.  *with_session_id* controls whether an extra
    ``Session`` membership check is appended.

    Mirrors ``Neo4jDBHandler.analysis_pre_check`` in *oxp-lib*.
    """
    if report_type not in _VALID_REPORT_TYPES:
        raise ValueError(
            f"Unknown report type: {report_type!r}. "
            f"Must be one of {', '.join(sorted(_VALID_REPORT_TYPES))}."
        )
    report_edge = _REPORT_TYPE_TO_EDGE[report_type]
    query = f"""
    OPTIONAL MATCH (sg:SemanticGroup {{id: $group_id}})
    WITH sg, sg IS NOT NULL AND ($group_hash = "" OR sg.nodeHash = $group_hash) AS hash_matches
    OPTIONAL MATCH (sg)-[:{report_edge}]->(report:{report_type})
    WHERE $group_hash = "" OR report.nodeHash = $group_hash
    WITH sg, hash_matches, count(report) > 0 AS report_exists
    """
    if with_session_id:
        query += """
    OPTIONAL MATCH (sg)-[:containsSession]->(s:Session {sessionId: $session_id})
    WITH hash_matches, report_exists, count(s) AS session_count
    RETURN hash_matches AND NOT report_exists AND session_count > 0 AS can_analyze
    """
    else:
        query += "RETURN hash_matches AND NOT report_exists AS can_analyze"
    return query, {}


def build_all_metrics_for_session_query() -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that fetches all metric name/result pairs for a session.

    The caller supplies ``session_id`` in the params dict.

    Mirrors ``Neo4jConnector.get_all_metrics_for_a_session`` in *oxp-lib*.
    """
    query = """
    MATCH (s:Session {sessionId: $session_id})-[:hasMetric]->(m:Metric)
    RETURN m.metricName AS metricName, m.metricResult AS metricResult
    """
    return query, {"session_id": None}


def build_mas_name_query() -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that looks up the MAS name for a session.

    The caller supplies ``session_id`` in the params dict.

    Mirrors ``Neo4jConnector.get_mas_name`` in *oxp-lib*.
    """
    query = """
    MATCH (s:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)
    RETURN mas.name AS masName
    """
    return query, {"session_id": None}


def build_impact_assessment_training_data_query(
    session_ids: list[str], embedding_model_name: str
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that retrieves raw impact-assessment training data.

    Mirrors ``Neo4jConnector.retrieve_raw_impact_assessment_data`` in *oxp-lib*.
    """
    query = """
    MATCH (s:Session)
    WHERE s.sessionId IN $included_ids

    MATCH (s)-[:hasInitialState]->(start:State)

    MATCH (t:Transition {sessionId: s.sessionId})-[:representsExecution]->(ac:AgentCall)
    OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
    MATCH (input_embedding:Embedding {embeddingModel: $emb_model})-[:represents]->(input:State)-[:inputTo]->(t)
    MATCH (t)-[:leadsTo]->(output:State)<-[:represents]-(output_embedding:Embedding {embeddingModel: $emb_model})

    WITH s, start, t, ac, agentNode, input, output, input_embedding, output_embedding
    ORDER BY ac.startTime ASC

    WITH s, start, collect({
        agent: agentNode.name,
        input: input.content,
        input_embedding: input_embedding.embeddingVector,
        output: output.content,
        output_embedding: output_embedding.embeddingVector
    }) as Triples

    RETURN DISTINCT
        s.sessionId AS SessionID,
        Triples
    """
    return query, {"included_ids": session_ids, "emb_model": embedding_model_name}


def build_all_mas_metric_pairs_query() -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that returns all distinct MAS/metric-name pairs.

    Mirrors ``Neo4jConnector.get_all_mas_metric_pairs`` in *oxp-lib*.
    """
    query = """
    MATCH (mas:MAS)<-[:executesSession]-(s:Session)-[:hasMetric]->(m:Metric)
    RETURN DISTINCT mas.id AS masId, m.metricName AS metricName
    """
    return query, {}


def build_all_application_ids_query() -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that returns all distinct non-null MAS names."""
    query = """
    MATCH (mas:MAS)
    WHERE mas.id IS NOT NULL
    RETURN DISTINCT mas.id AS masId
    """
    return query, {}


def build_all_mas_ids_query() -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that returns all distinct non-null MAS ids."""
    query = """
    MATCH (mas:MAS)
    WHERE mas.id IS NOT NULL
    RETURN DISTINCT mas.id AS masId
    """
    return query, {}


def build_remove_semantic_groups_query(ids: List[str]) -> tuple[str, Dict[str, object]]:
    """Build the query that removes semantic groups and attached analysis nodes."""
    query = """
    MATCH (n:SemanticGroup) WHERE n.id IN $ids
    OPTIONAL MATCH (n)-[]-(r)
    WHERE r:NormalBehaviourReport OR r:ConsistencyReport
       OR r:AnomalyReport OR r:Metric
    DETACH DELETE r, n
    """
    return query, {"ids": ids}


def build_cleanup_semantic_groups_query(
    ids: List[str],
) -> tuple[str, Dict[str, object]]:
    """Build the query that clears rels/reports for upserted semantic groups."""
    query = """
    MATCH (n:SemanticGroup) WHERE n.id IN $ids
    OPTIONAL MATCH (n)-[rel:containsSession]->()
    OPTIONAL MATCH (n)-[medioid_rel:hasMedioidSession]->()
    OPTIONAL MATCH (n)-[]-(r)
    WHERE r:NormalBehaviourReport OR r:ConsistencyReport
       OR r:AnomalyReport OR r:Metric
    DELETE rel, medioid_rel
    DETACH DELETE r
    """
    return query, {"ids": ids}


def build_delete_stale_child_edges_query(
    child_ids: List[str],
) -> tuple[str, Dict[str, object]]:
    """Build the query that deletes stale parent->child semantic-group edges."""
    query = """
    UNWIND $child_ids AS child_id
    MATCH (:SemanticGroup)-[rel:containsSession]->(child:SemanticGroup {id: child_id})
    DELETE rel
    """
    return query, {"child_ids": child_ids}


def build_ingest_node_query(
    label: str,
    properties: Dict[str, Any],
) -> tuple[str, Dict[str, object]]:
    """Build the query that upserts/creates a node for DAL ingest operations."""
    if "id" in properties:
        query = f"MERGE (n:{label} {{id: $id}}) SET n += $properties"
        params: Dict[str, object] = {"id": properties["id"], "properties": properties}
    else:
        query = f"CREATE (n:{label}) SET n = $properties"
        params = {"properties": properties}
    return query, params


def build_create_rel_query(
    from_label: str,
    from_id_labels: List[str],
    from_id_values: List[Any],
    to_label: str,
    to_id_labels: List[str],
    to_id_values: List[Any],
    relationship: str,
) -> tuple[str, Dict[str, object]]:
    """Build the query that creates a directed relationship between two nodes."""
    query = ""
    params: Dict[str, object] = {}
    for i, (lbl, val) in enumerate(zip(from_id_labels, from_id_values)):
        query += f"MATCH (a:{from_label} {{{lbl}: $from_id_{i}}})\n"
        params[f"from_id_{i}"] = val
    for i, (lbl, val) in enumerate(zip(to_id_labels, to_id_values)):
        query += f"MATCH (b:{to_label} {{{lbl}: $to_id_{i}}})\n"
        params[f"to_id_{i}"] = val
    query += f"MERGE (a)-[:{relationship}]->(b)"
    return query, params


def build_cleanup_outdated_insights_query(
    target_label: str,
    target_id_field: str,
    target_node_id: str,
    template_id: str,
    current_ids: List[str],
) -> tuple[str, Dict[str, object]]:
    """Build the query that detaches and prunes outdated insights."""
    query = (
        f"MATCH (target:{target_label} {{{target_id_field}: $target_node_id}})"
        f"-[rel:hasInsight]->(old:Insight {{templateId: $template_id}})\n"
        "WHERE NOT old.id IN $current_ids\n"
        "DELETE rel\n"
        "WITH old\n"
        "WHERE NOT ()-[:hasInsight]->(old)\n"
        "DETACH DELETE old"
    )
    params: Dict[str, object] = {
        "target_node_id": target_node_id,
        "template_id": template_id,
        "current_ids": current_ids,
    }
    return query, params


def build_analysis_data_for_semantic_group_query(
    group_id: str,
    group_hash: str,
    embedding_model: str,
    skip: int = 0,
    limit: int = 0,
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher query that retrieves all session data for a semantic group.

    Mirrors ``Neo4jDBHandler.get_analysis_data_for_semantic_group`` in *oxp-lib*.
    """
    query = """
    MATCH (sg:SemanticGroup {id: $group_id})
    WHERE ($group_hash = "" OR sg.nodeHash = $group_hash)
      AND NOT EXISTS { MATCH (sg)-[:containsSession]->(:SemanticGroup) }
    WITH coalesce(sg.sessionIds, []) AS session_ids
    WITH CASE
        WHEN $limit > 0 THEN session_ids[$skip..($skip + $limit)]
        ELSE session_ids
    END AS paged_session_ids
    UNWIND paged_session_ids AS session_id
    MATCH (session:Session {sessionId: session_id})

    CALL (session) {
        OPTIONAL MATCH (session)-[:hasMetric]->(metric:Metric)
        RETURN [item IN collect(DISTINCT metric {.*}) WHERE item IS NOT NULL] AS metrics
    }

    CALL (session) {
        OPTIONAL MATCH (session)-[:hasInitialState]->(input_state:State)
        OPTIONAL MATCH (input_embedding:Embedding {embeddingModel: $embedding_model})-[:represents]->(input_state)
        RETURN
            head(collect(DISTINCT input_state.content)) AS input_content,
            coalesce(head(collect(DISTINCT input_embedding.embeddingVector)), []) AS input_embedding
    }

    CALL (session) {
        OPTIONAL MATCH (session)-[:hasFinalState]->(output_state:State)
        OPTIONAL MATCH (output_embedding:Embedding {embeddingModel: $embedding_model})-[:represents]->(output_state)
        RETURN
            head(collect(DISTINCT output_state.content)) AS output_content,
            coalesce(head(collect(DISTINCT output_embedding.embeddingVector)), []) AS output_embedding
    }

    CALL (session) {
        OPTIONAL MATCH (ac:AgentCall)
        WHERE ac.sessionId = session.sessionId
        OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
        OPTIONAL MATCH (t1:Transition)-[:representsExecution]->(ac)
        WHERE t1.sessionId = session.sessionId
        OPTIONAL MATCH (t1)-[:leadsTo]->(:State)-[:inputTo]->(t2:Transition)-[:representsExecution]->(ac_next:AgentCall)
        WHERE t2.sessionId = session.sessionId
        RETURN
            [node IN collect(DISTINCT CASE
                WHEN ac IS NULL THEN NULL
                ELSE { node_id: ac.id, agent_id: agentNode.name }
            END) WHERE node IS NOT NULL] AS graph_nodes,
            [edge IN collect(DISTINCT CASE
                WHEN ac_next IS NULL THEN NULL
                ELSE { source: ac.id, target: ac_next.id }
            END) WHERE edge IS NOT NULL] AS graph_edges
    }

    RETURN
        session.sessionId AS session_id,
        input_content,
        input_embedding,
        output_content,
        output_embedding,
        metrics,
        graph_nodes,
        graph_edges
    """
    params: Dict[str, object] = {
        "group_id": group_id,
        "group_hash": group_hash,
        "embedding_model": embedding_model,
        "skip": max(0, skip),
        "limit": max(0, limit),
    }

    return query, params


def build_session_data_for_ia_inference_query(
    session_id: str,
    metric_name: str,
    embedding_model_name: str,
) -> tuple[str, Dict[str, object]]:
    """Build the Cypher query for session data used in IA inference.

    Mirrors ``Neo4jDBHandler.get_session_data_for_ia_inference`` in *oxp-lib*.
    """
    query = """
    MATCH (s:Session {sessionId: $session_id})
    MATCH (s)-[:hasMetric]->(m:Metric {metricName: $metric_name})
    MATCH (t:Transition {sessionId: s.sessionId})-[:representsExecution]->(ac:AgentCall)
    OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
    MATCH (input_embedding:Embedding {embeddingModel: $emb_model})-[:represents]->(input:State)-[:inputTo]->(t)
    MATCH (t)-[:leadsTo]->(output:State)<-[:represents]-(output_embedding:Embedding {embeddingModel: $emb_model})

    WITH s, m, t, ac, agentNode, input, output, input_embedding, output_embedding
    ORDER BY ac.startTime ASC

    WITH s, m, collect({
        agent: agentNode.name,
        input: input.content,
        input_embedding: input_embedding.embeddingVector,
        output: output.content,
        output_embedding: output_embedding.embeddingVector
    }) AS triples

    RETURN
        s.sessionId AS SessionID,
        triples AS Triples,
        m.metricResult AS RawMetric
    """
    return query, {
        "session_id": session_id,
        "metric_name": metric_name,
        "emb_model": embedding_model_name,
    }


def build_all_metrics_for_a_group_of_sessions_query(
    session_ids: List[str], subset: Iterable[str] | None
) -> Tuple[str, Dict[str, object]]:
    params = {"session_ids": session_ids}
    match_clause: str = "MATCH p=(s:Session)-[:hasMetric]->(m:Metric)"
    condition: str = "(s.sessionId IN $session_ids)"
    if subset is not None:
        params["metric_names"] = list(subset)
        condition = f"({condition} AND (m.metricName in $metric_names))"
    query: str = f"""{match_clause}
    WHERE {condition}
    RETURN Distinct
    s.sessionId as sessionId,
    m.metricName as metricName, 
    m.metricResult as metricResult
    """
    return query, params


def build_waste_estimation_data_query(
    session_ids: list[str], embedding_model_name: str
) -> tuple[str, dict[str, Any]]:
    query = """
        MATCH (s:Session)
        WHERE s.sessionId IN $included_ids

        MATCH (s)-[:hasInitialState]->(start:State)

        MATCH (t:Transition {sessionId: s.sessionId})-[:representsExecution]->(ac:AgentCall)
        MATCH (input_embedding:Embedding {embeddingModel: $emb_model})-[:represents]->(input:State)-[:inputTo]->(t)

        WITH s, t, ac, input, input_embedding
        ORDER BY ac.startTime ASC

        WITH s, head(collect({
            question: input.content,
            question_embedding: input_embedding.embeddingVector
        })) AS first_block

        RETURN DISTINCT
            s.sessionId AS SessionID,
            first_block.question AS question,
            first_block.question_embedding AS question_embedding
        """

    params = {"included_ids": session_ids, "emb_model": embedding_model_name}
    return query, params


def _build_wr_all_sessions_query(
    excluded_session_ids: Optional[List[str]] = None,
) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (s:Session)
    WHERE s.sessionId IS NOT NULL
      AND trim(s.sessionId) <> ""
        AND (
            size(coalesce($excluded_session_ids, [])) = 0
            OR NOT s.sessionId IN $excluded_session_ids
        )
    RETURN DISTINCT s.sessionId AS session_id
    """
    return query, {"excluded_session_ids": excluded_session_ids or []}


def _build_wr_sessions_by_setting_with_metrics_query(
    mas_id: Optional[str],
    excluded_session_ids: Optional[list[str]] = None,
) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (s:Session)-[:executesSession]->(mas:MAS)
    WHERE s.sessionId IS NOT NULL
        AND trim(s.sessionId) <> ""
        AND ($mas_id IS NULL OR coalesce(mas.id, "") = $mas_id)
        AND (
            size(coalesce($excluded_session_ids, [])) = 0
            OR NOT s.sessionId IN $excluded_session_ids
        )
        AND EXISTS { MATCH (s)-[:hasMetric]->(:Metric) }
    RETURN DISTINCT s.sessionId AS session_id
    """
    return query, {
        "mas_id": mas_id,
        "excluded_session_ids": excluded_session_ids or [],
    }


def build_wr_session_ids(
    mas_id: Optional[str] = None, excluded_session_ids: Optional[List[str]] = None
):
    if mas_id is None:
        query, params = _build_wr_all_sessions_query(
            excluded_session_ids=excluded_session_ids,
        )
    else:
        query, params = _build_wr_sessions_by_setting_with_metrics_query(
            mas_id=mas_id,
            excluded_session_ids=excluded_session_ids,
        )
    return query, params


def build_wr_agent_tool_baseline_by_session_ids_query(
    session_ids: list[str],
) -> tuple[str, Dict[str, object]]:
    query = """
    UNWIND $session_ids AS sid
    MATCH (t:Transition {sessionId: sid})-[:representsExecution]->(ac:AgentCall)
    OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
    OPTIONAL MATCH (ac)-[:hasToolCall]->(tc:ToolCall)
    OPTIONAL MATCH (tc)-[:executesTool]->(toolNode:Tool)
    RETURN
        coalesce(agentNode.name, "") AS agent_name,
        coalesce(toolNode.name, "") AS tool_name
    """
    return query, {"session_ids": session_ids}


def build_wr_tool_calls_by_session_query(sid: str) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (t:Transition {sessionId: $sid})-[:representsExecution]->(ac:AgentCall)-[:hasToolCall]->(tc:ToolCall)
    OPTIONAL MATCH (tc)-[:executesTool]->(toolNode:Tool)
    OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
    OPTIONAL MATCH (tc)-[:hasInitialState]->(input_state:State)
    OPTIONAL MATCH (tc)-[:hasFinalState]->(output_state:State)
    RETURN
      coalesce(toolNode.name, "") AS tool_name,
      coalesce(input_state.content, "") AS input_params,
      coalesce(output_state.content, "") AS tool_output,
      coalesce(output_state.content, "") AS output_content,
      coalesce(tc.startTime, 0.0) AS timestamp,
      coalesce(agentNode.name, "") AS agent_name
    ORDER BY timestamp ASC
    """
    return query, {"sid": sid}


def build_wr_agent_calls_by_session_query(sid: str) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (t:Transition {sessionId: $sid})-[:representsExecution]->(ac:AgentCall)
    OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
    OPTIONAL MATCH (ac)-[:hasToolCall]->(tc:ToolCall)
    OPTIONAL MATCH (tc)-[:executesTool]->(toolNode:Tool)
    WITH
        ac,
        agentNode,
        count(tc) AS tool_call_count,
        collect(DISTINCT coalesce(toolNode.name, "")) AS tool_names
    RETURN
        elementId(ac) AS agentcall_id,
        coalesce(agentNode.name, "") AS agent_name,
        coalesce(ac.startTime, 0.0) AS timestamp,
        tool_call_count,
        [name IN tool_names WHERE name <> ""] AS tool_names
    ORDER BY timestamp ASC, agentcall_id ASC
    """
    return query, {"sid": sid}


def build_wr_agent_tool_counts_by_session_query(
    sid: str,
) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (t:Transition {sessionId: $sid})-[:representsExecution]->(ac:AgentCall)-[:hasToolCall]->(tc:ToolCall)
    OPTIONAL MATCH (ac)-[:executesAgent]->(agentNode:Agent)
    OPTIONAL MATCH (tc)-[:executesTool]->(toolNode:Tool)
    WITH
        coalesce(agentNode.name, "") AS agent_name,
        coalesce(toolNode.name, "") AS tool_name
    WHERE agent_name <> "" AND tool_name <> ""
    RETURN agent_name, tool_name, count(*) AS call_count
    ORDER BY agent_name, tool_name
    """
    return query, {"sid": sid}


def build_wr_llm_calls_via_edges_query(sid: str) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (t:Transition {sessionId: $sid})-[:representsExecution]->(ac:AgentCall)
    OPTIONAL MATCH (ac)-[:hasLLMCall]->(lc:LLMCall)
    WITH DISTINCT lc
    WHERE lc IS NOT NULL
    OPTIONAL MATCH (lc)-[:executesLLM]->(llmNode:LLM)
    RETURN
      elementId(lc) AS node_eid,
      coalesce(lc.id, "") AS execution_id,
      coalesce(llmNode.name, "") AS model_name,
      coalesce(lc.promptTokenCount, 0) AS prompt_tokens,
      coalesce(lc.cacheReadTokenCount, 0) AS cached_tokens,
      coalesce(lc.completionTokenCount, 0) AS completion_tokens,
      coalesce(lc.totalTokenCount, 0) AS total_tokens,
      coalesce(lc.startTime, 0.0) AS timestamp
    ORDER BY timestamp ASC
    """
    return query, {"sid": sid}


def build_wr_llm_calls_by_session_property_query(
    sid: str,
) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (lc:LLMCall {sessionId: $sid})
    OPTIONAL MATCH (lc)-[:executesLLM]->(llmNode:LLM)
    RETURN
      elementId(lc) AS node_eid,
      coalesce(lc.id, "") AS execution_id,
      coalesce(llmNode.name, "") AS model_name,
      coalesce(lc.promptTokenCount, 0) AS prompt_tokens,
      coalesce(lc.cacheReadTokenCount, 0) AS cached_tokens,
      coalesce(lc.completionTokenCount, 0) AS completion_tokens,
      coalesce(lc.totalTokenCount, 0) AS total_tokens,
      coalesce(lc.startTime, 0.0) AS timestamp
    ORDER BY timestamp ASC
    """
    return query, {"sid": sid}


def build_wr_session_metrics_query(sid: str) -> tuple[str, Dict[str, object]]:
    query = """
    MATCH (s:Session {sessionId: $sid})-[:hasMetric]->(m:Metric)
    RETURN
        coalesce(m.metricName, m.metric_name, "") AS metric_name,
        coalesce(m.metricResult, m.metric_result, "") AS metric_result
    """
    return query, {"sid": sid}
