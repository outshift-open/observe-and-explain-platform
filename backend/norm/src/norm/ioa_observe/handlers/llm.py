#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handlers for the "llm.*" events (OTel log records): the event-side of handle_chat."""

from __future__ import annotations

from typing import Any

from oxp_ontology.models.edges import (
    executesLLM,
    hasFinalState,
    hasInitialState,
    hasLLMCall,
    usesLLM,
)
from oxp_ontology.models.nodes import LLM, LLMCall

from ..fields import _hash_id
from ..registry import Registry
from ..trajectory import add_final_state_transition, add_initial_state
from .agent import _own_agent_id
from .topology import _ensure_agent_call


def _ensure_llm_call(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> tuple[LLMCall, str, str, float] | None:
    """Ensure the whole chain down to the LLMCall exists -- MAS, Session, MASCall, Agent,
    AgentCall (the owning ``ioa_observe.agent.span_id``), LLM and LLMCall -- creating
    whatever is missing.

    Returns ``(llm_call, session_id, span_id, event_time)``, or None if the event names
    no agent, session or LLM.
    """
    owning_span_id = str(event_attrs.get("ioa_observe.agent.span_id") or "")
    ensured = _ensure_agent_call(event, event_attrs, registry, span_id=owning_span_id)
    llm_name = str(event_attrs.get("llm.name") or "")
    if ensured is None or not llm_name:
        return None
    agent_call, session_id, _, event_time = ensured
    agent_id = _own_agent_id(registry, agent_call) or str(event_attrs.get("agent.name") or "")
    span_id = str(event_attrs.get("llm.call.id") or event.get("SpanId") or event_attrs.get("span.id") or "")

    # llm.name is "<provider>/<model>" (as in "azure/gpt-4o"); handle_chat gets them separately.
    provider, _, model = llm_name.partition("/")
    if not model:
        provider, model = "", llm_name
    llm, _ = registry.add_if_not_exists(
        LLM(id=f"llm-{provider}-{model}", name=model, provider=provider)
    )
    registry.add_edge(usesLLM(source_id=agent_id, target_id=llm.id))

    llm_call, _ = registry.add_if_not_exists(
        LLMCall(
            id=_hash_id("llmcall", provider, model, span_id),
            name=f"LLM call ({provider}/{model}) {span_id}",
            sessionId=session_id,
            startTime=event_time,
            endTime=event_time,
            duration=0.0,
            spanId=span_id,
            parentSpanId=owning_span_id,
        )
    )
    registry.add_edge(executesLLM(source_id=llm_call.id, target_id=llm.id))
    registry.add_edge(hasLLMCall(source_id=agent_call.id, target_id=llm_call.id))
    return llm_call, session_id, span_id, event_time


def handle_llm_started(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the chain down to the LLMCall and give it its initial State (from
    ``llm.input``) once. Its final State and Transition need ``llm.output``, so they
    belong to ``llm.completed``."""
    ensured = _ensure_llm_call(event, event_attrs, registry)
    if ensured is None:
        return
    llm_call, session_id, span_id, _ = ensured
    if registry.edge_target(hasInitialState, llm_call.id) is None:
        add_initial_state(
            registry, llm_call.id, session_id, span_id, str(event_attrs.get("llm.input") or "")
        )


def handle_llm_completed(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the chain down to the LLMCall, close it, and give it its final State
    (from ``llm.output``) and Transition. The initial State is whatever ``llm.started``
    stored; only if there is none is one created, from ``llm.input``."""
    ensured = _ensure_llm_call(event, event_attrs, registry)
    if ensured is None:
        return
    llm_call, session_id, span_id, event_time = ensured

    if event_time > llm_call.endTime:
        llm_call.endTime = event_time  # type: ignore[attr-defined]
        llm_call.duration = (event_time - llm_call.startTime) * 1000.0  # type: ignore[attr-defined]

    input_text = str(event_attrs.get("llm.input") or "")
    initial_id = registry.edge_target(hasInitialState, llm_call.id)
    if initial_id is None:
        initial_id = add_initial_state(registry, llm_call.id, session_id, span_id, input_text).id
    if registry.edge_target(hasFinalState, llm_call.id) is not None:
        return
    add_final_state_transition(
        registry,
        llm_call.id,
        session_id,
        span_id,
        initial_id,
        input_text,
        str(event_attrs.get("llm.output") or ""),
    )
