#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stateless, span-at-a-time normalization against a graph database.

``build_kg`` needs the whole span array. ``StreamNormalizer.process`` takes a
single span and keeps nothing between calls: the graph already stored in the
database *is* the state. For each span it

1. loads what it needs from the database through a ``GraphReader`` (the
   span's session subgraph plus the structural nodes the span touches),
2. adds the span to that graph with the usual per-span handler,
3. recomputes the cross-span heuristics (handoffs, capability chains,
   container boundary states) over the loaded graph, and
4. returns only the difference against what was loaded, as a ``StreamDelta``,
   for the caller to write back.

The heuristics' derived items (bridge ProcessingCalls, container-boundary
Transitions and States) are dropped from the loaded graph and rebuilt every
time, so a late-arriving span replaces stale ones instead of piling up.

The one thing a node cannot rebuild is a span's handoff signal
(``ioa_observe.handoff.source.span_ids``): ontology models forbid extra
fields, so it is carried on the AgentCall payload as the non-ontology
``handoffSourceSpanIds`` property.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError
from oxp_ontology.models import edges as edge_models
from oxp_ontology.models import nodes as node_models
from oxp_ontology.models.base import KGBase
from oxp_ontology.models.edges import (
    correspondsToTransition,
    executesAgent,
    hasFinalState,
    hasInitialState,
    hasState,
)
from oxp_ontology.models.nodes import AgentCall, MASCall, ProcessingCall, Session, Transition

from .build import apply_heuristics, dispatch_span, serialize_registry
from .fields import attrs, get_session_id
from .heuristics.handoff import _source_span_ids
from .registry import Registry
from ..verifier import PROPERTY_DOMAIN_RANGE

HANDOFF_SOURCES_PROP = "handoffSourceSpanIds"


@dataclass
class StreamDelta:
    """What a single ``StreamNormalizer.process`` call changed in the database.

    ``nodes``/``edges`` are new or modified items; ``removed_*`` are items the
    database holds that the recomputed graph no longer contains. Edges carry
    ``from_type``/``to_type`` so they can be written without their endpoint
    nodes being part of the same delta.
    """

    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    removed_edges: list[dict[str, Any]] = field(default_factory=list)
    removed_nodes: list[dict[str, Any]] = field(default_factory=list)


class GraphReader(Protocol):
    def load(
        self, session_id: str, node_ids: Sequence[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return ``(nodes, edges)`` as stored.

        ``nodes``: every node with ``sessionId == session_id`` or ``id`` in
        ``node_ids``, plus the endpoints of the edges below, each a dict with
        ``node_type`` and its properties. ``edges``: every edge touching a
        node of that session, plus those among ``node_ids``, each a dict
        with ``edge_type``, ``from_id`` and ``to_id``.
        """
        ...


def _node_key(node: dict[str, Any]) -> tuple[str, str, str]:
    return ("node", str(node["node_type"]), str(node["id"]))


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return ("edge", str(edge["edge_type"]), str(edge["from_id"]), str(edge["to_id"]))


def _rehydrate(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[Registry, dict[str, list[str]]]:
    registry = Registry()
    signals: dict[str, list[str]] = {}
    for raw in nodes:
        cls = getattr(node_models, str(raw["node_type"]), None)
        if cls is None:
            continue
        data = {k: v for k, v in raw.items() if k in cls.model_fields}
        try:
            node = cls.model_validate(data)
        except ValidationError:
            continue  # partial node (only an id) written ahead of its own span; that span will fill it in
        registry.upsert(node)
        sources = raw.get(HANDOFF_SOURCES_PROP)
        if sources:
            signals[node.id] = [str(item) for item in sources]
    for raw in edges:
        cls = getattr(edge_models, str(raw["edge_type"]), None)
        if cls is None:
            continue
        registry.add_edge(cls(source_id=str(raw["from_id"]), target_id=str(raw["to_id"])))
    return registry, signals


def _strip_derived(registry: Registry) -> None:
    """Drop everything ``apply_heuristics`` derives, so it can be rebuilt."""
    containers = {n.id for n in registry.all_of(Session)} | {n.id for n in registry.all_of(MASCall)}
    bridges = {n.id for n in registry.all_of(ProcessingCall)}
    owners = containers | bridges
    transitions = {
        target
        for etype, source, target in registry.edges
        if etype is correspondsToTransition and source in owners
    }
    for bridge_id in bridges:
        registry.remove_node(ProcessingCall, bridge_id)
    for transition_id in transitions:
        registry.remove_node(Transition, transition_id)
    gone = bridges | transitions
    boundary_edges = (hasInitialState, hasFinalState, hasState)
    registry.remove_edges_where(
        lambda etype, source, target: (
            source in gone or target in gone or (etype in boundary_edges and source in containers)
        )
    )


def _handoff_spans(registry: Registry, signals: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Minimal ``*.agent`` spans carrying only the handoff signal, rebuilt from stored state."""
    spans: list[dict[str, Any]] = []
    for call in registry.all_of(AgentCall):
        sources = signals.get(call.id)
        agent_id = registry.edge_target(executesAgent, call.id)
        if not sources or agent_id is None:
            continue
        spans.append(
            {
                "SpanName": "handoff.agent",
                "SpanId": call.spanId,
                "SpanAttributes": {
                    "agent_id": agent_id,
                    "ioa_observe.handoff.source.span_ids": json.dumps(sources),
                },
            }
        )
    return spans


def _endpoint_type(edge_type: str, side: int, node_id: str, node_types: dict[str, str]) -> str:
    """Type of an edge endpoint: its node's own type, else the one class the
    ontology allows there (``side`` 0 = domain, 1 = range). "" if ambiguous.

    An endpoint node can legitimately not exist yet -- e.g. ``usesLLM`` is
    emitted by a chat span before the agent span that creates the Agent --
    in which case the database holds a partial (id-only) node until then.
    """
    if node_id in node_types:
        return node_types[node_id]
    candidates = PROPERTY_DOMAIN_RANGE.get(edge_type, ([], []))[side]
    return str(candidates[0]) if len(candidates) == 1 else ""


def _snapshot(registry: Registry, signals: dict[str, list[str]]) -> dict[tuple[str, ...], dict[str, Any]]:
    nodes, edges = serialize_registry(registry)
    node_types = {str(n["id"]): str(n["node_type"]) for n in nodes}
    items: dict[tuple[str, ...], dict[str, Any]] = {}
    for node in nodes:
        if node["node_type"] == "AgentCall" and signals.get(str(node["id"])):
            node[HANDOFF_SOURCES_PROP] = signals[str(node["id"])]
        items[_node_key(node)] = node
    for edge in edges:
        edge["from_type"] = _endpoint_type(edge["edge_type"], 0, str(edge["from_id"]), node_types)
        edge["to_type"] = _endpoint_type(edge["edge_type"], 1, str(edge["to_id"]), node_types)
        items[_edge_key(edge)] = edge
    return items


class StreamNormalizer:
    def __init__(self, reader: GraphReader) -> None:
        self._reader = reader

    def process(self, span: dict[str, Any]) -> StreamDelta:
        span_attrs = attrs(span)
        session_id = get_session_id(span, span_attrs)

        # Dry run on an empty registry to learn which nodes this span touches.
        scratch = Registry()
        dispatch_span(span, scratch)
        touched = {node.id for node in scratch.nodes.values()}
        for _etype, source_id, target_id in scratch.edges:
            touched.update((source_id, target_id))

        stored_nodes, stored_edges = self._reader.load(session_id, sorted(touched))
        registry, signals = _rehydrate(stored_nodes, stored_edges)

        # Already processed (re-delivery / re-run): handlers are not order-independent,
        # so replaying a span into a complete graph would change it. Make it a no-op.
        span_id = str(span.get("SpanId") or "")
        if span_id and any(getattr(n, "spanId", None) == span_id for n in registry.nodes.values()):
            return StreamDelta()

        before = _snapshot(registry, signals)

        dispatch_span(span, registry)
        if str(span.get("SpanName") or "").endswith(".agent"):
            sources = _source_span_ids(span_attrs)
            call = registry.find(AgentCall, lambda a: a.spanId == span_id)
            if sources and call is not None:
                signals[call.id] = sources

        _strip_derived(registry)
        apply_heuristics(_handoff_spans(registry, signals), registry)
        after = _snapshot(registry, signals)

        delta = StreamDelta()
        for key, item in after.items():
            if before.get(key) != item:
                (delta.nodes if key[0] == "node" else delta.edges).append(item)
        for key, item in before.items():
            if key not in after:
                (delta.removed_nodes if key[0] == "node" else delta.removed_edges).append(item)
        return delta


class InMemoryGraph:
    """A ``GraphReader`` plus writer over plain dicts; for tests and dry runs."""

    # Set on creation and never changed afterwards, same as the Neo4j store.
    IMMUTABLE_PROPS = frozenset({"startTime", "endTime"})

    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    def load(
        self, session_id: str, node_ids: Sequence[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        ids = set(node_ids)
        by_id = {node["id"]: node for node in self.nodes.values()}
        in_session = {i for i, n in by_id.items() if session_id and n.get("sessionId") == session_id}
        edges = [
            e
            for e in self.edges.values()
            if e["from_id"] in in_session
            or e["to_id"] in in_session
            or (e["from_id"] in ids and e["to_id"] in ids)
        ]
        wanted = in_session | ids | {e["from_id"] for e in edges} | {e["to_id"] for e in edges}
        nodes = [dict(by_id[i]) for i in wanted if i in by_id]
        return nodes, [dict(e) for e in edges]

    def apply(self, delta: StreamDelta) -> None:
        for edge in delta.removed_edges:
            self.edges.pop((edge["edge_type"], edge["from_id"], edge["to_id"]), None)
        for node in delta.removed_nodes:
            self.nodes.pop((node["node_type"], node["id"]), None)
            self.edges = {
                k: e for k, e in self.edges.items() if node["id"] not in (e["from_id"], e["to_id"])
            }
        for node in delta.nodes:
            key = (node["node_type"], node["id"])
            existing = self.nodes.get(key)
            if existing is None:
                self.nodes[key] = dict(node)
            else:
                existing.update({k: v for k, v in node.items() if k not in self.IMMUTABLE_PROPS})
        for edge in delta.edges:
            self.edges[(edge["edge_type"], edge["from_id"], edge["to_id"])] = dict(edge)
