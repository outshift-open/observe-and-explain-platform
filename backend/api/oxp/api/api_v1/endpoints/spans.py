#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /spans endpoint."""

from __future__ import annotations

from typing import Any

import redis as redis_lib
from fastapi import APIRouter, Depends

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_redis
from oxp.models.otel_traces import SpanDetailsResponse

router = APIRouter()


def _client(db: Connector = Depends(get_db)):  # noqa: B008
    """Lazily resolve the UI client from the current DB dependency."""
    return get_client(api_client=db)


@router.get("/{span_id}", response_model=SpanDetailsResponse)
def get_span_details(
    span_id: str,
    ui_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return detailed information about a single span."""
    key = make_cache_key("spans:details", {"span": span_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: ui_client.get_spans(span_id=span_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )
