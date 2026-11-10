#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handlers for the "a2a.*" events (OTel log records)."""

from __future__ import annotations

import json
from typing import Any

from oxp_ontology.models.edges import belongsToMAS, hasState
from oxp_ontology.models.nodes import Agent, AgentCall, State

from ..fields import _hash_id
from ..registry import Registry
from .agent import _find_nameless_agent, _latest_call_of
from .topology import _ensure_agent_call, _ensure_session_and_mas


def _ensure_message_parties(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> tuple[AgentCall, str, str, str, str, str] | None:
    """What ``a2a.message.sent`` and ``a2a.message.received`` have in common: the sender's
    AgentCall (found by ``source.agent.span.id``) with everything above it -- MAS, Session,
    MASCall, Agent -- and the recipient Agent (``target.agent``), each created if missing.

    Returns ``(sender_call, session_id, source_span_id, target_name, message_id, content)``,
    or None if the event names no sender, recipient, sender span or session."""
    source_name = str(event_attrs.get("source.agent") or "")
    target_name = str(event_attrs.get("target.agent") or "")
    source_span_id = str(
        event_attrs.get("source.agent.span.id")
        or event_attrs.get("ioa_observe.agent.span_id")
        or ""
    )
    if not source_name or not target_name or not source_span_id:
        return None
    ensured = _ensure_agent_call(
        event, {**event_attrs, "agent.name": source_name}, registry, span_id=source_span_id
    )
    if ensured is None:
        return None
    agent_call, session_id, _, _ = ensured
    if registry.find(Agent, lambda agent: agent.name == target_name) is None:
        registry.add(Agent(id=target_name, name=target_name, description=""))
    message_id = str(event_attrs.get("message.id") or event_attrs.get("event.id") or "")
    content = str(event_attrs.get("message.input") or "")
    return agent_call, session_id, source_span_id, target_name, message_id, content


def handle_a2a_message_sent(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the sender's call and recipient Agent, and retain the outgoing message
    as a State of the sender without changing its initial or final State."""
    parties = _ensure_message_parties(event, event_attrs, registry)
    if parties is None:
        return
    agent_call, session_id, source_span_id, target_name, message_id, content = parties
    if not content:
        return
    state = registry.add(
        State(
            id=_hash_id(
                "state", "a2a.message.sent", session_id, source_span_id,
                target_name, message_id, content,
            ),
            sessionId=session_id,
            content=content,
        )
    )
    registry.add_edge(hasState(source_id=agent_call.id, target_id=state.id))


def handle_a2a_message_received(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the same nodes as ``a2a.message.sent``, and retain the incoming message as a
    State of the recipient's AgentCall without changing its initial or final State.

    The event names the recipient only by ``target.agent`` -- its span is not in it, and
    its AgentCall is normally created a few milliseconds later by its own
    ``topology.node.started`` -- so the State is added only if that call is already there;
    otherwise nothing of the message is kept."""
    parties = _ensure_message_parties(event, event_attrs, registry)
    if parties is None:
        return
    _, session_id, source_span_id, target_name, message_id, content = parties
    receiver_call = _latest_call_of(registry, target_name, session_id)
    if receiver_call is None or not content:
        return
    state = registry.add(
        State(
            id=_hash_id(
                "state", "a2a.message.received", session_id, source_span_id,
                target_name, message_id, content,
            ),
            sessionId=session_id,
            content=content,
        )
    )
    registry.add_edge(hasState(source_id=receiver_call.id, target_id=state.id))


def _agent_card(event_attrs: dict[str, Any]) -> dict[str, Any]:
    """The agent card carried in ``capability.content`` (a JSON object), or {} if absent or malformed."""
    content = event_attrs.get("capability.content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return {}
    return content if isinstance(content, dict) else {}


def handle_a2a_agent_card(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Add the Agent the card describes -- ``capability.content``'s ``name`` and
    ``description`` -- to the MAS and Session named by ``session.id``.

    Skipped without a ``session.id``. The MAS is the first part of ``session.id``
    (``<masname>_<sessionid>``) and the Session the rest; both are created if missing. The
    card has no span id of the described agent (its own ``ioa_observe.agent.span_id`` is the
    span of the agent that fetched it), so the Agent is keyed on its name and attached to the
    MAS with ``belongsToMAS``. An Agent of that name already in the MAS (or attached to
    nothing) is reused and only gets its description. The agent's own events later replace
    the node with one keyed on their span id (see ``_ensure_agent``)."""
    card = _agent_card(event_attrs)
    name = str(card.get("name") or "")
    mas_name = str(event_attrs.get("session.id") or "").partition("_")[0]
    if not name or not mas_name:
        return
    if _ensure_session_and_mas(event, {**event_attrs, "application_id": mas_name}, registry) is None:
        return
    description = str(card.get("description") or "")
    agent = _find_nameless_agent(registry, name, (mas_name,)) or next(
        (
            a
            for a in registry.all_of(Agent)
            if a.name == name and mas_name in registry.edges_from(belongsToMAS, a.id)
        ),
        None,
    )
    if agent is None:
        agent = registry.add(Agent(id=name, name=name, description=description))
    elif description and agent.description != description:
        agent.description = description  # type: ignore[attr-defined]
    registry.add_edge(belongsToMAS(source_id=agent.id, target_id=mas_name))
    # TODO: version  (card["version"])
    # TODO: supportedInterfaces  (how to reach the agent: url, protocolBinding, protocolVersion)
    # TODO: provider  (card["provider"], capability.provider.id)
    # TODO: capabilities  (card["capabilities"]: streaming, pushNotifications, ...)
    # TODO: defaultInputModes / defaultOutputModes
    # TODO: skills  (card["skills"])
    # TODO: securitySchemes / security


def handle_a2a_tool_started(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """A ``tool.started`` of type ``a2a``: the agent whose span is
    ``ioa_observe.agent.span_id`` hands off to the agent named ``tool.name``.

    The target Agent is made sure to exist: an Agent of that name, or else an unattached
    one keyed on the name, which the target's own events later replace with the node keyed
    on its span id (see ``_ensure_agent``)."""
    source_span_id = str(event_attrs.get("ioa_observe.agent.span_id") or "")
    target_name = str(event_attrs.get("tool.name") or "")
    if not source_span_id or not target_name:
        return
    if not any(agent.name == target_name for agent in registry.all_of(Agent)):
        registry.add(Agent(id=target_name, name=target_name, description=""))
    # TODO: record the handoff itself, from the Agent keyed on ``source_span_id`` to the
    # target. The ontology has no Agent -> Agent relationship; a handoff is otherwise a
    # bridge ProcessingCall between the two AgentCalls (heuristics/handoff.py), and the
    # target's AgentCall does not exist yet when this event arrives.
