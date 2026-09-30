#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /labels endpoint.

Endpoints
---------
GET    /labels/{session_id}   — Retrieve the label for a session.
PUT    /labels/{session_id}   — Create or update a label for a session.
DELETE /labels/{session_id}   — Remove the label for a session.
"""

from __future__ import annotations

from typing import Any

import redis as redis_lib
from fastapi import APIRouter, Depends

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_db, get_redis
from oxp.models.otel_traces import (
    LabelDeleteResponse,
    LabelPutRequest,
    LabelResponse,
)

router = APIRouter()


def _client(db: Connector = Depends(get_db)):  # noqa: B008
    """Lazily resolve the client from the current DB dependency."""
    return get_client(api_client=db)


@router.get("/{session_id}", response_model=LabelResponse)
def get_label(
    session_id: str,
    client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return the label for *session_id* (or ``null`` if none exists)."""
    key = make_cache_key("labels:session", {"session": session_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: client.get_label(session_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.put("/{session_id}", response_model=LabelResponse)
def put_label(
    session_id: str,
    body: LabelPutRequest,
    client=Depends(_client),  # noqa: B008
) -> Any:
    """Create or update the label for *session_id*."""
    return client.put_label(session_id, body)


@router.delete("/{session_id}", response_model=LabelDeleteResponse)
def delete_label(
    session_id: str,
    client=Depends(_client),  # noqa: B008
) -> Any:
    """Delete the label for *session_id*."""
    return client.delete_label(session_id)
