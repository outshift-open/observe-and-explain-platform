#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Normalize an OTel export JSONL trace into (nodes, edges) -- to files or Neo4j.

Just the normalization step -- no SHACL/verify_kg.

Usage:
    python scripts/generate_kg.py data/otel_traces_export_clean.jsonl \\
        --nodes-out /tmp/nodes.json --edges-out /tmp/edges.json

    python scripts/generate_kg.py data/otel_traces_export_clean.jsonl --neo4j \\
        --neo4j-uri bolt://localhost:7687 \\
        --neo4j-user neo4j --neo4j-password change-me

Neo4j push requires: pip install neo4j
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _is_safe_label(value: str) -> bool:
    """Every current node_type/edge_type is a plain identifier; reject anything else."""
    return value.isidentifier()


def push_to_neo4j(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    uri: str,
    user: str,
    password: str,
    database: str = "neo4j",
) -> None:
    """MERGE every node (labelled by node_type, keyed by id) and edge into Neo4j."""
    from neo4j import GraphDatabase

    id_to_type: dict[str, str] = {}
    indexed_types: set[str] = set()

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            for node in nodes:
                node_type = str(node.get("node_type") or "")
                node_id = str(node.get("id") or "")
                if not node_type or not node_id:
                    continue
                if not _is_safe_label(node_type):
                    raise ValueError(f"Unsafe node_type for Cypher label: {node_type!r}")
                id_to_type[node_id] = node_type

                if node_type not in indexed_types:
                    session.run(
                        f"CREATE INDEX {node_type.lower()}_id IF NOT EXISTS "
                        f"FOR (n:{node_type}) ON (n.id)"
                    )
                    indexed_types.add(node_type)

                props = {k: v for k, v in node.items() if k != "node_type"}
                session.run(
                    f"MERGE (n:{node_type} {{id: $id}}) SET n += $props",
                    id=node_id,
                    props=props,
                )

            skipped = 0
            for edge in edges:
                edge_type = str(edge.get("edge_type") or "")
                from_id = str(edge.get("from_id") or "")
                to_id = str(edge.get("to_id") or "")
                if not edge_type or not from_id or not to_id:
                    continue
                if not _is_safe_label(edge_type):
                    raise ValueError(f"Unsafe edge_type for Cypher relationship: {edge_type!r}")
                from_type = id_to_type.get(from_id)
                to_type = id_to_type.get(to_id)
                if from_type is None or to_type is None:
                    # Endpoint not in this batch's nodes -- skip rather than
                    # merge against an untyped placeholder node.
                    skipped += 1
                    continue
                session.run(
                    f"MATCH (a:{from_type} {{id: $from_id}}), (b:{to_type} {{id: $to_id}}) "
                    f"MERGE (a)-[:{edge_type}]->(b)",
                    from_id=from_id,
                    to_id=to_id,
                )
            if skipped:
                logger.warning("Skipped %d edges with an endpoint outside this batch", skipped)
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to an OTel export JSONL file")
    parser.add_argument("--nodes-out", type=Path, default=Path("/tmp/nodes.json"))
    parser.add_argument("--edges-out", type=Path, default=Path("/tmp/edges.json"))
    parser.add_argument(
        "--neo4j",
        action="store_true",
        help="Push to Neo4j instead of writing --nodes-out/--edges-out",
    )
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password")
    parser.add_argument("--neo4j-database", default="neo4j")
    args = parser.parse_args()

    if args.neo4j and not args.neo4j_password:
        parser.error("--neo4j-password is required with --neo4j")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from norm import load_otel_export, normalize

    spans = load_otel_export(args.input)
    nodes, edges = normalize(spans)
    logger.info("%d spans -> %d nodes, %d edges", len(spans), len(nodes), len(edges))

    if args.neo4j:
        push_to_neo4j(
            nodes,
            edges,
            uri=args.neo4j_uri,
            user=args.neo4j_user,
            password=args.neo4j_password,
            database=args.neo4j_database,
        )
        logger.info("Pushed to Neo4j at %s", args.neo4j_uri)
    else:
        args.nodes_out.write_text(json.dumps(nodes, indent=2), encoding="utf-8")
        args.edges_out.write_text(json.dumps(edges, indent=2), encoding="utf-8")
        logger.info("Wrote %s and %s", args.nodes_out, args.edges_out)


if __name__ == "__main__":
    main()
