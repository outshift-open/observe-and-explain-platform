#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /live_topology endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from oxp.dependencies import ApplicationName

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.connectors.base import Connector
from oxp.dependencies import get_db
from oxp.models.live_topology import (
    LiveAgents,
    LiveTopologySessions,
    LiveTools,
    RealtimeTopologyResponse,
)

router = APIRouter()


def _client(db: Connector = Depends(get_db)):  # noqa: B008
    """Lazily resolve the live-topology client from the shared database dependency."""
    return get_client(api_client=db)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/{application_name}/sessions",
    response_model=LiveTopologySessions,
)
def get_live_topology_sessions(
    application_name: ApplicationName,
    lt_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return live topology sessions for a specific application."""
    return lt_client.get_live_topology_sessions(application_name=application_name)


@router.get(
    "/agents",
    response_model=LiveAgents,
)
def get_live_agents(
    lt_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return live agents"""
    return lt_client.get_live_agents()


@router.get(
    "/tools",
    response_model=LiveTools,
)
def get_live_tools(
    lt_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return live tools"""
    return lt_client.get_live_tools()


@router.get(
    "/sessions/{session_id}/topology",
    response_model=RealtimeTopologyResponse,
)
def get_realtime_topology(
    session_id: str,
    lt_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return a real-time topology graph for a session.

    Combines the static graph structure (nodes, edges) derived from the most
    recent ``*.graph`` span for the session with live status information sourced
    from ``topology.node.*`` and ``tool.*`` events in ``otel_logs``.

    Each node carries:
    - ``type``: ``"agent"`` or ``"tool"``
    - ``status``: ``"active"``, ``"completed"``, or ``"unknown"``
    - ``start_time`` / ``end_time``: ISO timestamps from live events
    - ``description``: agent description if available
    - ``data``: tool list for agent nodes that expose tools
    """
    return lt_client.get_realtime_topology(session_id=session_id)
