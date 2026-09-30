#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Ontology Hierarchy Loader

Dynamically loads the MAS Class Hierarchy from the ontology package.
Ensures Single Source of Truth via confirmed Python dependency.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def load_ontology_hierarchy() -> dict:
    """
    Load MAS ontology class hierarchy.

    Returns:
        dict: Mapping of class names to list of descendant classes
              Example: {"ExecutionElement": ["Session", "AgentCall", "LLMCall", ...]}
    """
    import rdflib

    try:
        from oxp_ontology import load_graph
    except ImportError:
        logger.error("ontology package not found. Install it via pip/uv.")
        return {}

    # 1. Load Ontology (Delegated to package)
    try:
        g = load_graph("mas-ontology")
    except Exception as e:
        logger.error(f"Failed to load/parse ontology from package: {e}")
        return {}

    # 2. Build Subclass Map
    subclass_map = {}
    for s, p, o in g.triples((None, rdflib.RDFS.subClassOf, None)):
        # Extract simple names (fragment) from URIs
        if "#" in str(s):
            child = str(s).split("#")[-1]
        else:
            continue

        if "#" in str(o):
            parent = str(o).split("#")[-1]
        else:
            continue

        if parent not in subclass_map:
            subclass_map[parent] = []
        subclass_map[parent].append(child)

    # 3. Flatten Hierarchy (Class -> List of all Descendants)
    hierarchy = {}

    def get_descendants(node, visiting: set | None = None):
        """DFS over the subclass graph with cycle detection via a visiting set."""
        if visiting is None:
            visiting = set()
        if node in visiting:
            logger.debug(
                "Ontology cycle detected at '%s' — skipping to avoid infinite recursion",
                node,
            )
            return set()
        visiting = visiting | {node}  # immutable copy so siblings are unaffected
        desc = {node}
        for child in subclass_map.get(node, []):
            desc.update(get_descendants(child, visiting))
        return desc

    # Compute for all known keys in map
    roots = list(subclass_map.keys()) + [
        "ExecutionElement",
        "Session",
        "AgentCall",
        "TaskCall",
        "LLMCall",
        "ToolCall",
    ]

    for r in roots:
        hierarchy[r] = list(get_descendants(r))

    return hierarchy
