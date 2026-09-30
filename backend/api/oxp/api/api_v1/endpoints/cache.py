#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for cache management endpoints.

Endpoints
---------
DELETE /cache
    Invalidate all Redis cache entries (keys matching ``cache:*``).
"""

from __future__ import annotations

import logging

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from oxp.dependencies import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


class CacheInvalidationResponse(BaseModel):
    deleted: int
    message: str


@router.delete("/", response_model=CacheInvalidationResponse)
def invalidate_cache(
    redis_client: redis.Redis = Depends(get_redis),
) -> CacheInvalidationResponse:
    """Delete all Redis keys under the ``cache:*`` namespace."""
    try:
        keys = redis_client.keys("cache:*")
        deleted = len(keys)
        if keys:
            redis_client.delete(*keys)
        logger.info("Cache invalidated — %d key(s) deleted", deleted)
        return CacheInvalidationResponse(
            deleted=deleted,
            message=f"Cache invalidated: {deleted} key(s) deleted.",
        )
    except Exception as exc:
        logger.error("Cache invalidation failed: %s", exc)
        raise HTTPException(
            status_code=503, detail=f"Cache invalidation failed: {exc}"
        ) from exc
