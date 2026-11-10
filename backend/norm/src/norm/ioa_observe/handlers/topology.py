#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handlers for the "topology.*" events (OTel log records)."""

from __future__ import annotations

from typing import Any

from oxp_ontology.models.edges import (
    belongsToMAS,
    executesAgent,
    executesSession,
    executesTool,
    hasAgentCall,
    hasFinalState,
    hasInitialState,
    hasToolCall,
    usesTool,
)
from oxp_ontology.models.nodes import MAS, Agent, AgentCall, Session, State, ToolCall

from ..fields import (
    _hash_id,
    get_event_application_id,
    get_event_session_id,
    get_event_start_time,
)
from ..registry import Registry
from ..trajectory import add_final_state_transition, add_initial_state
from .agent import _ensure_agent, _ensure_mas_call, _own_agent_id


def handle_topology_edge_updated(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """The handoff from one agent to another: an ``executesAgent`` edge from the source's
    AgentCall to the target Agent.

    The source is the AgentCall of ``source.agent.span.id``; the target is named only
    (``target.agent``), so it is the Agent of that name. Nothing is created: the agents'
    own events do that, and an edge to something that is not an agent (an MCP server, say)
    matches nothing."""
    source_span_id = str(event_attrs.get("source.agent.span.id") or "")
    target_name = str(event_attrs.get("target.agent") or "")
    session_id = get_event_session_id(event, event_attrs)
    if not source_span_id or not target_name or not session_id:
        return
    source = registry.find(
        AgentCall, lambda call: call.spanId == source_span_id and call.sessionId == session_id
    )
    target = registry.find(Agent, lambda agent: agent.name == target_name)
    if source is not None and target is not None and target.id != _own_agent_id(registry, source):
        registry.add_edge(executesAgent(source_id=source.id, target_id=target.id))


def _ensure_session_and_mas(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> Session | None:
    """Ensure the Session and its MAS exist, linked by ``executesSession``, creating
    whichever is missing. None if the event has no session id."""
    session_id = get_event_session_id(event, event_attrs)
    application_id = get_event_application_id(event, event_attrs)
    if not session_id:
        return None
    start_time = get_event_start_time(event, event_attrs)

    session, _ = registry.add_if_not_exists(
        Session(
            id=session_id,
            name=f"Session {session_id}",
            sessionId=session_id,
            startTime=start_time,
            endTime=start_time,
            duration=0.0,
            spanId=str(event.get("SpanId") or event_attrs.get("span.id") or ""),
        )
    )
    if application_id:
        mas, _ = registry.add_if_not_exists(
            MAS(id=application_id, name=application_id, description=application_id)
        )
        registry.add_edge(executesSession(source_id=session.id, target_id=mas.id))
    return session


def _ensure_session_initial_state(registry: Registry, session: Session) -> str:
    """The Session's first State, with ``hasInitialState``, created once. Keyed on the
    session id: the session events carry no span id of their own, nor any content."""
    initial_id = registry.edge_target(hasInitialState, session.id)
    if initial_id is None:
        initial_id = add_initial_state(registry, session.id, session.sessionId, session.id, "").id
    return initial_id


def handle_topology_session_started(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the Session and its MAS, and give the Session its initial State."""
    session = _ensure_session_and_mas(event, event_attrs, registry)
    if session is not None:
        _ensure_session_initial_state(registry, session)


def handle_topology_session_completed(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Same nodes as session.started, then close the Session and give it a final State
    and Transition. The event carries no input/output, so the States have no content.

    Every ``session.completed`` adds a State (and Transition), but only the latest one
    -- by ``event.time``, not by arrival -- holds ``hasFinalState``: a later event moves
    it, an earlier or repeated one leaves it where it is."""
    session = _ensure_session_and_mas(event, event_attrs, registry)
    if session is None:
        return
    end_time = get_event_start_time(event, event_attrs)
    initial_id = _ensure_session_initial_state(registry, session)

    # Session.endTime only ever moves forward, so it is the latest completion seen so far
    # (it starts at startTime, hence the check for no final State yet).
    is_latest = registry.edge_target(hasFinalState, session.id) is None or end_time > session.endTime
    if end_time > session.endTime:
        session.endTime = end_time  # type: ignore[attr-defined]
        session.duration = (end_time - session.startTime) * 1000.0  # type: ignore[attr-defined]
    if is_latest:
        registry.remove_edges_where(lambda cls, src, _: cls is hasFinalState and src == session.id)
    add_final_state_transition(
        registry,
        session.id,
        session.sessionId,
        f"{session.id}@{end_time}",  # one final State per completion time
        initial_id,
        "",
        "",
        mark_final=is_latest,
    )


def _ensure_agent_call(
    event: dict[str, Any],
    event_attrs: dict[str, Any],
    registry: Registry,
    span_id: str | None = None,
) -> tuple[AgentCall, str, str, float] | None:
    """Agent-side counterpart of handle_agent: make sure the MAS, Session, MASCall,
    Agent and AgentCall for this event's node exist, creating whichever are missing.

    ``span_id`` is the AgentCall's span (default: the event's own, as for ``node.*``
    events; ``llm.*``/``tool.*`` events pass their owning agent span).

    Returns ``(agent_call, session_id, span_id, event_time)``, or None if the event
    names no agent or session.
    """
    agent_id = str(event_attrs.get("agent.name") or "")
    session_id = get_event_session_id(event, event_attrs)
    if not agent_id or not session_id:
        return None
    application_id = get_event_application_id(event, event_attrs)
    if span_id is None:
        span_id = str(event.get("SpanId") or event_attrs.get("span.id") or "")
    event_time = get_event_start_time(event, event_attrs)

    # The Agent is keyed on the agent's span id -- the same value whether it comes from the
    # agent's own node.* event (span.id) or from its llm.*/tool.* events
    # (ioa_observe.agent.span_id). One that an a2a.agent_card left unattached, under the
    # same name, is adopted; the first event naming the MAS connects it.
    mas_prefix = str(event_attrs.get("session.id") or "").partition("_")[0]
    agent = _ensure_agent(registry, span_id or agent_id, agent_id, (application_id, mas_prefix))
    if application_id:
        registry.add_edge(belongsToMAS(source_id=agent.id, target_id=application_id))

    agent_call, _ = registry.add_if_not_exists(
        AgentCall(
            id=_hash_id("agentcall", agent_id, span_id),
            name=f"{agent_id} call {span_id}",
            sessionId=session_id,
            startTime=event_time,
            endTime=event_time,
            duration=0.0,
            spanId=span_id,
        )
    )
    registry.add_edge(executesAgent(source_id=agent_call.id, target_id=agent.id))
    if application_id:
        mas_call = _ensure_mas_call(registry, session_id, application_id, agent_call.startTime)
        registry.add_edge(hasAgentCall(source_id=mas_call.id, target_id=agent_call.id))
    # Tool events name only their owning agent *span*, so a ToolCall can arrive before its
    # AgentCall exists: attach the ones already waiting for this span.
    for tool_call in registry.all_of(ToolCall):
        if span_id and tool_call.parentSpanId == span_id:
            registry.add_edge(hasToolCall(source_id=agent_call.id, target_id=tool_call.id))
            tool_id = registry.edge_target(executesTool, tool_call.id)
            if tool_id:
                registry.add_edge(usesTool(source_id=agent.id, target_id=tool_id))
    return agent_call, session_id, span_id, event_time


def handle_topology_node_started(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the agent's nodes exist and give the AgentCall its initial State
    (from ``agent.input``) -- once; if it already has one, it is left alone."""
    ensured = _ensure_agent_call(event, event_attrs, registry)
    if ensured is None:
        return
    agent_call, session_id, span_id, _ = ensured
    if registry.edge_target(hasInitialState, agent_call.id) is None:
        add_initial_state(
            registry, agent_call.id, session_id, span_id, str(event_attrs.get("agent.input") or "")
        )


def handle_topology_node_completed(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the agent's nodes exist, close the AgentCall and give it its final
    State (from ``agent.output``) and Transition. The initial State is whatever
    ``node.started`` stored; only if there is none is one created, from ``agent.input``."""
    ensured = _ensure_agent_call(event, event_attrs, registry)
    if ensured is None:
        return
    agent_call, session_id, span_id, event_time = ensured

    if event_time > agent_call.endTime:
        agent_call.endTime = event_time  # type: ignore[attr-defined]
        agent_call.duration = (event_time - agent_call.startTime) * 1000.0  # type: ignore[attr-defined]

    # node.completed carries agent.input as well as agent.output. If it is ever missing,
    # the stored initial State (from node.started) supplies the input below.
    input_text = str(event_attrs.get("agent.input") or "")

    initial_id = registry.edge_target(hasInitialState, agent_call.id)
    if initial_id is None:
        initial_id = add_initial_state(registry, agent_call.id, session_id, span_id, input_text).id
    if registry.edge_target(hasFinalState, agent_call.id) is not None:
        return
    if not input_text:
        initial = registry.get(State, initial_id)
        stored = initial.content if initial is not None else ""
        input_text = "" if stored == "(no content recorded)" else stored
    add_final_state_transition(
        registry,
        agent_call.id,
        session_id,
        span_id,
        initial_id,
        input_text,
        str(event_attrs.get("agent.output") or ""),
    )
