#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Structural comparison and JSON I/O for KG documents.

This module provides the same lightweight comparison surface used by the broader
library-kg implementation, but keeps the logic self-contained in norm so the
standalone package can validate and compare generated graphs without importing
repo-specific orchestration code.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "KGCompareResult",
    "compare_kg",
    "check_agent_coverage",
    "check_node_distribution",
    "check_edge_distribution",
    "check_call_depth",
    "check_tool_coverage",
    "check_delegation_topology",
    "check_element_diff",
    "read_kg_json",
    "write_kg_json",
]


@dataclass
class KGCompareResult:
    """Result of a KG structural comparison."""

    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    reference_stats: Dict[str, Any] = field(default_factory=dict)
    candidate_stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "summary": self.summary,
            "reference_stats": self.reference_stats,
            "candidate_stats": self.candidate_stats,
        }


def _node_type(node: Dict[str, Any]) -> str:
    for key in ("node_type", "nodeType", "type"):
        val = node.get(key)
        if val:
            return str(val)
    return "unknown"


def _edge_type(edge: Dict[str, Any]) -> str:
    for key in ("edge_type", "edgeType", "type"):
        val = edge.get(key)
        if val:
            return str(val)
    return "unknown"


def _edge_source(edge: Dict[str, Any]) -> str:
    return str(edge.get("from_id") or edge.get("source") or edge.get("from") or "")


def _edge_target(edge: Dict[str, Any]) -> str:
    return str(edge.get("to_id") or edge.get("target") or edge.get("to") or "")


_CONTAINMENT_EDGE_TYPES = (
    "hasMASCall",
    "hasAgentCall",
    "hasToolCall",
    "hasLLMCall",
    "hasProcessingCall",
)


def _agent_ids(nodes: Iterable[Dict[str, Any]]) -> Set[str]:
    """Return the identity (``id``) of every structural ``Agent`` node.

    The ontology has no separate ``agentId`` field — ``Agent.id`` is an
    agent's sole identity now (see norm.ioa_observe's ``agent:<name>``
    scoping).
    """
    return {str(n["id"]) for n in nodes if _node_type(n) == "Agent" and n.get("id")}


def _tool_names(nodes: Iterable[Dict[str, Any]]) -> Set[str]:
    """Return the ``name`` of every structural ``Tool`` node.

    ``ToolCall`` carries no ``toolName`` of its own — the tool identity lives
    on the ``Tool`` node it ``executesTool``.
    """
    return {str(n["name"]) for n in nodes if _node_type(n) == "Tool" and n.get("name")}


def _delegation_pairs(
    edges: Iterable[Dict[str, Any]], nodes: Iterable[Dict[str, Any]]
) -> Set[Tuple[str, str]]:
    """Return (calling agent id, called agent id) pairs from ``executesAgent`` edges.

    Under the flat hierarchy (AgentCall only nests under MASCall via
    ``hasAgentCall`` — an AgentCall cannot directly contain another
    AgentCall), true cross-agent delegation isn't representable, so this
    naturally returns an empty set; kept for schema completeness rather than
    removed.
    """
    del nodes
    pairs: Set[Tuple[str, str]] = set()
    for e in edges:
        if _edge_type(e) == "executesAgent":
            src, tgt = _edge_source(e), _edge_target(e)
            if src and tgt and src != tgt:
                pairs.add((src, tgt))
    return pairs


def _max_nesting_depth(nodes: Iterable[Dict[str, Any]], edges: Iterable[Dict[str, Any]]) -> int:
    children: Dict[str, List[str]] = {}
    node_ids: Set[str] = {n.get("id", "") for n in nodes}
    for e in edges:
        if _edge_type(e) in _CONTAINMENT_EDGE_TYPES:
            src, tgt = _edge_source(e), _edge_target(e)
            if src in node_ids and tgt in node_ids:
                children.setdefault(src, []).append(tgt)

    roots = node_ids - {t for kids in children.values() for t in kids}
    if not roots:
        return 0

    max_d = 0
    stack = [(r, 0) for r in roots]
    while stack:
        nid, depth = stack.pop()
        max_d = max(max_d, depth)
        for child in children.get(nid, []):
            stack.append((child, depth + 1))
    return max_d


def _stable_node_key(node: Dict[str, Any]) -> str:
    return f"{_node_type(node)}|{node.get('id', '')}"


