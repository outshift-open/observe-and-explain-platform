#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""One handler module per ``SpanName`` shape -- see build.py for dispatch."""

from .a2a import handle_a2a_agent_card, handle_a2a_message_received, handle_a2a_message_sent
from .agent import handle_agent
from .chat import handle_chat
from .graph import handle_graph
from .mcp import (
    handle_mcp_message_completed,
    handle_mcp_message_received,
    handle_mcp_message_sent,
    handle_mcp_tools_discovered,
)
from .llm import handle_llm_completed, handle_llm_started
from .session import handle_session_end, handle_session_start
from .tool import handle_tool
from .tool_events import handle_tool_completed, handle_tool_started
from .topology import (
    handle_topology_edge_updated,
    handle_topology_node_completed,
    handle_topology_node_started,
    handle_topology_session_completed,
    handle_topology_session_started,
)

__all__ = [
    "handle_a2a_agent_card",
    "handle_a2a_message_received",
    "handle_a2a_message_sent",
    "handle_agent",
    "handle_chat",
    "handle_graph",
    "handle_llm_completed",
    "handle_llm_started",
    "handle_mcp_message_completed",
    "handle_mcp_message_received",
    "handle_mcp_message_sent",
    "handle_mcp_tools_discovered",
    "handle_session_end",
    "handle_session_start",
    "handle_tool",
    "handle_tool_completed",
    "handle_tool_started",
    "handle_topology_edge_updated",
    "handle_topology_node_completed",
    "handle_topology_node_started",
    "handle_topology_session_completed",
    "handle_topology_session_started",
]
