#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Any, List, Literal, Optional

from pydantic import BaseModel


class LiveTopologySessions(BaseModel):
    """Represents the live topology sessions response model."""

    class Session(BaseModel):
        """Represents a single session in the live topology."""

        session_id: str
        start_time: str
        end_time: Optional[str]
        status: Literal["active", "completed"]

    sessions: List[Session]


class LiveAgents(BaseModel):
    """Represents the live agents response model."""

    class Agent(BaseModel):
        """Represents a single agent node in the live topology."""

        agent_name: str
        start_time: str
        end_time: Optional[str]
        status: Literal["active", "completed"]

    agents: List[Agent]


class LiveTools(BaseModel):
    """Represents the live tools response model."""

    class Tool(BaseModel):
        """Represents a single tool invocation in the live topology."""

        tool_name: str
        start_time: str
        end_time: Optional[str]
        status: Literal["active", "completed"]

    tools: List[Tool]


class RealtimeTopologyNode(BaseModel):
    """A node in the real-time topology graph (agent or tool)."""

    id: str
    name: str
    type: Literal["agent", "tool", "unknown"] = "unknown"
    status: Literal["active", "completed", "unknown"] = "unknown"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None
    data: Optional[Any] = None


class RealtimeTopologyEdge(BaseModel):
    """A directed edge between two nodes in the real-time topology graph."""

    source: str
    target: str
    label: Optional[str] = None


class RealtimeTopologyResponse(BaseModel):
    """Real-time topology graph built from otel_logs topology events."""

    session_id: str
    session_status: Literal["active", "completed", "unknown"] = "unknown"
    nodes: List[RealtimeTopologyNode] = []
    edges: List[RealtimeTopologyEdge] = []
    last_updated: Optional[str] = None
