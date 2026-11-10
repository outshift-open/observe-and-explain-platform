#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handlers for the "mcp.*" events (OTel log records)."""

from __future__ import annotations

import json
from typing import Any

from oxp_ontology.models.edges import belongsToMAS, hasFinalState, hasInitialState, usesTool
from oxp_ontology.models.nodes import Tool, ToolCall

from ..registry import Registry
from ..trajectory import add_final_state_transition, add_initial_state
from .agent import _ensure_agent
from .tool_events import _ensure_tool_call
from .topology import _ensure_agent_call, _ensure_session_and_mas


def _discovered_tools(event_attrs: dict[str, Any]) -> list[dict[str, Any]]:
    """The tools listed in ``capability.content`` (a JSON object with a ``tools`` array),
    or [] if absent or malformed."""
    content = event_attrs.get("capability.content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return []
    tools = content.get("tools") if isinstance(content, dict) else None
    return [tool for tool in tools if isinstance(tool, dict)] if isinstance(tools, list) else []


def handle_mcp_tools_discovered(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Ensure the MAS, Session and Agent of the agent that discovered the tools
    (``ioa_observe.agent.span_id``), then create every tool in ``capability.content`` and link each to the agent (``usesTool``).

    Skipped without an ``ioa_observe.agent.span_id`` or a session. The MAS is named by the
    first part of ``session.id`` (``<masname>_<sessionid>``). The Agent is keyed on its span
    id; its name is not in the event, so one that is created here has none until its own
    events give it one. """
    agent_span_id = str(event_attrs.get("ioa_observe.agent.span_id") or "")
    mas_name = str(event_attrs.get("session.id") or "").partition("_")[0]
    if not agent_span_id or not mas_name:
        return
    session = _ensure_session_and_mas(event, {**event_attrs, "application_id": mas_name}, registry)
    if session is None:
        return
    agent = _ensure_agent(registry, agent_span_id, "")
    registry.add_edge(belongsToMAS(source_id=agent.id, target_id=mas_name))

    for item in _discovered_tools(event_attrs):
        name = str(item.get("name") or "")
        if not name:
            continue
        description = str(item.get("description") or "")
        tool, _ = registry.add_if_not_exists(Tool(id=name, name=name, description=description))
        if description and not tool.description:  # created earlier by a tool event, without one
            tool.description = description  # type: ignore[attr-defined]
        registry.add_edge(usesTool(source_id=agent.id, target_id=tool.id))


def _message_tool_name(message_input: Any) -> str:
    """``name`` of the JSON object in ``message.input`` (the tool of a ``tools/call``), or ""
    if the input is empty, not a JSON object, or has no name."""
    if isinstance(message_input, str):
        try:
            message_input = json.loads(message_input)
        except ValueError:
            return ""
    return str(message_input.get("name") or "") if isinstance(message_input, dict) else ""


def _ensure_mcp_tool_call(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> tuple[ToolCall, str, str, float, str] | None:
    """A tool call sent by an agent: ensure the MAS, Session, MASCall, Agent and AgentCall of
    the sender, then the Tool (``message.input.name``) and the ToolCall, and its initial State
    from ``message.input`` -- all created if missing.

    The sender is ``source.agent`` (name) and ``source.agent.span.id`` (the Agent's id and
    the AgentCall's span). The ToolCall is keyed on ``message.id``, which
    ``mcp.message.sent`` and ``mcp.message.completed`` share.

    Returns ``(tool_call, session_id, span_id, event_time, message_input)``, or None if
    ``message.input`` is empty or names no tool, as in a ``tools/list`` request, or the event
    names no sender or session."""
    message_input = str(event_attrs.get("message.input") or "")
    tool_name = _message_tool_name(message_input)
    source_name = str(event_attrs.get("source.agent") or "")
    source_span_id = str(
        event_attrs.get("source.agent.span.id") or event_attrs.get("ioa_observe.agent.span_id") or ""
    )
    if not tool_name or not source_name or not source_span_id:
        return None
    mas_name = str(event_attrs.get("session.id") or "").partition("_")[0]
    agent_attrs = {
        **event_attrs,
        "application_id": event_attrs.get("application_id") or mas_name,
        "agent.name": source_name,
    }
    if _ensure_agent_call(event, agent_attrs, registry, span_id=source_span_id) is None:
        return None
    ensured = _ensure_tool_call(
        event,
        {
            **agent_attrs,
            "tool.name": tool_name,
            "ioa_observe.agent.span_id": source_span_id,
            # the message id is the id of the tool call: tool.started/completed carry it as tool.call.id
            "tool.call.id": event_attrs.get("message.id"),
        },
        registry,
    )
    if ensured is None:
        return None
    tool_call, session_id, span_id, event_time = ensured
    if registry.edge_target(hasInitialState, tool_call.id) is None:
        add_initial_state(registry, tool_call.id, session_id, span_id, message_input)
    return tool_call, session_id, span_id, event_time, message_input


def handle_mcp_message_sent(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """Create the Tool and ToolCall of an agent's tool call, with everything above them
    and the ToolCall's initial State (see ``_ensure_mcp_tool_call``). Nothing here closes it."""
    _ensure_mcp_tool_call(event, event_attrs, registry)


def handle_mcp_message_received(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """The same as ``mcp.message.sent``: the message reaching the server carries the same
    input, sender and ``message.id``, so it lands on the same ToolCall (on another span)."""
    _ensure_mcp_tool_call(event, event_attrs, registry)


def handle_mcp_message_completed(
    event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry
) -> None:
    """The same nodes as ``mcp.message.sent``, then close the ToolCall and give it its final
    State (from ``message.output``) and Transition. ``success`` is ``not isError`` when the
    output says so. A repeated event adds nothing."""
    ensured = _ensure_mcp_tool_call(event, event_attrs, registry)
    if ensured is None:
        return
    tool_call, session_id, span_id, event_time, message_input = ensured

    if event_time > tool_call.endTime:
        tool_call.endTime = event_time  # type: ignore[attr-defined]
        tool_call.duration = (event_time - tool_call.startTime) * 1000.0  # type: ignore[attr-defined]
    output = str(event_attrs.get("message.output") or "")
    is_error = _output_is_error(output)
    if is_error is not None:
        tool_call.success = not is_error  # type: ignore[attr-defined]

    if registry.edge_target(hasFinalState, tool_call.id) is not None:
        return
    initial_id = registry.edge_target(hasInitialState, tool_call.id)
    if initial_id is None:  # _ensure_mcp_tool_call just made it
        return
    add_final_state_transition(
        registry, tool_call.id, session_id, span_id, initial_id, message_input, output
    )


def _output_is_error(message_output: str) -> bool | None:
    """The ``isError`` flag of a ``tools/call`` result in ``message.output``, if it has one."""
    try:
        parsed = json.loads(message_output)
    except ValueError:
        return None
    flag = parsed.get("isError") if isinstance(parsed, dict) else None
    return flag if isinstance(flag, bool) else None
