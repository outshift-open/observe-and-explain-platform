#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the "*.agent" span name: Agent, AgentCall, initial/final State."""

from __future__ import annotations

from typing import Any

from oxp_ontology.models.edges import (
    belongsToMAS,
    executesAgent,
    executesMAS,
    executesSession,
    hasAgentCall,
    hasMASCall,
)
from oxp_ontology.models.nodes import MAS, Agent, AgentCall, MASCall, Session

from ..fields import (
    _hash_id,
    get_span_agent_id,
    get_span_application_id,
    get_span_duration_ms,
    get_span_end_time,
    get_span_session_id,
    get_span_start_time,
    get_span_success,
)
from ..registry import Registry
from ..trajectory import add_state_pair_transition


def _is_unattached(registry: Registry, node_id: str) -> bool:
    return not any(node_id in (source, target) for _, source, target in registry.edges)


def _in_mas(registry: Registry, agent: Agent, mas_ids: tuple[str, ...]) -> bool:
    """True if the Agent is attached to nothing or belongs to one of ``mas_ids``."""
    if _is_unattached(registry, agent.id):
        return True
    return any(m in registry.edges_from(belongsToMAS, agent.id) for m in mas_ids if m) or not any(
        True for _ in registry.edges_from(belongsToMAS, agent.id)
    )


def _find_nameless_agent(registry: Registry, name: str, mas_ids: tuple[str, ...]) -> Agent | None:
    """An Agent of exactly this ``name`` that has no span id of its own yet, i.e. one left by
    an ``a2a.agent_card`` (or by a handoff target): keyed on its name and either attached to
    one of ``mas_ids`` (what the card does) or attached to nothing."""
    for agent in registry.all_of(Agent):
        if agent.name != name:
            continue
        if _is_unattached(registry, agent.id):
            return agent
        if agent.id == name and any(
            mas_id in registry.edges_from(belongsToMAS, agent.id) for mas_id in mas_ids
        ):
            return agent
    return None


def _ensure_agent(
    registry: Registry, agent_id: str, name: str, mas_ids: tuple[str, ...] = ()
) -> Agent:
    """The Agent with this id; created if absent.

    Before creating one, an Agent of exactly the same name that is still keyed on its name
    -- what an ``a2a.agent_card`` leaves behind, attached to the MAS (``mas_ids``) -- or an
    unattached one, is adopted: it is replaced by the new node, which keeps its description."""
    agent = registry.get(Agent, agent_id)
    if agent is not None:
        if name and not agent.name:  # created by an event that did not know the name
            agent.name = name  # type: ignore[attr-defined]
        return agent
    description = ""
    orphan = _find_nameless_agent(registry, name, tuple(m for m in mas_ids if m)) if name else None
    if orphan is not None and orphan.id != agent_id:
        description = orphan.description
        registry.remove_node(Agent, orphan.id)
        registry.remove_edges_where(lambda _, source, target: orphan.id in (source, target))
    return registry.add(Agent(id=agent_id, name=name, description=description))


def _latest_call_of(
    registry: Registry, agent_name: str, session_id: str, not_after: float | None = None
) -> AgentCall | None:
    """The most recently started AgentCall, in the session, of the Agent called ``agent_name``
    (agents are found by name: their ids are span ids), optionally one started no later than
    ``not_after``."""
    latest: AgentCall | None = None
    for edge_type, call_id, agent_id in registry.edges:
        if edge_type is not executesAgent:
            continue
        agent = registry.get(Agent, agent_id)
        call = registry.get(AgentCall, call_id)
        if agent is None or call is None or agent.name != agent_name or call.sessionId != session_id:
            continue
        if not_after is not None and call.startTime > not_after:
            continue
        if latest is None or call.startTime > latest.startTime:
            latest = call
    return latest


def _own_agent_id(registry: Registry, call: AgentCall) -> str | None:
    """The id of the Agent this AgentCall is an instance of.

    A call can have more than one ``executesAgent`` edge: ``topology.edge.updated`` adds
    one to the agent it hands off to. The call's own Agent is the one keyed on its span
    (see ``_ensure_agent_call``); failing that, the only or the first."""
    agent_ids = registry.edges_from(executesAgent, call.id)
    return next((i for i in agent_ids if i == call.spanId), agent_ids[0] if agent_ids else None)