def check_agent_coverage(
    candidate_nodes: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_agents = _agent_ids(reference_nodes)
    cand_agents = _agent_ids(candidate_nodes)
    missing = ref_agents - cand_agents
    extra = cand_agents - ref_agents
    return {
        "name": "agent_coverage",
        "passed": len(missing) == 0,
        "reference_agents": sorted(ref_agents),
        "candidate_agents": sorted(cand_agents),
        "missing": sorted(missing),
        "extra": sorted(extra),
    }


def check_node_distribution(
    candidate_nodes: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_dist = Counter(_node_type(n) for n in reference_nodes)
    cand_dist = Counter(_node_type(n) for n in candidate_nodes)
    deficits = {
        ntype: (ref_dist[ntype] - cand_dist.get(ntype, 0))
        for ntype in ref_dist
        if cand_dist.get(ntype, 0) < ref_dist[ntype]
    }
    return {
        "name": "node_distribution",
        "passed": len(deficits) == 0,
        "reference": dict(ref_dist),
        "candidate": dict(cand_dist),
        "deficits": deficits,
    }


def check_edge_distribution(
    candidate_edges: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_dist = Counter(_edge_type(e) for e in reference_edges)
    cand_dist = Counter(_edge_type(e) for e in candidate_edges)
    deficits = {
        etype: (ref_dist[etype] - cand_dist.get(etype, 0))
        for etype in ref_dist
        if cand_dist.get(etype, 0) < ref_dist[etype]
    }
    return {
        "name": "edge_distribution",
        "passed": len(deficits) == 0,
        "reference": dict(ref_dist),
        "candidate": dict(cand_dist),
        "deficits": deficits,
    }


def check_call_depth(
    candidate_nodes: List[Dict[str, Any]],
    candidate_edges: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_depth = _max_nesting_depth(reference_nodes, reference_edges)
    cand_depth = _max_nesting_depth(candidate_nodes, candidate_edges)
    return {
        "name": "call_depth",
        "passed": cand_depth >= ref_depth,
        "reference_depth": ref_depth,
        "candidate_depth": cand_depth,
    }


def check_tool_coverage(
    candidate_nodes: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_tools = _tool_names(reference_nodes)
    cand_tools = _tool_names(candidate_nodes)
    missing = ref_tools - cand_tools
    return {
        "name": "tool_coverage",
        "passed": len(missing) == 0,
        "reference_tools": sorted(ref_tools),
        "candidate_tools": sorted(cand_tools),
        "missing": sorted(missing),
    }


def check_delegation_topology(
    candidate_nodes: List[Dict[str, Any]],
    candidate_edges: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_pairs = _delegation_pairs(reference_edges, reference_nodes)
    cand_pairs = _delegation_pairs(candidate_edges, candidate_nodes)
    missing = ref_pairs - cand_pairs
    return {
        "name": "delegation_topology",
        "passed": len(missing) == 0,
        "reference": sorted(f"{s}->{t}" for s, t in ref_pairs),
        "candidate": sorted(f"{s}->{t}" for s, t in cand_pairs),
        "missing": sorted(f"{s}->{t}" for s, t in missing),
    }


def _element_level_diff(
    candidate_nodes: List[Dict[str, Any]],
    candidate_edges: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_node_keys = Counter(_stable_node_key(n) for n in reference_nodes)
    cand_node_keys = Counter(_stable_node_key(n) for n in candidate_nodes)
    missing_nodes = sorted((ref_node_keys - cand_node_keys).keys())
    spurious_nodes = sorted((cand_node_keys - ref_node_keys).keys())

    def _edge_key(edge: Dict[str, Any]) -> str:
        return f"{_edge_type(edge)}|{_edge_source(edge)}|{_edge_target(edge)}"

    ref_edge_keys = Counter(_edge_key(e) for e in reference_edges)
    cand_edge_keys = Counter(_edge_key(e) for e in candidate_edges)
    missing_edges = sorted((ref_edge_keys - cand_edge_keys).keys())
    spurious_edges = sorted((cand_edge_keys - ref_edge_keys).keys())
    identical = (
        not missing_nodes and not spurious_nodes and not missing_edges and not spurious_edges
    )
    return {
        "name": "element_level_diff",
        "passed": identical,
        "missing_nodes": missing_nodes,
        "spurious_nodes": spurious_nodes,
        "missing_edges": missing_edges,
        "spurious_edges": spurious_edges,
    }


def check_element_diff(
    candidate_nodes: List[Dict[str, Any]],
    candidate_edges: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return _element_level_diff(candidate_nodes, candidate_edges, reference_nodes, reference_edges)


def compare_kg(
    candidate: Dict[str, Any], reference: Dict[str, Any], *, strict: bool = False
) -> KGCompareResult:
    cand_nodes = candidate.get("nodes") or []
    cand_edges = candidate.get("edges") or []
    ref_nodes = reference.get("nodes") or []
    ref_edges = reference.get("edges") or []

    checks: List[Dict[str, Any]] = [
        check_agent_coverage(cand_nodes, ref_nodes),
        check_node_distribution(cand_nodes, ref_nodes),
        check_edge_distribution(cand_edges, ref_edges),
        check_call_depth(cand_nodes, cand_edges, ref_nodes, ref_edges),
        check_tool_coverage(cand_nodes, ref_nodes),
        check_delegation_topology(cand_nodes, cand_edges, ref_nodes, ref_edges),
        check_element_diff(cand_nodes, cand_edges, ref_nodes, ref_edges),
    ]

    structural_checks = [c for c in checks if c["name"] != "element_level_diff"]
    all_passed = all(c["passed"] for c in (checks if strict else structural_checks))

    summary = {
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c["passed"]),
        "failed": sum(1 for c in checks if not c["passed"]),
    }
    ref_agents = _agent_ids(ref_nodes)
    cand_agents = _agent_ids(cand_nodes)

    return KGCompareResult(
        passed=all_passed,
        checks=checks,
        summary=summary,
        reference_stats={
            "nodes": len(ref_nodes),
            "edges": len(ref_edges),
            "agents": sorted(ref_agents),
        },
        candidate_stats={
            "nodes": len(cand_nodes),
            "edges": len(cand_edges),
            "agents": sorted(cand_agents),
        },
    )


def read_kg_json(path: str | Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError("KG JSON document must deserialize to a dict")
    return {
        "nodes": list(data.get("nodes") or []),
        "edges": list(data.get("edges") or []),
    }


def write_kg_json(doc: Dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "nodes": list(doc.get("nodes") or []),
        "edges": list(doc.get("edges") or []),
    }
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return out
