#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

"""Writes one span's KG delta straight to Neo4j, updating nodes in place."""

import logging
import json
from collections.abc import Sequence
from typing import Any

from norm import StreamDelta

logger = logging.getLogger(__name__)

# Node types merged on `name` (unique constraint) instead of `id`; mirrors oxp.client.dal.
NAME_KEYED_NODE_TYPES = frozenset({"LLM"})
# Set when a node is first created and never changed afterwards.
IMMUTABLE_PROPS = frozenset({"startTime", "endTime"})
_NON_PROPS = frozenset({"node_type"})
_EDGE_NON_PROPS = frozenset({"edge_type", "from_id", "from_type", "to_id", "to_type"})


def _safe(identifier: str) -> str:
    from oxp.client.dal import _is_safe_cypher_identifier

    if not _is_safe_cypher_identifier(identifier):
        raise ValueError(f"Unsafe Cypher identifier: {identifier!r}")
    return identifier


def _props(values: dict[str, Any], skip: frozenset[str]) -> dict[str, Any]:
    from oxp.client.dal import _neo4j_props

    return _neo4j_props({k: v for k, v in values.items() if k not in skip})


def _decode(value: Any) -> Any:
    """Undo ``oxp.client.dal._neo4j_props``'s JSON-prefix encoding of dict/list values."""
    from oxp.client.dal import _JSON_PREFIX

    if isinstance(value, str) and value.startswith(_JSON_PREFIX):
        return json.loads(value[len(_JSON_PREFIX) :])
    return value


def _node(label: str, props: dict[str, Any]) -> dict[str, Any]:
    return {**{k: _decode(v) for k, v in props.items()}, "node_type": label}


class Neo4jStore:
    """Neo4j implementation of norm's ``GraphReader``, plus writer for its deltas."""

    def __init__(self, connector: Any):
        self._db = connector

    def load(
        self, session_id: str, node_ids: Sequence[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Read the span's session subgraph and the nodes it touches from Neo4j."""
        params = {"sid": session_id, "ids": list(node_ids)}
        nodes: dict[tuple[str, str], dict[str, Any]] = {}
        for row in self._db.execute(
            "MATCH (n) WHERE n.sessionId = $sid OR n.id IN $ids "
            "RETURN labels(n)[0] AS label, properties(n) AS props",
            params,
        ):
            node = _node(row["label"], row["props"])
            nodes[(node["node_type"], node["id"])] = node

        edges: list[dict[str, Any]] = []
        for row in self._db.execute(
            "MATCH (a)-[r]->(b) "
            "WHERE a.sessionId = $sid OR b.sessionId = $sid "
            "OR (a.id IN $ids AND b.id IN $ids) "
            "RETURN type(r) AS edge_type, a.id AS from_id, b.id AS to_id, "
            "labels(a)[0] AS from_label, properties(a) AS from_props, "
            "labels(b)[0] AS to_label, properties(b) AS to_props",
            params,
        ):
            edges.append({"edge_type": row["edge_type"], "from_id": row["from_id"], "to_id": row["to_id"]})
            for label, props in ((row["from_label"], row["from_props"]), (row["to_label"], row["to_props"])):
                node = _node(label, props)
                nodes.setdefault((node["node_type"], node["id"]), node)
        return list(nodes.values()), edges

    def apply(self, delta: StreamDelta) -> None:
        """Apply a delta: removals first, then nodes, then edges (endpoints must exist)."""
        for edge in delta.removed_edges:
            self._delete_edge(edge)
        for node in delta.removed_nodes:
            self._delete_node(node)
        for node in delta.nodes:
            self._upsert_node(node)
        for edge in delta.edges:
            self._upsert_edge(edge)

    def _upsert_node(self, node: dict[str, Any]) -> None:
        node_type = _safe(str(node["node_type"]))
        props = _props(node, _NON_PROPS)
        on_match = {k: v for k, v in props.items() if k not in IMMUTABLE_PROPS}
        key = "name" if node_type in NAME_KEYED_NODE_TYPES else "id"
        self._db.execute_command(
            f"MERGE (n:{node_type} {{{key}: $key}}) "
            "ON CREATE SET n += $props ON MATCH SET n += $on_match",
            {"key": props[key], "props": props, "on_match": on_match},
        )

    def _upsert_edge(self, edge: dict[str, Any]) -> None:
        edge_type = _safe(str(edge["edge_type"]))
        from_type = _safe(str(edge["from_type"]))
        to_type = _safe(str(edge["to_type"]))
        # MERGE (not MATCH) the endpoints: one may not exist yet (e.g. usesLLM before
        # the agent span), and is then created as a partial node its own span fills in.
        self._db.execute_command(
            f"MERGE (a:{from_type} {{id: $from_id}}) MERGE (b:{to_type} {{id: $to_id}}) "
            f"MERGE (a)-[r:{edge_type}]->(b) SET r += $props",
            {
                "from_id": edge["from_id"],
                "to_id": edge["to_id"],
                "props": _props(edge, _EDGE_NON_PROPS),
            },
        )

    def _delete_edge(self, edge: dict[str, Any]) -> None:
        edge_type = _safe(str(edge["edge_type"]))
        from_type = _safe(str(edge["from_type"]))
        to_type = _safe(str(edge["to_type"]))
        self._db.execute_command(
            f"MATCH (a:{from_type} {{id: $from_id}})-[r:{edge_type}]->(b:{to_type} {{id: $to_id}}) DELETE r",
            {"from_id": edge["from_id"], "to_id": edge["to_id"]},
        )

    def _delete_node(self, node: dict[str, Any]) -> None:
        node_type = _safe(str(node["node_type"]))
        self._db.execute_command(
            f"MATCH (n:{node_type} {{id: $id}}) DETACH DELETE n",
            {"id": node["id"]},
        )
