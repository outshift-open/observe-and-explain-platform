#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Event (OTel log record) dispatch, keyed on the ``event.name`` attribute."""

from __future__ import annotations

from typing import Any

from .handlers import (
    handle_a2a_agent_card,
    handle_a2a_message_received,
    handle_a2a_message_sent,
    handle_llm_completed,
    handle_llm_started,
    handle_mcp_message_completed,
    handle_mcp_message_received,
    handle_mcp_message_sent,
    handle_mcp_tools_discovered,
    handle_tool_completed,
    handle_tool_started,
    handle_topology_edge_updated,
    handle_topology_node_completed,
    handle_topology_node_started,
    handle_topology_session_completed,
    handle_topology_session_started,
)
from .registry import Registry


def dispatch_event(event: dict[str, Any], event_attrs: dict[str, Any], registry: Registry) -> bool:
    """Run the case for the event's ``event.name``. False if the name is unknown."""
    match str(event_attrs.get("event.name") or ""):
        case "topology.session.started":
            handle_topology_session_started(event, event_attrs, registry)
        case "topology.session.completed":
            handle_topology_session_completed(event, event_attrs, registry)
        case "topology.node.started":
            handle_topology_node_started(event, event_attrs, registry)
        case "topology.node.completed":
            handle_topology_node_completed(event, event_attrs, registry)
        case "topology.edge.updated":
            # TODO: handle topology.edge.updated
            #handle_topology_edge_updated(event, event_attrs, registry)
            pass
        case "llm.started":
            handle_llm_started(event, event_attrs, registry)
        case "llm.completed":
            handle_llm_completed(event, event_attrs, registry)
        case "tool.started":
            handle_tool_started(event, event_attrs, registry)
        case "tool.completed":
            handle_tool_completed(event, event_attrs, registry)
        case "a2a.message.sent":
            handle_a2a_message_sent(event, event_attrs, registry)
        case "a2a.message.received":
            handle_a2a_message_received(event, event_attrs, registry)
        case "a2a.agent_card":
            handle_a2a_agent_card(event, event_attrs, registry)
        case "slim.message.sent":
            # TODO: handle slim.message.sent
            pass
        case "slim.message.received":
            # TODO: handle slim.message.received
            pass
        case "mcp.message.sent":
            handle_mcp_message_sent(event, event_attrs, registry)
        case "mcp.message.received":
            handle_mcp_message_received(event, event_attrs, registry)
        case "mcp.message.completed":
            handle_mcp_message_completed(event, event_attrs, registry)
        case "mcp.tools.discovered":
            handle_mcp_tools_discovered(event, event_attrs, registry)
        case "mcp.tools.published":
            # TODO: handle mcp.tools.published
            pass
        case _:
            return False
    return True
