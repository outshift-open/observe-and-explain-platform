#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Dispatch: one handler per ``SpanName`` shape, accumulated into a Registry.

"session.start"  -> Session, MAS (placeholder)
"session.end"    -> update Session end time/duration
"*.graph"        -> MAS (declared), Agent/Tool (declared, from graph data)
"*.agent"        -> Agent (undeclared), AgentCall, initial/final State
"*.chat"         -> LLM, LLMCall, initial/final State, Transition
"*.tool"         -> Tool, ToolCall, initial/final State, Transition
"""

from __future__ import annotations

from typing import Any

from .fields import attrs
from .handlers import (
    handle_agent,
    handle_chat,
    handle_graph,
    handle_session_end,
    handle_session_start,
    handle_tool,
)
from .heuristics import (
    assign_container_boundary_states,
    chain_agent_handoffs_fallback,
    chain_capability_calls,
    link_agent_handoffs,
)
from .registry import Registry

_HANDLERS: dict[str, Any] = {
    "session.start": handle_session_start,
    "session.end": handle_session_end,
}


def build_kg(
    spans: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build (nodes, edges) JSON dicts from raw ClickHouse-shaped OTel spans."""
    registry = Registry()

    for span in spans:
        span_name = str(span.get("SpanName") or "")
        span_attrs = attrs(span)

        handler = _HANDLERS.get(span_name)
        if handler is not None:
            handler(span, span_attrs, registry)
        elif span_name.endswith(".graph"):
            handle_graph(span, span_attrs, registry)
        elif span_name.endswith(".agent"):
            handle_agent(span, span_attrs, registry)
        elif span_name.endswith(".chat"):
            handle_chat(span, span_attrs, registry)
        elif span_name.endswith(".tool"):
            handle_tool(span, span_attrs, registry)

    # Clean up trajectory once all spans are processed
    # Agent handoffs
    explicit_handoff_targets = link_agent_handoffs(spans, registry)
    # Fallback: timestamp-order sibling AgentCalls the above left unlinked
    chain_agent_handoffs_fallback(registry, explicit_handoff_targets)
    # Capability calls within agent call
    chain_capability_calls(registry)
    # Session and MAS call i/o
    assign_container_boundary_states(registry)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for item in registry.all_items():
        payload = item.to_json()
        if "node_type" not in payload:
            edges.append(payload)
            continue
        # hierarchyLevel/layer are ClassVar on the ontology models (a fixed
        # constant per concrete class, not per-instance data), so pydantic
        # never serializes them -- read them straight off the class and
        # denormalize them into the output JSON instead.
        for attr in ("hierarchyLevel", "layer"):
            value = getattr(item, attr, None)
            if value is not None:
                payload[attr] = value
        nodes.append(payload)
    return nodes, edges