def _ensure_session(
    registry: Registry, session_id: str, application_id: str, start_time: float
) -> Session:
    """The "*.agent" span is usually the first to need a Session -- "session.start"
    never actually fires in real captured traces -- so build one here too if
    handle_session_start hasn't already."""
    session, created = registry.add_if_not_exists(
        Session(
            id=session_id,
            name=f"Session {session_id}",
            sessionId=session_id,
            startTime=start_time,
            endTime=start_time,
            duration=0.0,
        )
    )
    if created and application_id:
        registry.add_edge(
            executesSession(
                source_id=session.id,
                target_id=application_id,
            )
        )
    return session


def _ensure_mas_call(
    registry: Registry, session_id: str, application_id: str, start_time: float
) -> MASCall:
    """``hasAgentCall`` attaches under MASCall, not Session -- no span type
    produces one, so build it (and its own Session) lazily here."""
    mas_call, created = registry.add_if_not_exists(
        MASCall(
            id=f"mascall:{session_id}",
            name=f"MASCall {session_id}",
            sessionId=session_id,
            startTime=start_time,
            endTime=start_time,
            duration=0.0,
        )
    )
    if created:
        session = _ensure_session(registry, session_id, application_id, start_time)
        mas = registry.add(
            MAS(
                id=application_id,
                name=application_id,
                description=application_id,
            )
        )
        registry.add_edge(hasMASCall(source_id=session.id, target_id=mas_call.id))
        registry.add_edge(executesMAS(source_id=mas_call.id, target_id=mas.id))
    return mas_call


def handle_agent(
    span: dict[str, Any],
    span_attrs: dict[str, Any],
    registry: Registry,
) -> None:
    # Some "*.agent" spans carry no agent id: the agent is then known by its name, which is
    # also the id of the Agent an a2a.agent_card creates.
    entity_name = str(span_attrs.get("ioa_observe.entity.name") or "")
    agent_id = get_span_agent_id(span, span_attrs) or entity_name
    if not agent_id:
        return
    application_id = get_span_application_id(span, span_attrs)
    session_id = get_span_session_id(span, span_attrs)
    span_id = str(span.get("SpanId") or "")

    name = entity_name or agent_id
    description = str(span_attrs.get("ioa_observe.entity.description") or "")
    # An Agent may already be there from its a2a.agent_card (keyed on its name, attached to
    # the MAS of the card's session): reuse it only if it is the same name in the same MAS,
    # fill in what it lacks, and connect it. The same name in another MAS is another Agent.
    mas_ids = (application_id,)
    existing = registry.get(Agent, agent_id)
    if existing is not None and not _in_mas(registry, existing, mas_ids):
        agent_id = f"{application_id}:{agent_id}"
    agent = _ensure_agent(registry, agent_id, name, mas_ids)
    if description and not agent.description:
        agent.description = description  # type: ignore[attr-defined]
    if application_id:
        registry.add_edge(belongsToMAS(source_id=agent.id, target_id=application_id))

    start_time = get_span_start_time(span, span_attrs)
    end_time = get_span_end_time(start_time, span)
    duration_ms = get_span_duration_ms(span)

    call_id = _hash_id("agentcall", agent_id, span_id)
    agent_call = registry.add(
        AgentCall(
            id=call_id,
            name=f"{agent_id} call {span_id}",
            sessionId=session_id,
            startTime=start_time,
            endTime=end_time,
            duration=duration_ms,
            spanId=span_id,
            parentSpanId=str(span.get("ParentSpanId") or ""),
            success=get_span_success(span, span_attrs),
        )
    )
    registry.add_edge(executesAgent(source_id=agent_call.id, target_id=agent.id))

    if application_id:
        mas_call = _ensure_mas_call(registry, session_id, application_id, start_time)
        registry.add_edge(hasAgentCall(source_id=mas_call.id, target_id=agent_call.id))

    input_text = str(span_attrs.get("ioa_observe.entity.input") or "")
    output_text = str(span_attrs.get("ioa_observe.entity.output") or "")
    add_state_pair_transition(
        registry,
        agent_call.id,
        session_id,
        span_id,
        input_text,
        output_text,
    )
