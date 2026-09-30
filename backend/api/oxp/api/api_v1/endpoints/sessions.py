#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /sessions endpoint."""

from __future__ import annotations

from typing import Any, Optional

import redis as redis_lib
from fastapi import APIRouter, Depends, Query

from oxp.api.api_v1.endpoints.applications import _kg_client
from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_neo4j_db, get_redis
from oxp.models.otel_traces import (
    AgentConversationResponse,
    AgentDetailsResponse,
    GraphResponse,
    ImpactAssessmentResponse,
    LatentSpaceResponse,
    SessionSpansResponse,
    SessionSummaryResponse,
    TrajectoryResponse,
    WaterfallResponse,
)

router = APIRouter()


def _client(db: Connector = Depends(get_db)):  # noqa: B008
    """Lazily resolve the UI client from the current DB dependency."""
    return get_client(api_client=db)


def _graph_client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Resolve the Neo4j-backed client for execution graph queries."""
    return get_client(api_client=db)


@router.get("/count")
def get_sessions_count(
    application_id: str = Query(
        ..., description="MAS application name (e.g. noa-trip-planner-mas)"
    ),
    start_time: int | None = Query(
        default=None, description="Start of date range (unix epoch seconds)"
    ),
    end_time: int | None = Query(
        default=None, description="End of date range (unix epoch seconds)"
    ),
    ui_client=Depends(_graph_client),  # noqa: B008
) -> dict[str, int]:
    """Return session count for an application, optionally filtered by time range."""
    return ui_client.get_sessions_count(
        application_id=application_id,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/", response_model=SessionSummaryResponse)
def list_sessions(
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return ``session_id`` + ``timestamp`` for each session."""
    key = make_cache_key(
        "sessions:list",
        {"start": start_time, "end": end_time, "limit": limit, "offset": offset},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.list_sessions(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/sessions/{session_id}/agent/{agent_id}/details",
    response_model=AgentDetailsResponse,
)
def get_session_agent_details(
    session_id: str,
    agent_id: str,
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    key = make_cache_key(
        "sessions:agent_details",
        {"session": session_id, "agent": agent_id},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_agent_details(
            session_id=session_id, agent_id=agent_id
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/sessions/{session_id}/impact_assessment", response_model=ImpactAssessmentResponse
)
def get_session_impact_assessment(
    session_id: str,
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    key = make_cache_key(
        "sessions:impact_assessment",
        {"session": session_id},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_impact_assessment(session_id=session_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{session_id}/spans", response_model=SessionSpansResponse)
def get_session_spans(
    session_id: str,
    span_types: Optional[list[str]] = Query(None, alias="spanTypes"),
    limit: int = Query(500, ge=1),
    offset: int = Query(0, ge=0),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return traces/spans for a session with basic filters."""
    key = make_cache_key(
        "sessions:spans",
        {
            "session": session_id,
            "types": sorted(span_types or []),
            "limit": limit,
            "offset": offset,
            "order": order,
        },
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_spans(
            session_ids=[session_id],
            span_types=span_types,
            limit=limit,
            offset=offset,
            order=order,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{session_id}/timeline-waterfall", response_model=WaterfallResponse)
def get_session_timeline_waterfall(
    session_id: str,
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Build a waterfall span tree for a session."""
    key = make_cache_key("sessions:timeline_waterfall", {"session": session_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_timeline_waterfall(session_id=session_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{session_id}/timeline", response_model=GraphResponse)
def get_session_timeline(
    session_id: str,
    level: Optional[str] = Query(None),
    ui_client=Depends(_graph_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Build a state-machine timeline graph for a session."""
    key = make_cache_key("sessions:timeline", {"session": session_id, "level": level})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_timeline(
            session_id=session_id, level=level
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{session_id}/trajectory", response_model=TrajectoryResponse)
def get_session_trajectory(
    session_id: str,
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Trajectory."""
    key = make_cache_key("sessions:trajectory", {"session": session_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_trajectory(session_id=session_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{session_id}/execution-graph", response_model=GraphResponse)
def get_session_execution_graph(
    session_id: str,
    ui_client=Depends(_graph_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Build an execution_graph for a session."""
    key = make_cache_key("sessions:execution_graph", {"session": session_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_execution_graph(session_id=session_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{session_id}/conversation", response_model=AgentConversationResponse)
def get_session_conversation(
    session_id: str,
    ui_client=Depends(_graph_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return the ordered list of agent-level turns (the agent conversation) for a session."""
    key = make_cache_key("sessions:conversation", {"session": session_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_conversation(session_id=session_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{session_id}/latent-space", response_model=LatentSpaceResponse)
def get_session_latent_space(
    session_id: str,
    n_neighbors: int = Query(
        default=15,
        ge=2,
        le=200,
        description="UMAP n_neighbors parameter (controls local vs global structure, will be adjusted if larger than n_samples-1)",
    ),
    min_dist: float = Query(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="UMAP min_dist parameter (controls how tightly points cluster together)",
    ),
    ui_client=Depends(_graph_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """
    Get session states projected to 2D latent space using UMAP.

    Projects state embeddings from the agent hierarchy level to a 2D space
    for visualization. Uses UMAP with cosine distance metric.

    Nodes: States with x,y coordinates from UMAP projection
    Edges: Transitions between states (same as state machine graph)

    The embeddings are retrieved from Embedding nodes connected to State nodes
    via the represents relationship.

    Args:
        session_id: Session ID to fetch
        n_neighbors: UMAP n_neighbors (default 15, auto-adjusted if needed)
        min_dist: UMAP min_dist (default 0.1, controls clustering tightness)

    Returns:
        LatentSpaceResponse with nodes positioned in 2D space

    Example:
        GET /graph/latent-space/0c589041-888a-449d-983e-19c6af599494
        GET /graph/latent-space/0c589041-888a-449d-983e-19c6af599494?n_neighbors=10&min_dist=0.2
    """
    key = make_cache_key(
        "sessions:latent_space",
        {"session": session_id, "n_neighbors": n_neighbors, "min_dist": min_dist},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_session_latent_space(
            session_id=session_id,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )
