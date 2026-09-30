#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /concepts endpoint.

Endpoints
---------
GET  /concepts/{app_id}
    Read symbols / concepts for neurosymbolic analysis for an application.
POST /concepts/{app_id}
    Write concepts to an application.

GET  /concepts/{app_id}/sessions/{session_id}/spans/{span_id}
    Read symbols / concepts for a specific span.
POST /concepts/{app_id}/sessions/{session_id}/spans/{span_id}
    Write concepts to a span.
"""

from __future__ import annotations

from typing import Any

import redis as redis_lib
from fastapi import APIRouter, Depends

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_neo4j_db, get_redis
from oxp.models.otel_traces import (
    ConceptsResponse,
    ConceptsWriteRequest,
    ConceptsWriteResponse,
    SpanConceptsResponse,
    SpanConceptsWriteRequest,
)

router = APIRouter()


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Lazily resolve the concepts client from the shared Neo4j dependency."""
    return get_client(api_client=db)


# ── App-level concepts ────────────────────────────────────────────────────────


@router.get("/{app_id}", response_model=ConceptsResponse)
def get_app_concepts(
    app_id: str,
    concepts_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return all concepts for *app_id*."""
    key = make_cache_key("concepts:app", {"app": app_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: concepts_client.get_app_concepts(app_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.post("/{app_id}", response_model=ConceptsWriteResponse)
def post_app_concepts(
    app_id: str, body: ConceptsWriteRequest, concepts_client=Depends(_client)
) -> Any:  # noqa: B008
    """Write concepts to an application in the knowledge graph."""
    result = concepts_client.write_app_concepts(
        app_id,
        concepts=[c.model_dump() for c in body.concepts],
    )
    return ConceptsWriteResponse(**result)


# ── Span-level concepts ──────────────────────────────────────────────────────


@router.get(
    "/{app_id}/sessions/{session_id}/spans/{span_id}",
    response_model=SpanConceptsResponse,
)
def get_span_concepts(
    app_id: str,
    session_id: str,
    span_id: str,
    concepts_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return concepts for a specific span."""
    key = make_cache_key(
        "concepts:span", {"app": app_id, "session": session_id, "span": span_id}
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: concepts_client.get_span_concepts(app_id, session_id, span_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.post(
    "/{app_id}/sessions/{session_id}/spans/{span_id}",
    response_model=ConceptsWriteResponse,
)
def post_span_concepts(
    app_id: str,
    session_id: str,
    span_id: str,
    body: SpanConceptsWriteRequest,
    concepts_client=Depends(_client),  # noqa: B008
) -> Any:
    """Write concepts to a span in the knowledge graph."""
    result = concepts_client.write_span_concepts(
        app_id,
        session_id,
        span_id,
        concepts=[c.model_dump() for c in body.concepts],
    )
    return ConceptsWriteResponse(**result)
