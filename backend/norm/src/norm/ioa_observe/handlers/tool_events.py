#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handlers for the "tool.*" events (OTel log records): the event-side of handle_tool."""

from __future__ import annotations

from typing import Any

from oxp_ontology.models.edges import (
    executesTool,
    hasFinalState,
    hasInitialState,
    hasToolCall,
    usesTool,
)
from oxp_ontology.models.nodes import AgentCall, Tool, ToolCall

from ..fields import (
    _hash_id,
    get_event_application_id,
    get_event_session_id,
    get_event_start_time,
)
from ..registry import Registry
from ..trajectory import add_final_state_transition, add_initial_state
from .a2a import handle_a2a_tool_started
from .agent import _ensure_mas_call, _own_agent_id


def _ensure_tool_call(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> tuple[ToolCall, str, str, float] | None:
    """Ensure MAS, Session, MASCall, Tool and ToolCall exist, creating whatever is missing,
    and link the ToolCall to its AgentCall.

    Tool events carry no ``agent.name``, only the owning ``ioa_observe.agent.span_id``, so
    the AgentCall (and Agent) can be found but not created here. If it isn't there yet,
    ``topology.node.*`` links this ToolCall when it creates the AgentCall.

    Returns ``(tool_call, session_id, span_id, event_time)``, or None if the event names
    no session or tool.
    """
    tool_name = str(event_attrs.get("tool.name") or "")
    session_id = get_event_session_id(event, event_attrs)
    if not tool_name or not session_id:
        return None
    application_id = get_event_application_id(event, event_attrs)
    owning_span_id = str(event_attrs.get("ioa_observe.agent.span_id") or "")
    span_id = str(event.get("SpanId") or event_attrs.get("span.id") or "")
    event_time = get_event_start_time(event, event_attrs)

    if application_id:
        _ensure_mas_call(registry, session_id, application_id, event_time)
    tool, _ = registry.add_if_not_exists(Tool(id=tool_name, name=tool_name, description=""))
    # ``tool.call.id`` is the id of the call itself, shared by every event about it: the
    # tool.* events and, for an MCP tool, the mcp.message.* events (as their message.id).
    # Without it the call is told apart by the span of the event.
    call_id = str(event_attrs.get("tool.call.id") or "") or _hash_id("toolcall", tool_name, span_id)
    tool_call, _ = registry.add_if_not_exists(
        ToolCall(
            id=call_id,
            name=f"Tool call ({tool_name}) {span_id}",
            sessionId=session_id,
            startTime=event_time,
            endTime=event_time,
            duration=0.0,
            spanId=span_id,
            parentSpanId=owning_span_id,
        )
    )
    registry.add_edge(executesTool(source_id=tool_call.id, target_id=tool.id))

    agent_call = (
        registry.find(AgentCall, lambda a: a.spanId == owning_span_id) if owning_span_id else None
    )
    if agent_call is not None:
        registry.add_edge(hasToolCall(source_id=agent_call.id, target_id=tool_call.id))
        agent_id = _own_agent_id(registry, agent_call)
        if agent_id:
            registry.add_edge(usesTool(source_id=agent_id, target_id=tool.id))
    return tool_call, session_id, span_id, event_time


def handle_tool_started(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the ToolCall's nodes and edges and give it its initial State (from
    ``tool.input``) once. Its final State and Transition need ``tool.output``, so they
    belong to ``tool.completed``.

    A tool of type ``a2a`` is a call to another agent, not a tool: it is a handoff (see
    ``handle_a2a_tool_started``) and gets no Tool or ToolCall."""
    if str(event_attrs.get("tool.type") or "") == "a2a":
        handle_a2a_tool_started(event, event_attrs, registry)
        return
    ensured = _ensure_tool_call(event, event_attrs, registry)
    if ensured is None:
        return
    tool_call, session_id, span_id, _ = ensured
    if registry.edge_target(hasInitialState, tool_call.id) is None:
        add_initial_state(
            registry, tool_call.id, session_id, span_id, str(event_attrs.get("tool.input") or "")
        )


def handle_tool_completed(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the ToolCall's nodes and edges, close it, and give it its final State
    (from ``tool.output``) and Transition. The initial State is whatever ``tool.started``
    stored; only if there is none is one created, from ``tool.input``.

    A tool of type ``a2a`` is a handoff, recorded by ``tool.started``; nothing to close."""
    if str(event_attrs.get("tool.type") or "") == "a2a":
        # TODO: the handoff's result (tool.output) is not recorded yet.
        return
    ensured = _ensure_tool_call(event, event_attrs, registry)
    if ensured is None:
        return
    tool_call, session_id, span_id, event_time = ensured

    if event_time > tool_call.endTime:
        tool_call.endTime = event_time  # type: ignore[attr-defined]
        tool_call.duration = (event_time - tool_call.startTime) * 1000.0  # type: ignore[attr-defined]
    status = str(event_attrs.get("tool.status") or "")
    if status:
        tool_call.success = status == "success"  # type: ignore[attr-defined]

    input_text = str(event_attrs.get("tool.input") or "")
    initial_id = registry.edge_target(hasInitialState, tool_call.id)
    if initial_id is None:
        initial_id = add_initial_state(registry, tool_call.id, session_id, span_id, input_text).id
    if registry.edge_target(hasFinalState, tool_call.id) is not None:
        return
    add_final_state_transition(
        registry,
        tool_call.id,
        session_id,
        span_id,
        initial_id,
        input_text,
        str(event_attrs.get("tool.output") or ""),
    )
