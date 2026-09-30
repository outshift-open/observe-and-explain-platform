#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /semanticgroups endpoint."""

from __future__ import annotations

from typing import Any

import redis as redis_lib
from fastapi import APIRouter, Depends, Query

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_neo4j_db, get_redis
from oxp.models.otel_traces import (
    SemanticgroupAnomalyResponse,
    SemanticgroupConsistencyResponse,
    SemanticgroupDetailsResponse,
    SemanticgroupNormalBehaviorResponse,
)

router = APIRouter()


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Lazily resolve the semantic-groups client from the shared Neo4j dependency."""
    return get_client(api_client=db)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/{semanticgroup_id}/normal_behavior",
    response_model=SemanticgroupNormalBehaviorResponse,
)
def get_semanticgroup_normal_behavior(
    semanticgroup_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    sg_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return normal behaviour report for a semantic group."""
    key = make_cache_key(
        "semanticgroups:normal_behavior",
        {"sg": semanticgroup_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: sg_client.get_semanticgroup_normal_behavior(
            semanticgroup_id=semanticgroup_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/{semanticgroup_id}/consistency_report",
    response_model=SemanticgroupConsistencyResponse,
)
def get_semanticgroup_consistency_report(
    semanticgroup_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    sg_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return consistency report for a semantic group."""
    key = make_cache_key(
        "semanticgroups:consistency_report",
        {"sg": semanticgroup_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: sg_client.get_semanticgroup_consistency_report(
            semanticgroup_id=semanticgroup_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/{semanticgroup_id}/anomaly_report", response_model=SemanticgroupAnomalyResponse
)
def get_semanticgroup_anomaly_report(
    semanticgroup_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    sg_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return anomaly report for a semantic group."""
    key = make_cache_key(
        "semanticgroups:anomaly_report",
        {"sg": semanticgroup_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: sg_client.get_semanticgroup_anomaly_report(
            semanticgroup_id=semanticgroup_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/{semanticgroup_id}", response_model=SemanticgroupDetailsResponse)
def get_semanticgroup_details(
    semanticgroup_id: str,
    start_time: str = Query(""),
    end_time: str = Query(""),
    sg_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return details for a semantic group."""
    key = make_cache_key(
        "semanticgroups:details",
        {"sg": semanticgroup_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: sg_client.get_semanticgroup_details(
            semanticgroup_id=semanticgroup_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )
