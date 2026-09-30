#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Redis-backed caching utilities."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

import redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def make_cache_key(prefix: str, params: dict) -> str:
    """Return a deterministic Redis key for *prefix* + *params*."""
    payload = json.dumps(params, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"cache:{prefix}:{digest}"


def _serialize(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(value)


def cached(
    redis_client: redis.Redis,
    key: str,
    fetch: Callable[[], Any],
    ttl: int = 30,
    enabled: bool = True,
) -> Any:
    """Return the cached value for *key*, or call *fetch()*, cache and return it.

    When *enabled* is False, *fetch()* is called directly and Redis is not
    consulted.  Redis errors are caught and logged so that unavailability
    never breaks the API.
    """
    if not enabled:
        logger.debug("cache DISABLED — bypassing for %s", key)
        return fetch()

    try:
        raw = redis_client.get(key)
        if raw is not None:
            logger.debug("cache HIT  %s", key)
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis GET failed (%s) — bypassing cache", exc)

    result = fetch()

    try:
        redis_client.set(key, _serialize(result), ex=ttl)
        logger.debug("cache MISS %s (stored, ttl=%ds)", key, ttl)
    except Exception as exc:
        logger.warning("Redis SET failed (%s) — result not cached", exc)

    return result
