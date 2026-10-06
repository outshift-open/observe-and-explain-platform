#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /applications endpoint."""

from __future__ import annotations

from typing import Any

import redis as redis_lib
from fastapi import APIRouter, Depends, Query

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_neo4j_db, get_redis
from oxp.models.otel_traces import (
    ApplicationAgentToolsResponse,
    CollectByApplicationResponse,
    ImpactAssessmentResponse,
    MonitorApplicationLevelData,
    MonitorByApplicationResponse,
    SemanticgroupsResponse,
)

router = APIRouter()


def _client(db: Connector = Depends(get_db)):  # noqa: B008
    """Lazily resolve the UI client from the current DB dependency."""
    return get_client(api_client=db)


def _kg_client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Resolve a client backed by Neo4j for KG-only endpoints."""
    return get_client(api_client=db)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/{application_id}/agents", response_model=MonitorByApplicationResponse)
def application_agents(
    application_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return per-agent monitoring data for an application."""
    key = make_cache_key(
        "applications:agents",
        {"app": application_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_agents(
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{application_id}/sessions", response_model=CollectByApplicationResponse)
def application_sessions(
    application_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return session-level data for an application."""
    key = make_cache_key(
        "applications:sessions",
        {"app": application_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_sessions(
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/{application_id}/sessions_with_stateful_eval_multi_query",
    response_model=CollectByApplicationResponse,
)
def application_sessions_with_stateful_eval_multi_query(
    application_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return session-level data for an application including statefulEval metric."""
    key = make_cache_key(
        "applications:sessions_with_stateful_eval_multi_query",
        {"app": application_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_sessions_with_stateful_eval_multi_query(
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/{application_id}/sessions_with_stateful_eval",
    response_model=CollectByApplicationResponse,
)
def application_sessions_with_stateful_eval(
    application_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    semantic_group_id: str = Query(""),
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return session-level data using one query for statefulEval + metrics."""
    key = make_cache_key(
        "applications:sessions_with_stateful_eval",
        {
            "app": application_id,
            "start": start_time,
            "end": end_time,
            "semantic_group": semantic_group_id,
        },
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_sessions_with_stateful_eval(
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
            semantic_group_id=semantic_group_id,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{application_id}/agent/{agent_id}/charts")
def application_charts(
    application_id: str,
    agent_id: str,
    chart_type: str = Query(...),
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return chart data for an application by chart type."""
    key = make_cache_key(
        "applications:charts",
        {
            "app": application_id,
            "agent": agent_id,
            "chart": chart_type,
            "start": start_time,
            "end": end_time,
        },
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_charts(
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{application_id}/topology")
def application_topology(
    application_id: str,
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return the topology for an application."""
    key = make_cache_key(
        "applications:topology",
        {"app": application_id},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_topology(
            application_id=application_id,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/{application_id}/agent-tools", response_model=ApplicationAgentToolsResponse
)
def application_agent_tools(
    application_id: str,
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return each agent's tools for an application.

    Sourced from the knowledge graph's structural ``Agent -[:usesTool]->
    Tool`` edges rather than the topology endpoint's self-reported
    ``gen_ai.ioa.graph`` span attribute, which is not guaranteed to
    include tool nodes.
    """
    key = make_cache_key(
        "applications:agent_tools",
        {"app": application_id},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_agent_tools(
            application_id=application_id,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/{application_id}/semanticgroups/table", response_model=SemanticgroupsResponse
)
def get_application_semanticgroups_table(
    application_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return application-level monitoring data."""
    key = make_cache_key(
        "applications:semanticgroups:table",
        {"app": application_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_semanticgroups_table(
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{application_id}/semanticgroups", response_model=SemanticgroupsResponse)
def get_application_semanticgroups(
    application_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return application-level monitoring data."""
    key = make_cache_key(
        "applications:semanticgroups",
        {"app": application_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_semanticgroups(
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/{application_id}/semanticgroups/{semanticgroup_id}/impact_assessment",
    response_model=ImpactAssessmentResponse,
)
def get_application_semanticgroup_impact_assessment(
    application_id: str,
    semanticgroup_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_kg_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return impact assessment for a semantic group."""
    key = make_cache_key(
        "applications:semanticgroups:impact",
        {
            "app": application_id,
            "sg": semanticgroup_id,
            "start": start_time,
            "end": end_time,
        },
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_semanticgroup_impact_assessment(
            application_id=application_id,
            semanticgroup_id=semanticgroup_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{application_id}", response_model=MonitorApplicationLevelData)
def application_details(
    application_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return application-level monitoring data."""
    key = make_cache_key(
        "applications:details",
        {"app": application_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_application_details(
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )
