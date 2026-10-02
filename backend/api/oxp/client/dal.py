#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""DAL (Data Access Layer) private implementations for :class:`LocalClient`."""

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from oxp_ontology import OntologyValidationError, verify_kg_object
from oxp_ontology.models.edges import (
    aboutMetric,
    containsSession,
    hasMedioidSession,
    ofSemanticGroup,
)
from oxp_ontology.models.nodes import SemanticGroup

from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.query_builders import dal as dal_queries

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_JSON_PREFIX = "__json__:"
_SCALAR_TYPES = (str, int, float, bool)
# node_types whose `.id` index ingest_normalized_kg has already ensured exists
# in this process. CREATE INDEX IF NOT EXISTS is idempotent but still a round
# trip to the DB on every single call; since a worker process calls this once
# per session for its process's whole lifetime, this guard turns ~15-20
# no-op schema checks per ingest into a one-time cost per node_type.
_indexed_node_types: Set[str] = set()
# Node types that carry a unique constraint on `name` and must be merged on that key.
_NAME_KEYED_NODE_TYPES = frozenset({"LLM"})


MAX_SESSIONS_FOR_SINGLE_QUERY: int = 500

# ── get_state_content ────────────────────────────────────────────────────────


def get_state_content(
    db: Connector,
    filters_eq: Dict[str, str],
    filters_neq: Dict[str, str],
) -> List[Dict[str, str]]:
    """Return ``State`` node content matching the given filters.

    Equivalent to ``Neo4jDBHandler.get_state_content`` in *oxp-lib*:
    queries the graph for ``State`` nodes that satisfy *filters_eq* (equality)
    and *filters_neq* (inequality), and returns a list of
    ``{"id": stateId, "content": content}`` dicts.

    Parameters
    ----------
    db:
        An active :class:`~oxp.connectors.base.Connector` pointing at
        Neo4j.
    filters_eq:
        Property/value pairs that the ``State`` node **must** match.
    filters_neq:
        Property/value pairs that the ``State`` node **must not** match.

    Returns
    -------
    list[dict[str, str]]
        Each entry has ``"id"`` (the node's ``stateId``) and
        ``"content"`` (the node's ``content`` property).
    """
    query, params = dal_queries.build_state_content_query(filters_eq, filters_neq)

    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get state content: {exc}") from exc

    states: List[Dict[str, str]] = []
    for row in rows:
        # Neo4JConnector.execute returns record.data(), so each row is
        # {"n": {<node properties>}}.
        node = row.get("n") if isinstance(row, dict) else {}
        if not isinstance(node, dict):
            # neo4j-driver may return a Node object; convert via _properties.
            node = dict(getattr(node, "_properties", {}))
        states.append(
            {
                "id": str(node.get("id", "")),
                "content": str(node.get("content", "")),
            }
        )

    return states


# ── get_session_io ───────────────────────────────────────────────────────────


def get_session_io(
    db: Connector,
    session_id: str,
) -> List[Dict[str, str]]:
    """Return the initial and final ``State`` nodes for a session.

    Equivalent to ``Neo4jDBHandler.get_session_io`` in *oxp-lib*:
    traverses ``Session -[:hasFinalState]-> State`` and
    ``Session -[:hasInitialState]-> State`` and returns a list of
    ``{"id": id, "content": content}`` dicts.

    Parameters
    ----------
    db:
        An active :class:`~oxp.connectors.base.Connector` pointing at
        Neo4j.
    session_id:
        The ``sessionId`` property of the target ``Session`` node.

    Returns
    -------
    list[dict[str, str]]
        Each entry has ``"id"`` (the state's ``id``) and
        ``"content"`` (the state's ``content`` property).
    """
    transitions: List[Dict[str, str]] = []

    for edge in ("hasFinalState", "hasInitialState"):
        query, params = dal_queries.build_session_io_query(edge)
        params["session_id"] = session_id
        try:
            rows = db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(f"Failed to get session IO ({edge}): {exc}") from exc

        for row in rows:
            node = row.get("n") if isinstance(row, dict) else {}
            if not isinstance(node, dict):
                node = dict(getattr(node, "_properties", {}))
            transitions.append(
                {
                    "id": str(node.get("id", "")),
                    "content": str(node.get("content", "")),
                }
            )

    return transitions


# ── get_session_group ────────────────────────────────────────────────────────


def get_session_group(
    db: Connector,
    session_id: str = "",
    embedding_model: str = "",
    max_distance: float = 0.15,
) -> Tuple[str, str]:
    """Return the closest semantic group for a session.

    Equivalent to ``Neo4jDBHandler.get_session_group`` in *oxp-lib*:
    performs a cosine-similarity search against the medioid embeddings of
    leaf ``SemanticGroup`` nodes and returns the nearest one within
    *max_distance*.

    Parameters
    ----------
    db:
        An active :class:`~oxp.connectors.base.Connector` pointing at
        Neo4j.
    session_id:
        ``sessionId`` of the session to match.
    embedding_model:
        Name of the embedding model used to retrieve the vectors.
    max_distance:
        Maximum cosine distance (1 - similarity) allowed.

    Returns
    -------
    tuple[str, str]
        ``(group_id, node_hash)`` of the matched ``SemanticGroup``, or
        ``("", "")`` when no match is found.
    """
    if not session_id or not embedding_model:
        return "", ""

    query, params = dal_queries.build_session_group_query(
        session_id, embedding_model, max_distance
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get session group: {exc}") from exc

    if not rows:
        return "", ""

    row = rows[0] if isinstance(rows[0], dict) else {}
    group_id: str = row.get("group_id", "")
    node_hash: str = row.get("node_hash", "")
    if not group_id:
        return "", ""

    return group_id, node_hash


# ── acquire_hierarchical_grouping_lock ──────────────────────────────────────


def acquire_hierarchical_grouping_lock(
    db: Connector,
    owner: str,
    ttl_seconds: int = 300,
) -> bool:
    """Atomically acquire the hierarchical-grouping system lock.

    Equivalent to ``Neo4jDBHandler.acquire_hierarchical_grouping_lock`` in
    *oxp-lib*: uses a ``MERGE``-based Cypher query to claim the
    ``SystemLock`` node when it is either unlocked, expired, or already
    owned by *owner*.

    Parameters
    ----------
    db:
        An active :class:`~oxp.connectors.base.Connector` pointing at
        Neo4j.
    owner:
        Identifier of the caller acquiring the lock.
    ttl_seconds:
        Lock time-to-live in seconds (default 300).

    Returns
    -------
    bool
        ``True`` if the lock was successfully acquired, ``False`` otherwise.
    """
    query, params = dal_queries.build_acquire_hierarchical_grouping_lock_query(
        owner, ttl_seconds
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to acquire grouping lock: {exc}") from exc

    if not rows:
        return False
    row = rows[0] if isinstance(rows[0], dict) else {}
    return bool(row.get("acquired"))


# ── is_hierarchical_grouping_locked / wait_for_hierarchical_grouping_unlock ──


def is_hierarchical_grouping_locked(db: Connector) -> bool:
    """Return ``True`` when the hierarchical-grouping system lock is held.

    Equivalent to ``Neo4jDBHandler.is_hierarchical_grouping_locked`` in
    *oxp-lib*: queries for a ``SystemLock`` node whose ``expiresAt``
    timestamp is still in the future.

    Parameters
    ----------
    db:
        An active :class:`~oxp.connectors.base.Connector` pointing at
        Neo4j.
    """
    query, params = dal_queries.build_hierarchical_grouping_lock_query()
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to check grouping lock: {exc}") from exc

    if not rows:
        return False
    row = rows[0]
    return bool(row.get("is_locked") if isinstance(row, dict) else False)


async def wait_for_hierarchical_grouping_unlock(
    db: Connector,
    max_wait_seconds: int = 120,
    poll_interval_seconds: float = 2.0,
) -> bool:
    """Poll until the hierarchical-grouping lock is released or timeout expires.

    Equivalent to ``Neo4jKGDAL.wait_for_hierarchical_grouping_unlock`` in
    *oxp-lib*.

    Parameters
    ----------
    db:
        An active :class:`~oxp.connectors.base.Connector` pointing at
        Neo4j.
    max_wait_seconds:
        Maximum number of seconds to wait before giving up.
    poll_interval_seconds:
        Seconds to sleep between consecutive lock checks.

    Returns
    -------
    bool
        ``True`` if the lock was released within the timeout, ``False``
        otherwise.
    """
    if not is_hierarchical_grouping_locked(db):
        return True

    elapsed = 0.0
    while elapsed < max_wait_seconds:
        await asyncio.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds
        if not is_hierarchical_grouping_locked(db):
            return True

    return False


# ── attach_session_to_group ──────────────────────────────────────────────────


def attach_session_to_group(
    db: Connector,
    session_id: str = "",
    group_id: str = "",
    node_hash: str = "",
) -> bool:
    """Attach a session to a semantic group if the node hash still matches.

    Equivalent to ``Neo4jDBHandler.attach_session_to_group`` in *oxp-lib*:
    first fetches the group's current session lists to compute a new hash,
    then conditionally writes the relationship guarded by *node_hash* to
    detect concurrent modifications.

    Parameters
    ----------
    db:
        An active :class:`~oxp.connectors.base.Connector` pointing at
        Neo4j.
    session_id:
        ``sessionId`` of the session to attach.
    group_id:
        ``id`` of the target ``SemanticGroup`` node.
    node_hash:
        Expected current hash of the group; pass ``""`` to skip the guard.

    Returns
    -------
    bool
        ``True`` if the relationship was successfully created, ``False`` if
        the group was not found or was concurrently modified.
    """
    if not session_id or not group_id:
        return False

    # ── step 1: fetch current session lists ──────────────────────────────────
    fetch_query, fetch_params = dal_queries.build_attach_session_fetch_query(
        group_id, node_hash
    )
    try:
        rows = db.execute(fetch_query, fetch_params)
    except Exception as exc:
        raise DatabaseError(f"Failed to fetch group session ids: {exc}") from exc

    if not rows:
        return False

    row = rows[0] if isinstance(rows[0], dict) else {}
    all_session_ids: list = list(row.get("all_session_ids", []))
    direct_session_ids: list = list(row.get("direct_session_ids", []))

    # ── step 2: compute new hash in Python ───────────────────────────────────
    all_session_ids.append(session_id)
    direct_session_ids.append(session_id)

    session_set = sorted({s for s in all_session_ids if s})
    new_group_hash = hashlib.sha256(",".join(session_set).encode()).hexdigest()
    new_direct_sessions = sorted({s for s in direct_session_ids if s})

    # ── step 3: write relationship ────────────────────────────────────────────
    update_query, update_params = dal_queries.build_attach_session_update_query(
        session_id, group_id, node_hash, new_direct_sessions, new_group_hash
    )
    try:
        rows = db.execute(update_query, update_params)
    except Exception as exc:
        raise DatabaseError(f"Failed to attach session to group: {exc}") from exc

    if not rows:
        logger.debug(
            "Failed to attach session %s to group %s, group was modified.",
            session_id,
            group_id,
        )
        return False

    return True


# ── private helpers ──────────────────────────────────────────────────────────


def _ingest_node(db: Connector, label: str, properties: Dict[str, Any]) -> None:
    """Upsert a single labelled node via MERGE on its ``id`` property."""
    query, params = dal_queries.build_ingest_node_query(label, properties)
    try:
        db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to ingest {label} node: {exc}") from exc


def _create_rel(
    db: Connector,
    from_label: str,
    from_id_labels: List[str],
    from_id_values: List[str],
    to_label: str,
    to_id_labels: List[str],
    to_id_values: List[str],
    relationship: str,
) -> None:
    """Create (MERGE) a directed relationship between two nodes."""
    query, params = dal_queries.build_create_rel_query(
        from_label,
        from_id_labels,
        from_id_values,
        to_label,
        to_id_labels,
        to_id_values,
        relationship,
    )
    max_attempts = 4
    retry_delay_seconds = 0.2

    for attempt in range(1, max_attempts + 1):
        try:
            db.execute(query, params)
            return
        except Exception as exc:
            error_text = str(exc)
            is_deadlock = (
                "DeadlockDetected" in error_text
                or "Neo.TransientError.Transaction.DeadlockDetected" in error_text
            )
            if not is_deadlock or attempt == max_attempts:
                raise DatabaseError(
                    f"Failed to create {from_label}-[:{relationship}]->{to_label}: {exc}"
                ) from exc

            logger.warning(
                "Retrying transient deadlock for %s-[:%s]->%s (attempt %s/%s)",
                from_label,
                relationship,
                to_label,
                attempt,
                max_attempts,
            )
            time.sleep(retry_delay_seconds * attempt)


def _is_safe_cypher_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.match(value))


def _chunked(rows: List[Dict[str, Any]], size: int) -> Iterator[List[Dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _neo4j_props(values: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dict values into Neo4j-safe scalar/list properties.

    Dict values and non-scalar lists are JSON-serialized with a sentinel
    prefix so they can be round-tripped by dump tooling when needed.
    """
    props: Dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, _SCALAR_TYPES):
            props[key] = value
            continue
        if isinstance(value, list):
            if all((item is None) or isinstance(item, _SCALAR_TYPES) for item in value):
                props[key] = [item for item in value if item is not None]
            else:
                props[key] = _JSON_PREFIX + json.dumps(value, ensure_ascii=False)
            continue
        if isinstance(value, dict):
            props[key] = _JSON_PREFIX + json.dumps(value, ensure_ascii=False)
    return props


def ingest_normalized_kg(
    db: Connector,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    run_id: str = "",
    override: bool = False,
    batch_size: int = 200,
) -> bool:
    """Ingest a denormalized KG payload into Neo4j.

    This is the DAL equivalent of the norm Neo4j push step and is intended
    for workers that produce ``{nodes, edges}`` payloads and need to avoid
    ``dal_kg`` usage.

    Every node is labelled with its ``node_type`` only - no generic label is
    added, since the ontology defines no such class. An edge's endpoint type
    is looked up from *this same batch's* ``nodes`` (an id -> node_type map
    built below); an edge whose endpoint isn't in that map is skipped rather
    than merged against an untyped placeholder node, since callers are
    expected to only submit edges between nodes they are also submitting.
    """
    if not nodes and not edges:
        return True

    if override and run_id:
        try:
            db.execute_command(
                "MATCH (n {runId: $run_id}) DETACH DELETE n",
                {"run_id": run_id},
            )
        except Exception as exc:
            raise DatabaseError(
                f"Failed to delete previous run '{run_id}': {exc}"
            ) from exc

    nodes_by_type: Dict[str, List[Dict[str, Any]]] = {}
    id_to_type: Dict[str, str] = {}
    for node in nodes:
        node_type = str(node.get("node_type", "")).strip()
        node_id = str(node.get("id", "")).strip()
        if not node_type or not node_id:
            continue
        if not _is_safe_cypher_identifier(node_type):
            raise DatabaseError(f"Unsafe node type for Cypher label: {node_type!r}")

        id_to_type[node_id] = node_type
        row = {
            "id": node_id,
            "props": _neo4j_props({k: v for k, v in node.items() if k != "node_type"}),
        }
        nodes_by_type.setdefault(node_type, []).append(row)

    for node_type, rows in nodes_by_type.items():
        if node_type not in _indexed_node_types:
            try:
                db.execute_command(
                    f"CREATE INDEX {str.lower(node_type)}_id IF NOT EXISTS "
                    f"FOR (n:{node_type}) ON (n.id)"
                )
            except Exception as exc:
                raise DatabaseError(
                    f"Failed to ensure index for '{node_type}': {exc}"
                ) from exc
            _indexed_node_types.add(node_type)

        if node_type in _NAME_KEYED_NODE_TYPES:
            # These types have a unique constraint on `name`; merge on that key.
            query = (
                "UNWIND $rows AS row\n"
                f"MERGE (n:{node_type} {{name: row.props.name}})\n"
                "SET n += row.props"
            )
        else:
            query = (
                "UNWIND $rows AS row\n"
                f"MERGE (n:{node_type} {{id: row.id}})\n"
                "SET n += row.props"
            )
        for batch in _chunked(rows, batch_size):
            try:
                db.execute_command(query, {"rows": batch})
            except Exception as exc:
                raise DatabaseError(
                    f"Failed to ingest '{node_type}' nodes: {exc}"
                ) from exc

    edges_by_key: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for edge in edges:
        edge_type = str(edge.get("edge_type", "")).strip()
        from_id = str(edge.get("from_id", "")).strip()
        to_id = str(edge.get("to_id", "")).strip()
        if not edge_type or not from_id or not to_id:
            continue
        if not _is_safe_cypher_identifier(edge_type):
            raise DatabaseError(
                f"Unsafe edge type for Cypher relationship: {edge_type!r}"
            )

        from_type = id_to_type.get(from_id)
        to_type = id_to_type.get(to_id)
        if from_type is None or to_type is None:
            logger.error(
                "Skipping %s edge %s->%s: endpoint node_type not found in this batch",
                edge_type,
                from_id,
                to_id,
            )
            continue

        rel_props = {
            k: v
            for k, v in edge.items()
            if k not in {"edge_type", "from_id", "from_type", "to_id", "to_type"}
        }
        edges_by_key.setdefault((edge_type, from_type, to_type), []).append(
            {
                "from_id": from_id,
                "to_id": to_id,
                "props": _neo4j_props(rel_props),
            }
        )

    for (edge_type, from_type, to_type), rows in edges_by_key.items():
        # Nodes are ingested above (in full) before any edge is ingested, so a plain
        # MATCH is safe here - both endpoints of every edge already exist.
        query = (
            "UNWIND $rows AS row\n"
            f"MATCH (a:{from_type} {{id: row.from_id}})\n"
            f"MATCH (b:{to_type} {{id: row.to_id}})\n"
            f"MERGE (a)-[r:{edge_type}]->(b)\n"
            "SET r += row.props"
        )
        for batch in _chunked(rows, batch_size):
            try:
                db.execute_command(query, {"rows": batch})
            except Exception as exc:
                raise DatabaseError(
                    f"Failed to ingest '{edge_type}' edges: {exc}"
                ) from exc

    return True


# ── release_hierarchical_grouping_lock ───────────────────────────────────────


def release_hierarchical_grouping_lock(db: Connector, owner: str) -> bool:
    """Release the hierarchical-grouping system lock held by *owner*.

    Equivalent to ``Neo4jDBHandler.release_hierarchical_grouping_lock`` in
    *oxp-lib*.
    """
    query, params = dal_queries.build_release_hierarchical_grouping_lock_query(owner)
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to release grouping lock: {exc}") from exc
    if not rows:
        return False
    row = rows[0] if isinstance(rows[0], dict) else {}
    return bool(row.get("released"))


# ── get_all_session_input_embeddings ─────────────────────────────────────────


def get_all_session_input_embeddings(
    db: Connector,
    application_id: str,
    embedding_model: str,
) -> List[Dict[str, Any]]:
    """Return all input embeddings for sessions belonging to an application.

    Equivalent to ``Neo4jDBHandler.get_all_session_input_embeddings`` in
    *oxp-lib*.
    """
    query, params = dal_queries.build_all_session_input_embeddings_query(
        application_id, embedding_model
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get session input embeddings: {exc}") from exc

    results: List[Dict[str, Any]] = []
    for row in rows:
        row = row if isinstance(row, dict) else {}
        if row.get("session_id") and row.get("input_embedding"):
            results.append(
                {
                    "session_id": row["session_id"],
                    "input_query": row.get("input_query", ""),
                    "input_embedding": row["input_embedding"],
                }
            )
    return results


# ── get_semantic_group_hierarchy ─────────────────────────────────────────────


def get_semantic_group_hierarchy(
    db: Connector,
    embedding_model: str,
    application_id: str,
) -> List[Dict[str, Any]]:
    """Return all semantic groups for an application ordered by session count.

    Equivalent to ``Neo4jDBHandler.get_semantic_group_hierarchy`` in *oxp-lib*.
    """
    query, params = dal_queries.build_semantic_group_hierarchy_query(
        embedding_model, application_id
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get semantic group hierarchy: {exc}") from exc

    groups: List[Dict[str, Any]] = []
    for row in rows:
        row = row if isinstance(row, dict) else {}
        properties = row.get("sg", row)
        if not isinstance(properties, dict):
            properties = dict(getattr(properties, "_properties", {}))
        properties.pop("layer", None)
        groups.append(properties)
    return groups


# ── ingest_semantic_groups ────────────────────────────────────────────────────


def ingest_semantic_groups(
    db: Connector,
    group_hierarchy: List[Dict[str, Any]],
    delta: Dict[str, List[str]],
    application_id: str,
) -> None:
    """Upsert / remove SemanticGroup nodes and rebuild their relationships.

    Equivalent to ``Neo4jKGDAL.ingest_semantic_groups`` +
    ``Neo4jDBHandler.ingest_semantic_group_nodes`` in *oxp-lib*.

    Parameters
    ----------
    db:
        Neo4j connector.
    group_hierarchy:
        List of group property dicts (matching ``SemanticGroupNode.to_dict()``
        ``"properties"`` sub-dict: keys ``id``, ``sessionIds``,
        ``childrenNodes``, etc.).
    delta:
        Dict with ``"add"``, ``"update"``, and ``"remove"`` lists of group IDs.
    application_id:
        ``masId`` of the owning MAS node.
    """
    upsert_list: List[str] = delta.get("add", []) + delta.get("update", [])
    remove_list: List[str] = delta.get("remove", [])

    if not (upsert_list or remove_list):
        return

    upsert_set = set(upsert_list)

    def _run_write(query: str, params: Dict[str, Any], tx: Any | None) -> None:
        if tx is not None:
            tx.run(query, parameters=params).consume()
        else:
            db.execute(query, params)

    def _apply_semantic_group_ingest(tx: Any | None = None) -> None:
        if remove_list:
            remove_query, remove_params = (
                dal_queries.build_remove_semantic_groups_query(remove_list)
            )
            _run_write(remove_query, remove_params, tx)

        if not upsert_list:
            return

        cleanup_query, cleanup_params = dal_queries.build_cleanup_semantic_groups_query(
            upsert_list
        )
        _run_write(cleanup_query, cleanup_params, tx)

        for group in group_hierarchy:
            group_id: str = group.get("id", "")
            if group_id not in upsert_set:
                continue

            session_ids: List[str] = group.get("sessionIds", [])
            child_ids: List[str] = group.get("childrenNodes", [])
            medioid_session_id: str = group.get("medioidSessionId", "")

            ontology_group = SemanticGroup(
                id=group_id,
                name=group.get("groupName", ""),
                description=group.get("groupSummary", ""),
                embeddingModel=group.get("embeddingModel", ""),
                nSessions=group.get("nSessions", 0),
                splitDistance=group.get("splitDistance", 0.0),
                nodeHash=group.get("nodeHash", ""),
            )
            verify_edges: List[Any] = [
                containsSession(source_id=group_id, target_id=target_id)
                for target_id in (*session_ids, *child_ids)
            ]
            if medioid_session_id:
                verify_edges.append(
                    hasMedioidSession(source_id=group_id, target_id=medioid_session_id)
                )
            verification = verify_kg_object(ontology_group, edges=verify_edges)
            if not verification.conforms:
                raise OntologyValidationError(verification)

            ingest_query, ingest_params = dal_queries.build_ingest_node_query(
                "SemanticGroup", group
            )
            _run_write(ingest_query, ingest_params, tx)

        for group in group_hierarchy:
            group_id: str = group.get("id", "")
            if group_id not in upsert_set:
                continue

            for session_id in group.get("sessionIds", []):
                rel_query, rel_params = dal_queries.build_create_rel_query(
                    "SemanticGroup",
                    ["id"],
                    [group_id],
                    "Session",
                    ["sessionId"],
                    [session_id],
                    "containsSession",
                )
                _run_write(rel_query, rel_params, tx)

            medioid_session_id = group.get("medioidSessionId", "")
            if medioid_session_id:
                rel_query, rel_params = dal_queries.build_create_rel_query(
                    "SemanticGroup",
                    ["id"],
                    [group_id],
                    "Session",
                    ["sessionId"],
                    [medioid_session_id],
                    "hasMedioidSession",
                )
                _run_write(rel_query, rel_params, tx)

            child_ids: List[str] = group.get("childrenNodes", [])
            if child_ids:
                delete_stale_query, delete_stale_params = (
                    dal_queries.build_delete_stale_child_edges_query(child_ids)
                )
                _run_write(delete_stale_query, delete_stale_params, tx)
                for child_id in child_ids:
                    rel_query, rel_params = dal_queries.build_create_rel_query(
                        "SemanticGroup",
                        ["id"],
                        [group_id],
                        "SemanticGroup",
                        ["id"],
                        [child_id],
                        "containsSession",
                    )
                    _run_write(rel_query, rel_params, tx)

            rel_query, rel_params = dal_queries.build_create_rel_query(
                "MAS",
                ["masId"],
                [application_id],
                "SemanticGroup",
                ["id"],
                [group_id],
                "hasSemanticGroup",
            )
            _run_write(rel_query, rel_params, tx)

        for group in group_hierarchy:
            if group.get("id", "") in upsert_set:
                continue
            for child_id in group.get("childrenNodes", []):
                if child_id in upsert_set:
                    rel_query, rel_params = dal_queries.build_create_rel_query(
                        "SemanticGroup",
                        ["id"],
                        [group["id"]],
                        "SemanticGroup",
                        ["id"],
                        [child_id],
                        "containsSession",
                    )
                    _run_write(rel_query, rel_params, tx)

    try:
        driver = getattr(db, "driver", None)
        database = getattr(db, "_database", None)
        if driver is not None:
            with driver.session(database=database) as session:
                session.execute_write(lambda tx: _apply_semantic_group_ingest(tx))
        else:
            _apply_semantic_group_ingest()
    except Exception as exc:
        raise DatabaseError(f"Failed to ingest semantic groups: {exc}") from exc


# ── update_semantic_group_names_and_summaries ─────────────────────────────────


def update_semantic_group_names_and_summaries(
    db: Connector,
    group_nodes: List[Dict[str, Any]],
) -> None:
    """Bulk-update the ``groupName`` and ``groupSummary`` of SemanticGroup nodes.

    Equivalent to ``Neo4jDBHandler.update_semantic_group_names_and_summaries``
    in *oxp-lib*.

    Parameters
    ----------
    group_nodes:
        List of dicts with keys ``"uuid"`` (node id), ``"group_name"``, and
        ``"group_summary"`` — matching the attribute names of ``SemanticGroupNode``.
    """
    if not group_nodes:
        return
    groups = [
        {
            "id": g.get("uuid", g.get("id", "")),
            "groupName": g.get("group_name", g.get("groupName", "")),
            "groupSummary": g.get("group_summary", g.get("groupSummary", "")),
        }
        for g in group_nodes
    ]
    query, params = dal_queries.build_update_semantic_group_names_query(groups)
    try:
        db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to update semantic group names/summaries: {exc}"
        ) from exc


# ── get_semantic_groups_needing_analysis ──────────────────────────────────────


def get_semantic_groups_needing_analysis(
    db: Connector,
    embedding_model: str,
) -> List[Tuple[str, str]]:
    """Return ``(group_id, group_hash)`` pairs for groups missing analysis reports.

    Equivalent to ``Neo4jDBHandler.get_semantic_groups_needing_analysis`` in
    *oxp-lib*.
    """
    query, params = dal_queries.build_semantic_groups_needing_analysis_query(
        embedding_model
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get groups needing analysis: {exc}") from exc

    return [
        (r["group_id"], r["group_hash"])
        for r in rows
        if isinstance(r, dict) and r.get("group_id")
    ]


# ── analysis_pre_check ────────────────────────────────────────────────────────


def analysis_pre_check(
    db: Connector,
    group_id: str,
    report_type: str,
    group_hash: str = "",
    session_id: str = "",
) -> bool:
    """Return ``True`` when the group is unchanged and has no existing report.

    Equivalent to ``Neo4jDBHandler.analysis_pre_check`` in *oxp-lib*.
    """
    if not group_id:
        logger.error("Missing group ID.")
        return False

    try:
        query, _ = dal_queries.build_analysis_pre_check_query(
            report_type, with_session_id=bool(session_id)
        )
    except ValueError as exc:
        logger.error(str(exc))
        return False

    params: Dict[str, Any] = {"group_id": group_id, "group_hash": group_hash}
    if session_id:
        params["session_id"] = session_id

    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to run analysis pre-check: {exc}") from exc

    if not rows:
        return False
    row = rows[0] if isinstance(rows[0], dict) else {}
    return bool(row.get("can_analyze", False))


# ── generate_insights_from_query ─────────────────────────────────────────────


def generate_insights_from_query(
    db: Connector,
    query: str,
    application_id: str,
) -> List[Dict[str, Any]]:
    """Execute an insight-generation Cypher query parameterised by *application_id*.

    Equivalent to ``Neo4jDBHandler.generate_insights_from_query`` in *oxp-lib*.
    The *query* string is provided by the caller and is executed with a single
    ``$application_id`` parameter; it is the caller's responsibility to ensure
    the query is safe.
    """
    if not query:
        return []
    try:
        rows = db.execute(query, {"application_id": application_id})
    except Exception as exc:
        raise DatabaseError(f"Failed to generate insights: {exc}") from exc
    return [r for r in rows if isinstance(r, dict)]


# ── ingest_consistency_report ────────────────────────────────────────────────


def ingest_consistency_report(
    db: Connector,
    group_id: str,
    report: Any,
    group_hash: str = "",
    source: Any = None,
) -> bool:
    """Ingest a ConsistencyReport node and link it to a SemanticGroup.

    Equivalent to ``Neo4jDBHandler.ingest_consistency_reports`` in *oxp-lib*.

    Parameters
    ----------
    report:
        A ``oxp_ontology.models.nodes.consistency_report.ConsistencyReport``
        instance, with an ``id`` field set to its MERGE key, built using only
        real oxp-ontology properties (``mean``, ``confidenceInterval``,
        ``confidenceIndicator``, ...). Verified against the bundled SHACL
        shapes (raises ``OntologyValidationError`` on a mandatory-property
        violation) before being written.
    source:
        The ``dem.consistency.utils.ConsistencySessions`` this report was
        computed from, if available. Its ``.metadata`` (e.g.
        ``{"metric": "Cost"}``) is stored as the node's ``metadata``
        property -- not an ontology property of ConsistencyReport itself,
        so it's read off the original detector result rather than smuggled
        onto the ontology object. Read back by
        ``query_builders.semanticgroups.get_consistency_report``.
    """
    metadata = getattr(source, "metadata", None) or {}
    metric_name = metadata.get("metric", "")
    session_ids = getattr(source, "session_ids", None) or []

    verify_edges: List[Any] = [ofSemanticGroup(source_id=report.id, target_id=group_id)]
    if report.dataType == "metric" and metric_name:
        verify_edges.append(aboutMetric(source_id=report.id, target_id=metric_name))

    verification = verify_kg_object(report, edges=verify_edges)
    if not verification.conforms:
        raise OntologyValidationError(verification)

    label = "ConsistencyReport"
    props: Dict[str, Any] = {
        "id": report.id,
        "groupId": group_id,
        "dataType": report.dataType,
        "mean": report.mean,
        "confidenceInterval": report.confidenceInterval,
        "confidenceIndicator": report.confidenceIndicator,
        "metadata": json.dumps(metadata),
        "nodeHash": group_hash,
    }
    _ingest_node(db, label, props)

    guard_labels = ["id"]
    guard_values = [group_id]
    if group_hash:
        guard_labels.append("nodeHash")
        guard_values.append(group_hash)
    _create_rel(
        db,
        "SemanticGroup",
        guard_labels,
        guard_values,
        label,
        ["id"],
        [props["id"]],
        "hasConsistencyReport",
    )
    _create_rel(
        db,
        label,
        ["id"],
        [props["id"]],
        "SemanticGroup",
        ["id"],
        [group_id],
        "ofSemanticGroup",
    )
    if report.dataType == "metric" and metric_name:
        for session_id in session_ids:
            _create_rel(
                db,
                label,
                ["id"],
                [props["id"]],
                "Metric",
                ["metricName", "sessionId"],
                [metric_name, session_id],
                "aboutMetric",
            )
    return True


# ── ingest_anomaly_report ────────────────────────────────────────────────────


def ingest_anomaly_report(
    db: Connector,
    group_id: str,
    report: Any,
    group_hash: str = "",
    source: Any = None,
) -> bool:
    """Ingest an AnomalyReport node and link it to a SemanticGroup and sessions.

    Equivalent to ``Neo4jDBHandler.ingest_anomaly_reports`` in *oxp-lib*.

    Parameters
    ----------
    report:
        A ``oxp_ontology.models.nodes.anomaly_report.AnomalyReport``
        instance, with an ``id`` field set to its MERGE key, built using only
        real oxp-ontology properties (``scores``, ``threshold``, ...).
        Verified against the bundled SHACL shapes (raises
        ``OntologyValidationError`` on a mandatory-property violation)
        before being written.
    source:
        The ``dem.anomaly.AnomalyDetectionSessions`` this report was
        computed from, if available. Its ``.metadata``/``.inlier_sessions``/
        ``.outlier_sessions`` aren't ontology properties of AnomalyReport
        itself (the ontology expresses per-session/metric anomaly
        membership via ``isAnomalous`` edges, not JSON-blob node
        properties), so they're read off the original detector result
        rather than smuggled onto the ontology object. Stored as
        ``metadata``/``inliersValues``/``outliersValues``/``metricName``
        node properties, read back by
        ``query_builders.semanticgroups.get_anomaly_report`` and
        ``client._semanticgroups``, and used below to link outlier
        sessions/metrics to this report.
    """
    metadata = getattr(source, "metadata", None) or {}
    inlier_sessions = getattr(source, "inlier_sessions", None) or []
    outlier_sessions = getattr(source, "outlier_sessions", None) or []
    metric_name = metadata.get("metric", "")

    verify_edges: List[Any] = [ofSemanticGroup(source_id=report.id, target_id=group_id)]
    if report.dataType == "metric" and metric_name:
        verify_edges.append(aboutMetric(source_id=report.id, target_id=metric_name))

    verification = verify_kg_object(report, edges=verify_edges)
    if not verification.conforms:
        raise OntologyValidationError(verification)

    label = "AnomalyReport"
    props: Dict[str, Any] = {
        "id": report.id,
        "groupId": group_id,
        "dataType": report.dataType,
        "metricName": metric_name,
        "inliersValues": json.dumps(inlier_sessions),
        "outliersValues": json.dumps(outlier_sessions),
        "scores": report.scores,
        "threshold": report.threshold,
        "metadata": json.dumps(metadata),
        "nodeHash": group_hash,
    }
    _ingest_node(db, label, props)

    guard_labels = ["id"]
    guard_values = [group_id]
    if group_hash:
        guard_labels.append("nodeHash")
        guard_values.append(group_hash)
    _create_rel(
        db,
        "SemanticGroup",
        guard_labels,
        guard_values,
        label,
        ["id"],
        [props["id"]],
        "hasAnomalyReport",
    )
    _create_rel(
        db,
        label,
        ["id"],
        [props["id"]],
        "SemanticGroup",
        ["id"],
        [group_id],
        "ofSemanticGroup",
    )
    if metric_name:
        for session_id in sorted({*inlier_sessions, *outlier_sessions}):
            _create_rel(
                db,
                label,
                ["id"],
                [props["id"]],
                "Metric",
                ["metricName", "sessionId"],
                [metric_name, session_id],
                "aboutMetric",
            )

    # link each outlier session and metric → anomaly report
    report_id: str = props["id"]

    for session_id in outlier_sessions:
        _create_rel(
            db,
            "Session",
            ["sessionId"],
            [session_id],
            label,
            ["id"],
            [report_id],
            "hasAnomalyReport",
        )
        if metric_name:
            _create_rel(
                db,
                "Metric",
                ["metricName", "sessionId"],
                [metric_name, session_id],
                label,
                ["id"],
                [report_id],
                "hasAnomalyReport",
            )
    return True


# ── ingest_normal_behaviour_report ───────────────────────────────────────────


def ingest_normal_behaviour_report(
    db: Connector,
    group_id: str,
    report: Any,
    group_hash: str = "",
    source: Any = None,
) -> bool:
    """Ingest a NormalBehaviourReport node and link it to a SemanticGroup.

    Equivalent to ``Neo4jDBHandler.ingest_normal_behaviour_reports`` in
    *oxp-lib*.

    Parameters
    ----------
    report:
        A ``oxp_ontology.models.nodes.normal_behaviour_report.NormalBehaviourReport``
        instance, with an ``id`` field set to its MERGE key, built using only
        real oxp-ontology properties (``rawResult``, ``centroid``,
        ``representativeSample``, ``representativeProcessedSample``, ...).
        Verified against the bundled SHACL shapes (raises
        ``OntologyValidationError`` on a mandatory-property violation)
        before being written.
    source:
        The ``dem.normal_behaviour.utils.NormalBehaviourSessions`` this
        report was computed from, if available. Its ``.metadata`` (e.g.
        ``{"metric": "Cost"}``) is stored as the node's ``metadata``
        property -- not an ontology property of NormalBehaviourReport
        itself, so it's read off the original detector result rather than
        smuggled onto the ontology object. Read back by
        ``query_builders.semanticgroups.get_normal_behaviour_report``.
    """
    metadata = getattr(source, "metadata", None) or {}
    metric_name = metadata.get("metric", "")
    session_ids = getattr(source, "session_ids", None) or []

    verify_edges: List[Any] = [ofSemanticGroup(source_id=report.id, target_id=group_id)]
    if report.dataType == "metric" and metric_name:
        verify_edges.append(aboutMetric(source_id=report.id, target_id=metric_name))

    verification = verify_kg_object(report, edges=verify_edges)
    if not verification.conforms:
        raise OntologyValidationError(verification)

    label = "NormalBehaviourReport"
    props: Dict[str, Any] = {
        "id": report.id,
        "groupId": group_id,
        "dataType": report.dataType,
        "rawResult": report.rawResult,
        "metadata": json.dumps(metadata),
        "nodeHash": group_hash,
        "centroid": report.centroid,
        "representativeSample": report.representativeSample,
        "representativeProcessedSample": report.representativeProcessedSample,
    }
    _ingest_node(db, label, props)

    guard_labels = ["id"]
    guard_values = [group_id]
    if group_hash:
        guard_labels.append("nodeHash")
        guard_values.append(group_hash)
    _create_rel(
        db,
        "SemanticGroup",
        guard_labels,
        guard_values,
        label,
        ["id"],
        [props["id"]],
        "hasNormalBehaviourReport",
    )
    _create_rel(
        db,
        label,
        ["id"],
        [props["id"]],
        "SemanticGroup",
        ["id"],
        [group_id],
        "ofSemanticGroup",
    )
    if report.dataType == "metric" and metric_name:
        for session_id in session_ids:
            _create_rel(
                db,
                label,
                ["id"],
                [props["id"]],
                "Metric",
                ["metricName", "sessionId"],
                [metric_name, session_id],
                "aboutMetric",
            )
    return True


# ── get_all_metrics_for_a_session ─────────────────────────────────────────────


def get_all_metrics_for_a_group_of_sessions(
    db: Connector, session_ids: List[str], subset: Optional[Iterable[str]] = None
) -> Dict[str, Dict[str, Any]]:
    query, params = dal_queries.build_all_metrics_for_a_group_of_sessions_query(
        session_ids=session_ids, subset=subset
    )
    res_list = db.execute(query=query, params=params)
    res = dict()
    for record in res_list:
        session_id = record["sessionId"]
        if session_id not in res:
            res[session_id] = dict()
        metric_name = record["metricName"]
        metric_result = record["metricResult"]
        if isinstance(metric_result, (int, float)):
            metric_value = metric_result
        elif isinstance(metric_result, str):
            metric_value = float(json.loads(metric_result)["value"])
        else:
            raise ValueError(
                f"Unknown metric result type for session_id : {session_id}"
                f" and metric_name : {metric_name}"
            )

        res[session_id][metric_name] = metric_value
    return res


# ── get_mas_name ──────────────────────────────────────────────────────────────


def get_mas_name(db: Connector, session_id: str) -> str:
    """Return the MAS name for a session.

    Equivalent to ``Neo4jDBHandler.get_mas_name`` in *oxp-lib*.

    Raises :class:`ValueError` when no MAS is found.
    """
    query, params = dal_queries.build_mas_name_query()
    params["session_id"] = session_id
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get MAS name: {exc}") from exc

    if not rows:
        raise ValueError(f"No MAS name found for {session_id}")
    row = rows[0] if isinstance(rows[0], dict) else {}
    return str(row.get("masId", ""))


# ── get_session_io_embeddings ─────────────────────────────────────────────────


def get_session_io_embeddings(db: Connector, session_id: str) -> Dict[str, Any]:
    """Return a session's input/output content and embeddings.

    Equivalent to ``Neo4jKGDAL.get_session_io_embeddings`` in *oxp-lib*.
    """
    query = """
    MATCH (s:Session {sessionId: $session_id})
    OPTIONAL MATCH (in_emb:Embedding)-[:represents]->(in_state:State)<-[:hasInitialState]-(s)
    OPTIONAL MATCH (out_emb:Embedding)-[:represents]->(out_state:State)<-[:hasFinalState]-(s)
    RETURN
        in_state.content           as input_content,
        in_emb.embeddingVector     as input_embedding,
        in_emb.embeddingModel      as embedding_model,
        out_state.content          as output_content,
        out_emb.embeddingVector    as output_embedding
    """
    try:
        rows = db.execute(query, {"session_id": session_id})
    except Exception as exc:
        raise DatabaseError(f"Failed to get session IO embeddings: {exc}") from exc

    if rows:
        row = rows[0] if isinstance(rows[0], dict) else {}
        return {
            "input_content": row.get("input_content", ""),
            "input_embedding": row.get("input_embedding", []),
            "embedding_model": row.get("embedding_model", ""),
            "output_content": row.get("output_content", ""),
            "output_embedding": row.get("output_embedding", []),
        }

    return {
        "input_content": None,
        "input_embedding": None,
        "embedding_model": None,
        "output_content": None,
        "output_embedding": None,
    }


# ── get_session_data_for_ia_inference ─────────────────────────────────────────


def _reconstruction_communication_chain(
    agentic_blocks: List[Dict[str, Any]],
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Reconstruct a communication chain from ordered agentic blocks.

    Mirrors the static ``_reconstruction_communication_chain`` helper in
    *oxp-lib*.
    """
    if not agentic_blocks or len(agentic_blocks) < 2:
        return True, []

    sain = True
    chain: List[Dict[str, Any]] = []
    for i in range(len(agentic_blocks) - 1):
        current = agentic_blocks[i]
        nxt = agentic_blocks[i + 1]
        if current.get("output", "") != nxt.get("input", ""):
            sain = False
        edge: Dict[str, Any] = {
            "from": current.get("agent", ""),
            "to": nxt.get("agent", ""),
        }
        if current.get("agent", "") == "moderator":
            edge["query"] = current.get("output")
            if "output_embedding" in current:
                edge["query_embedding"] = current["output_embedding"]
        else:
            edge["response"] = current.get("output")
            if "output_embedding" in current:
                edge["response_embedding"] = current["output_embedding"]
        chain.append(edge)
    return sain, chain


def get_session_data_for_ia_inference(
    db: Connector,
    session_id: str,
    metric_name: str,
    embedding_model_name: str,
) -> Dict[str, Any]:
    """Return session data formatted for impact-assessment inference.

    Equivalent to ``Neo4jDBHandler.get_session_data_for_ia_inference`` in
    *oxp-lib*.

    Raises :class:`ValueError` when no data is found for the session.
    """

    query, params = dal_queries.build_session_data_for_ia_inference_query(
        session_id, metric_name, embedding_model_name
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get session data for IA inference: {exc}"
        ) from exc

    if not rows:
        raise ValueError(f"No session data found for session_id='{session_id}'")
    if len(rows) < 1:
        raise ValueError(f"No session data found for session_id='{session_id}'")
    row = rows[0]
    agentic_blocks: List[Dict[str, Any]] = row.get("Triples") or []
    sain, chain = _reconstruction_communication_chain(agentic_blocks)

    raw_metric = row.get("RawMetric")
    try:
        metric_value = float(raw_metric)
    except (TypeError, ValueError):
        metric_value = float(json.loads(raw_metric)["value"])

    question = None
    question_embedding = None
    if agentic_blocks and isinstance(agentic_blocks[0], dict):
        question = agentic_blocks[0].get("input")
        question_embedding = agentic_blocks[0].get("input_embedding")

    return {
        "session_id": row.get("SessionID"),
        metric_name: metric_value,
        "question": question,
        "question_embedding": question_embedding,
        "sain": sain,
        "communication_chain": chain,
    }


# ── ingest_impact_assessment_results ─────────────────────────────────────────


def ingest_impact_assessment_results(
    db: Connector,
    impact_assessment_results: List[Dict[str, Any]],
) -> None:
    """Ingest ImpactAssessment nodes and link each to its session.

    Equivalent to ``Neo4jDBHandler.ingest_impact_assessment_results`` in
    *oxp-lib*.

    Parameters
    ----------
    impact_assessment_results:
        List of dicts in ``ImpactAssessmentNode.to_dict()`` format.
    """
    for result in impact_assessment_results:
        label: str = result.get("label", "ImpactAssessment")
        props: Dict[str, Any] = result.get("properties", {})
        _ingest_node(db, label, props)
        session_id: str = props.get("sessionId", "")
        if session_id:
            _create_rel(
                db,
                "Session",
                ["sessionId"],
                [session_id],
                label,
                ["id"],
                [props["id"]],
                "hasImpactAssessment",
            )


def ingest_waste_estimation_results(
    db: Connector,
    waste_estimation_results: List[Dict[str, Any]],
) -> None:
    """Ingest waste estimation nodes and link each to its session."""
    for result in waste_estimation_results:
        label: str = result.get("label", "WasteEstimation")
        props: Dict[str, Any] = result.get("properties", {})
        _ingest_node(db=db, label=label, properties=props)
        session_id: str = props.get("sessionId", "")
        if session_id:
            _create_rel(
                db=db,
                from_label="Session",
                from_id_labels=["sessionId"],
                from_id_values=[session_id],
                to_label=label,
                to_id_labels=["id"],
                to_id_values=[props["id"]],
                relationship="hasWasteEstimationReport",
            )


# ── get_all_mas_metric_pairs ──────────────────────────────────────────────────


def get_all_mas_metric_pairs(db: Connector) -> List[Dict[str, Any]]:
    """Return all distinct ``{masId, metricName}`` pairs in the graph.

    Equivalent to ``Neo4jDBHandler.get_all_mas_metric_pairs`` in *oxp-lib*.
    """
    query, params = dal_queries.build_all_mas_metric_pairs_query()
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get MAS/metric pairs: {exc}") from exc
    return [r for r in rows if isinstance(r, dict)]


def get_all_application_ids(db: Connector) -> List[str]:
    """Return all distinct non-null MAS application identifiers."""
    query, params = dal_queries.build_all_application_ids_query()
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get MAS application ids: {exc}") from exc
    return [r["masId"] for r in rows if isinstance(r, dict) and r.get("masId")]


def get_all_mas_ids(db: Connector) -> List[str]:
    """Return all distinct non-null MAS identifiers."""
    query, params = dal_queries.build_all_mas_ids_query()
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get MAS ids: {exc}") from exc
    return [r["masId"] for r in rows if isinstance(r, dict) and r.get("masId")]


# ── get_impact_assessment_training_data ───────────────────────────────────────


def _get_session_ids_for_mas(db: Connector, mas_name: str) -> Set[str]:
    query, params = dal_queries.build_session_ids_for_mas_query(mas_name)
    rows = db.execute(query=query, params=params)
    res = set()
    for row in rows:
        session_id = row["SessionID"]
        res.add(session_id)
    del rows
    return res


def _get_impact_assessment_training_data_chunk(
    db: Connector, session_ids: list[str], embedding_model_name: str
) -> List[Dict[str, Any]]:
    if len(session_ids) > MAX_SESSIONS_FOR_SINGLE_QUERY:
        raise ValueError(
            f"`session_ids` list too long. Maximum supported is {MAX_SESSIONS_FOR_SINGLE_QUERY}"
        )
    elif len(session_ids) < 1:
        rows = []
    else:
        query, params = dal_queries.build_impact_assessment_training_data_query(
            session_ids=session_ids, embedding_model_name=embedding_model_name
        )
        try:
            rows = db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get impact assessment training data: {exc}"
            ) from exc

        if rows:
            if len(rows) > len(set([row["SessionID"] for row in rows])):
                raise ValueError("Found sessions with inconsistent data.")
    return rows


def _chunk_iterable(iterable: Iterable[Any], chunk_size: int) -> Iterable[List[Any]]:
    iterable_as_list = list(iterable)
    n_chunks, rest = divmod(len(iterable_as_list), chunk_size)
    if rest:
        n_chunks += 1
    for i in range(n_chunks):
        yield iterable_as_list[i * chunk_size : (i + 1) * chunk_size]


def get_impact_assessment_training_data(
    db: Connector,
    mas_name: str,
    embedding_model_name: str,
    excluded_session_ids: list[str] | None = None,
) -> List[Dict[str, Any]]:
    """Return formatted training data for the impact-assessment pipeline.

    Equivalent to ``Neo4jDBHandler.get_impact_assessment_training_data`` in
    *oxp-lib*.
    """
    if excluded_session_ids is None:
        excluded_session_ids = []

    session_ids = _get_session_ids_for_mas(db=db, mas_name=mas_name)
    session_ids = list(session_ids.difference(excluded_session_ids))
    logger.info(
        f"mas_name : {mas_name} - extracting impact assessment data for"
        f" {len(session_ids)} sessions"
    )
    rows = []
    for chunk in _chunk_iterable(
        iterable=session_ids, chunk_size=MAX_SESSIONS_FOR_SINGLE_QUERY
    ):
        addon = _get_impact_assessment_training_data_chunk(
            db=db, session_ids=chunk, embedding_model_name=embedding_model_name
        )
        rows += addon
        del addon
    records: List[Dict[str, Any]] = []
    for row in rows:
        agentic_blocks = row.get("Triples") or []
        sain, chain = _reconstruction_communication_chain(agentic_blocks=agentic_blocks)
        question = None
        question_embedding = None
        if (
            isinstance(agentic_blocks, list)
            and agentic_blocks
            and isinstance(agentic_blocks[0], dict)
        ):
            question = agentic_blocks[0].get("input")
            question_embedding = agentic_blocks[0].get("input_embedding")

        records.append(
            {
                "session_id": row.get("SessionID"),
                "AgenticBlocks": agentic_blocks,
                "question": question,
                "question_embedding": question_embedding,
                "sain": sain,
                "reconstructed_communication_chain": chain,
            }
        )
    return records


# ── get_analysis_data_for_semantic_group ──────────────────────────────────────


def get_analysis_data_for_semantic_group(
    db: Connector,
    group_id: str,
    group_hash: str = "",
    embedding_model: str = "",
    skip: int = 0,
    limit: int = 0,
) -> List[Dict[str, Any]]:
    """Return per-session analysis data for a semantic group.

    Equivalent to ``Neo4jDBHandler.get_analysis_data_for_semantic_group`` in
    *oxp-lib*.
    """
    query, params = dal_queries.build_analysis_data_for_semantic_group_query(
        group_id,
        group_hash,
        embedding_model,
        skip=skip,
        limit=limit,
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get analysis data for semantic group: {exc}"
        ) from exc

    result: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("session_id"):
            continue
        metrics_raw: List[Dict[str, Any]] = row.get("metrics") or []
        formatted_metrics = {
            m.get("metricName"): m.get("metricResult", m.get("value"))
            for m in metrics_raw
            if m.get("metricName")
        }
        result.append(
            {
                "session_id": row["session_id"],
                "input_content": row.get("input_content", ""),
                "input_embedding": row.get("input_embedding", []),
                "output_content": row.get("output_content", ""),
                "output_embedding": row.get("output_embedding", []),
                "metrics": formatted_metrics,
                "execution_graph": {
                    "nodes": row.get("graph_nodes", []),
                    "edges": row.get("graph_edges", []),
                },
            }
        )
    return result


# ── ingest_insights ───────────────────────────────────────────────────────────

_INSIGHT_SCOPE_TARGETS: Dict[str, Tuple[str, str]] = {
    "Session": ("Session", "sessionId"),
    "MAS": ("MAS", "masId"),
    "Agent": ("Agent", "agentName"),
    "SemanticGroup": ("SemanticGroup", "id"),
}


def ingest_insights(
    db: Connector,
    insights: List[Any],
) -> None:
    """Ingest Insight nodes and attach each to its target node.

    Equivalent to ``Neo4jDBHandler.ingest_insights`` in *oxp-lib*.

    Parameters
    ----------
    insights:
        List of ``oxp_ontology.models.nodes.insight.Insight`` instances,
        each with an ``id`` field set to its MERGE key. Each is verified
        against the bundled SHACL shapes (raises ``OntologyValidationError``
        on a mandatory-property violation) before being written.
    """
    current_ids_by_target_template: Dict[Tuple[str, str, str], set] = {}

    for insight in insights:
        verification = verify_kg_object(insight)
        if not verification.conforms:
            raise OntologyValidationError(verification)

        labels_value = insight.labels
        labels = (
            json.loads(labels_value)
            if isinstance(labels_value, str)
            else (labels_value or [])
        )

        label = "Insight"
        props: Dict[str, Any] = {
            "id": insight.id,
            "templateId": insight.templateId,
            "name": insight.name,
            "description": insight.description,
            "labels": labels,
            "scope": insight.scope,
            "priority": insight.priority,
            "targetNodeId": insight.targetNodeId,
            "createdAt": insight.createdAt,
        }
        _ingest_node(db, label, props)

        scope: str = props.get("scope") or ""
        target_node_id: str = props.get("targetNodeId") or ""
        template_id: str = props.get("templateId") or ""
        insight_id: str = props.get("id", "")

        if not scope or not target_node_id:
            logger.warning(
                "Skipping insight attachment for %s: scope=%r targetNodeId=%r",
                insight_id,
                scope,
                target_node_id,
            )
            continue

        target_config = _INSIGHT_SCOPE_TARGETS.get(scope)
        if target_config is None:
            logger.warning(
                "Skipping insight attachment for %s: unsupported scope %r",
                insight_id,
                scope,
            )
            continue

        target_label, target_id_field = target_config
        try:
            _create_rel(
                db,
                target_label,
                [target_id_field],
                [target_node_id],
                label,
                ["id"],
                [insight_id],
                "hasInsight",
            )
        except DatabaseError:
            logger.warning(
                "Skipping insight attachment for %s: no %s node with %s=%r",
                insight_id,
                target_label,
                target_id_field,
                target_node_id,
            )
            continue

        key = (scope, target_node_id, template_id)
        current_ids_by_target_template.setdefault(key, set()).add(insight_id)

    # clean up outdated insights that were not regenerated in this run
    for (
        scope,
        target_node_id,
        template_id,
    ), current_ids in current_ids_by_target_template.items():
        target_config = _INSIGHT_SCOPE_TARGETS.get(scope)
        if target_config is None:
            continue
        target_label, target_id_field = target_config
        cleanup_query, cleanup_params = (
            dal_queries.build_cleanup_outdated_insights_query(
                target_label=target_label,
                target_id_field=target_id_field,
                target_node_id=target_node_id,
                template_id=template_id,
                current_ids=list(current_ids),
            )
        )
        try:
            db.execute(cleanup_query, cleanup_params)
        except Exception as exc:
            raise DatabaseError(f"Failed to clean up outdated insights: {exc}") from exc


def ingest_embeddings(db: Connector, embeddings: List[Dict[str, Any]]) -> None:
    """Ingest Embedding nodes and attach each to the State it represents.

    Each element of *embeddings* is a flat dict produced by
    ``embedding_worker.wrapper.EmbeddingWrapper`` (``SessionId``, ``SpanId``
    -- actually the source State's own ``id``, for both the "transition"
    layer's individual states and the "session" layer's
    ``hasInitialState``/``hasFinalState`` states -- ``EmbeddingModel``,
    ``Embedding``). Only ``embeddingVector``/``embeddingModel``/
    ``embeddingDimension`` are real ``Embedding`` properties; everything
    else in the source dict (``AgentId``, ``TraceId``, ``EntityType``,
    ``Timestamp``) has no ontology home and is dropped rather than stored
    as an undeclared property.

    One relationship per embedding -- ``Embedding-[:represents]->State``,
    keyed by the *State*'s own id -- covers both layers: a "session"-layer
    record's id is already the session's own hasInitialState/hasFinalState
    target, so linking it as a State is exactly what
    ``get_embedding_by_session_id`` reads back via that same traversal; a
    separate Session-level relationship would be redundant for that record
    and outright wrong for "transition"-layer records (which don't represent
    the session's own boundary state at all).
    """
    if not embeddings:
        return

    embedding_nodes = []
    state_rels = []

    for node in embeddings:
        session_id: str = node.get("SessionId", "")
        span_id: str = node.get("SpanId", "")
        if isinstance(span_id, list):
            span_id = span_id[0] if span_id else ""
        embedding_model: str = node.get("EmbeddingModel", "")
        embedding = node.get("Embedding", [])

        uuid = f"{session_id}_{span_id}_{embedding_model}"

        embedding_nodes.append(
            {
                "id": uuid,
                "embeddingVector": embedding,
                "embeddingModel": embedding_model,
                "embeddingDimension": len(embedding) if embedding else 0,
            }
        )

        if span_id:
            state_rels.append(
                {
                    "session_id": session_id,
                    "span_id": span_id,
                    "embedding_id": uuid,
                }
            )

    # Batch ingest all Embedding nodes
    if embedding_nodes:
        try:
            query = """
            UNWIND $nodes AS node
            MERGE (e:Embedding {id: node.id})
            SET e += node
            """
            db.execute(query, {"nodes": embedding_nodes})
        except Exception as exc:
            raise DatabaseError(
                f"Failed to ingest Embedding nodes in batch: {exc}"
            ) from exc

    # Batch create Embedding→represents→State relationships
    if state_rels:
        try:
            query = """
            UNWIND $rels AS rel
            MATCH (s:State {sessionId: rel.session_id, id: rel.span_id})
            MATCH (e:Embedding {id: rel.embedding_id})
            MERGE (e)-[:represents]->(s)
            """
            db.execute(query, {"rels": state_rels})
        except Exception as exc:
            raise DatabaseError(
                f"Failed to create Embedding-represents-State relationships in batch: {exc}"
            ) from exc


def retrieve_raw_waste_estimation_data(
    db: Connector,
    embedding_model_name: str,
    mas_name: Optional[str] = None,
    session_ids: Optional[List[str]] = None,
    excluded_session_ids: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
    if session_ids is None:
        if mas_name is None:
            raise ValueError("mas_name must be provided if no session ids are provided")
        if excluded_session_ids is None:
            excluded_session_ids = []
        session_ids = _get_session_ids_for_mas(db=db, mas_name=mas_name)
        session_ids = list(session_ids.difference(excluded_session_ids))
        logger.info(
            f"mas_name : {mas_name} - extracting waste estimation data for"
            f" {len(session_ids)} sessions"
        )
    res = []
    if session_ids:
        for session_ids_chunk in _chunk_iterable(
            iterable=session_ids, chunk_size=MAX_SESSIONS_FOR_SINGLE_QUERY
        ):
            addon = retrieve_raw_waste_estimation_data_for_sessions(
                db=db,
                session_ids=session_ids_chunk,
                embedding_model_name=embedding_model_name,
            )
            res += addon
            del addon
    return res


def retrieve_raw_waste_estimation_data_for_sessions(
    db: Connector, session_ids: list[str], embedding_model_name: str
) -> list[dict[str, Any]]:
    """Retrieve the first transition input and embedding per session from Neo4j."""
    if len(session_ids) > MAX_SESSIONS_FOR_SINGLE_QUERY:
        raise ValueError(
            f"`session_ids` list too long. Maximum supported is {MAX_SESSIONS_FOR_SINGLE_QUERY}"
        )
    elif len(session_ids) < 1:
        rows = []
    else:
        query, params = dal_queries.build_waste_estimation_data_query(
            session_ids=session_ids, embedding_model_name=embedding_model_name
        )
        try:
            rows = db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get impact assessment training data: {exc}"
            ) from exc
        if rows:
            if len(rows) > len(set([row["SessionID"] for row in rows])):
                raise ValueError("Found sessions with inconsistent data.")
    return rows


def get_waste_estimation_data(
    db: Connector,
    embedding_model_name: str,
    mas_name: Optional[str] = None,
    session_ids: Optional[List[str]] = None,
    excluded_session_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    rows = retrieve_raw_waste_estimation_data(
        db=db,
        embedding_model_name=embedding_model_name,
        mas_name=mas_name,
        session_ids=session_ids,
        excluded_session_ids=excluded_session_ids,
    )
    return [
        {
            "session_id": row["SessionID"],
            "question": row["question"],
            "question_embedding": row["question_embedding"],
        }
        for row in rows
    ]


def get_wr_session_ids(
    db: Connector,
    application_id: Optional[str] = None,
    excluded_session_ids: Optional[List[str]] = None,
) -> List[str]:
    """Get session IDs for wasted resources training, optionally filtered by application.

    Updated for new KG schema: uses Session.appName instead of MAS relationships.
    """
    query, params = dal_queries.build_wr_session_ids(
        application_id=application_id, excluded_session_ids=excluded_session_ids
    )
    rows = db.execute(query, params)
    return [r["session_id"] for r in rows]


def get_wr_agent_tool_baseline_by_session_ids(
    db: Connector, session_ids: List[str]
) -> List[Dict[str, Any]]:
    query, params = dal_queries.build_wr_agent_tool_baseline_by_session_ids_query(
        session_ids=session_ids,
    )
    return db.execute(query=query, params=params)


def get_wr_tool_calls_by_session(db: Connector, sid: str) -> List[Dict[str, Any]]:
    query, params = dal_queries.build_wr_tool_calls_by_session_query(sid=sid)
    return db.execute(query=query, params=params)


def get_wr_agent_calls_by_session(db: Connector, sid: str) -> List[Dict[str, Any]]:
    query, params = dal_queries.build_wr_agent_calls_by_session_query(sid=sid)
    return db.execute(query=query, params=params)


def get_wr_agent_tool_counts_by_session(
    db: Connector, sid: str
) -> List[Dict[str, Any]]:
    query, params = dal_queries.build_wr_agent_tool_counts_by_session_query(sid=sid)
    return db.execute(query=query, params=params)


def get_wr_llm_calls_via_edges(db: Connector, sid: str) -> List[Dict[str, Any]]:
    query, params = dal_queries.build_wr_llm_calls_via_edges_query(sid=sid)
    return db.execute(query=query, params=params)


def get_wr_llm_calls_by_session_property(
    db: Connector, sid: str
) -> List[Dict[str, Any]]:
    query, params = dal_queries.build_wr_llm_calls_by_session_property_query(sid=sid)
    return db.execute(query=query, params=params)


def get_wr_session_metrics(db: Connector, sid: str) -> List[Dict[str, Any]]:
    query, params = dal_queries.build_wr_session_metrics_query(sid=sid)
    return db.execute(query=query, params=params)


def ingest_wasted_resources_inference(
    db: Connector,
    session_id: str,
    predictions: Dict[str, float],
    metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    requested_cost_target: Optional[str] = None,
    requested_quality_targets: Optional[List[str]] = None,
    resolved_targets: Optional[List[str]] = None,
    model_alias: Optional[str] = None,
    score_formula: Optional[str] = None,
    epsilon: Optional[float] = None,
    top_k: Optional[int] = None,
) -> None:
    rows: List[Dict[str, Any]] = []
    for target_name, value in predictions.items():
        node_id = f"{session_id}_{target_name}"
        target_metadata = (metadata or {}).get(target_name, {})
        rows.append(
            {
                "id": node_id,
                "sessionId": session_id,
                "targetName": target_name,
                "prediction": value,
                "metadata": json.dumps(target_metadata),
                "requestedCostTarget": requested_cost_target,
                "requestedQualityTargets": json.dumps(requested_quality_targets or []),
                "resolvedTargets": json.dumps(resolved_targets or []),
                "modelAlias": model_alias,
                "scoreFormula": score_formula,
                "epsilon": epsilon,
                "topK": top_k,
            }
        )

    if rows:
        query, params = dal_queries.build_ingest_wasted_resources_inference_nodes_query(
            rows
        )
        db.execute(query=query, params=params)

        query, params = (
            dal_queries.build_link_wasted_resources_inference_to_session_query(
                session_id=session_id,
                node_ids=[row["id"] for row in rows],
            )
        )
        db.execute(query=query, params=params)


def ingest_wasted_resources_feature_scores(
    db: Connector,
    session_id: str,
    feature_scores_by_quality_target: Dict[str, List[Dict[str, Any]]],
    cost_target: Optional[str] = None,
    model_alias: Optional[str] = None,
    score_formula: Optional[str] = None,
    epsilon: Optional[float] = None,
    top_k: Optional[int] = None,
) -> None:
    rows: List[Dict[str, Any]] = []
    for quality_target, feature_scores in feature_scores_by_quality_target.items():
        for rank, feature_score in enumerate(feature_scores, start=1):
            feature_name = str(feature_score.get("feature", ""))
            score_value = float(feature_score.get("score", 0.0))
            node_id = f"{session_id}_{quality_target}_{rank}_{feature_name}"
            rows.append(
                {
                    "id": node_id,
                    "sessionId": session_id,
                    "qualityTarget": quality_target,
                    "featureName": feature_name,
                    "score": score_value,
                    "rank": rank,
                    "costTarget": cost_target,
                    "modelAlias": model_alias,
                    "scoreFormula": score_formula,
                    "epsilon": epsilon,
                    "topK": top_k,
                }
            )

    if rows:
        query, params = (
            dal_queries.build_ingest_wasted_resources_feature_scores_nodes_query(rows)
        )
        db.execute(query=query, params=params)

        query, params = (
            dal_queries.build_link_wasted_resources_feature_scores_to_session_query(
                session_id=session_id,
                node_ids=[row["id"] for row in rows],
            )
        )
        db.execute(query=query, params=params)
