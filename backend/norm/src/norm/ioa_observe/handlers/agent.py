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
    get_agent_id,
    get_application_id,
    get_duration_ms,
    get_end_time,
    get_session_id,
    get_start_time,
    get_success,
)
from ..registry import Registry
from ..trajectory import add_state_pair_transition


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
    agent_id = get_agent_id(span, span_attrs)
    if not agent_id:
        return
    application_id = get_application_id(span, span_attrs)
    session_id = get_session_id(span, span_attrs)
    span_id = str(span.get("SpanId") or "")

    name = str(span_attrs.get("ioa_observe.entity.name") or agent_id)
    description = str(span_attrs.get("ioa_observe.entity.description") or "")
    agent, created = registry.add_if_not_exists(
        Agent(id=agent_id, name=name, description=description)
    )
    if created and application_id:
        registry.add_edge(belongsToMAS(source_id=agent.id, target_id=application_id))

    start_time = get_start_time(span, span_attrs)
    end_time = get_end_time(start_time, span)
    duration_ms = get_duration_ms(span)

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
            success=get_success(span, span_attrs),
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
