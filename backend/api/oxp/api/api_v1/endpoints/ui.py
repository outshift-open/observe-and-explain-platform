#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /ui endpoint."""

from __future__ import annotations

from typing import Any

import redis as redis_lib
from fastapi import APIRouter, Depends, Query, Request

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_redis
from oxp.models.otel_traces import (
    ApplicationNamesResponse,
    ApplicationsResponse,
)

router = APIRouter()


def _client(db: Connector = Depends(get_db)):  # noqa: B008
    """Lazily resolve the UI client from the current DB dependency."""
    return get_client(api_client=db)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/info")
def ui_info(request: Request, ui_client=Depends(_client)) -> Any:  # noqa: B008
    """Return descriptive information about this endpoint."""
    return ui_client.info(domain="ui")


@router.get("/applications/names", response_model=ApplicationNamesResponse)
def get_application_names(
    start_time: str = Query(""),
    end_time: str = Query(""),
    limit: int = Query(50),
    offset: int = Query(0),
    ui_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return the list of known applications."""
    return ui_client.get_application_names(
        start_time=start_time or None,
        end_time=end_time or None,
        limit=limit,
        offset=offset,
    )


@router.get("/applications", response_model=ApplicationsResponse)
def get_applications(
    start_time: str = Query(""),
    end_time: str = Query(""),
    limit: int = Query(50),
    offset: int = Query(0),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return the list of known applications (cached)."""
    key = make_cache_key(
        "ui:applications",
        {"start": start_time, "end": end_time, "limit": limit, "offset": offset},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_applications(
            start_time=start_time or None,
            end_time=end_time or None,
            limit=limit,
            offset=offset,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/applications/multiquery", response_model=ApplicationsResponse)
def get_applications_multiquery(
    start_time: str = Query(""),
    end_time: str = Query(""),
    limit: int = Query(50),
    offset: int = Query(0),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return the list of known applications (cached)."""
    key = make_cache_key(
        "ui:applications:multiquery",
        {"start": start_time, "end": end_time, "limit": limit, "offset": offset},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_applications_multiquery(
            start_time=start_time or None,
            end_time=end_time or None,
            limit=limit,
            offset=offset,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get(
    "/applications-from-clickhouse",
    response_model=ApplicationsResponse,
)
def get_applications_from_clickhouse(
    start_time: str = Query(""),
    end_time: str = Query(""),
    limit: int = Query(50),
    offset: int = Query(0),
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return the list of known applications from ClickHouse."""
    key = make_cache_key(
        "ui:applications:from-clickhouse",
        {"start": start_time, "end": end_time, "limit": limit, "offset": offset},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_applications_from_clickhouse(
            start_time=start_time or None,
            end_time=end_time or None,
            limit=limit,
            offset=offset,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )
