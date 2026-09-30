#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /kg (knowledge-graph) endpoint."""

from __future__ import annotations

import json
from typing import Any

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Request

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.core.exceptions import NotFoundError, ValidationError
from oxp.dependencies import get_neo4j_db, get_redis
from oxp.models.kg import (
    NeighborSession,
    NeighborsRequest,
    NeighborsResponse,
)
from oxp.models.otel_traces import KGQueryRequest, KGQueryResponse

router = APIRouter()


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Lazily resolve the KG client from the shared Neo4j dependency."""
    return get_client(api_client=db)


@router.get("/get_state_by_session_id/{session_id}")
def get_state_by_session_id(
    session_id: str,
    kg_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> dict:
    """Return the state associated with a given session ID."""
    key = make_cache_key("kg:state", {"session": session_id})
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: kg_client.get_state_by_session_id(session_id),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.post("/neighbors", response_model=NeighborsResponse)
def get_neighbors(
    body: NeighborsRequest, kg_client=Depends(_client)
) -> NeighborsResponse:  # noqa: B008
    """Find sessions whose embedding is close to a given session or vector.

    Provide **either** ``session_id`` (to look up the embedding from the KG)
    **or** ``embedding_vector`` (to query directly with a raw vector).
    """
    # ── validate input ────────────────────────────────────────────────────
    if body.session_id is None and body.embedding_vector is None:
        raise ValidationError(
            "Either 'session_id' or 'embedding_vector' must be provided.",
        )

    # ── resolve embedding vector ──────────────────────────────────────────
    embedding = body.embedding_vector
    if embedding is None:
        embedding = kg_client.get_embedding_by_session_id(body.session_id)
        if embedding is None:
            raise NotFoundError(
                f"No embedding found for session '{body.session_id}'.",
            )

    # ── query Neo4j ───────────────────────────────────────────────────────
    rows = kg_client.get_neighbors(
        embedding=embedding,
        max_distance=body.max_distance,
        max_neighbors=body.max_neighbors,
        metric_names=body.metric_names,
        distance_metric=body.distance_metric,
    )

    # ── build response ────────────────────────────────────────────────────
    neighbors: list[NeighborSession] = []
    for row in rows:
        # Flatten metric nodes [{metricName: ..., metricResult: ...}, ...]
        # into a simple {name: value} dict.
        raw_metrics = row.get("metrics") or []
        metrics_dict = {}
        for m in raw_metrics:
            if not m or "metricName" not in m:
                continue
            value = None
            result_str = m.get("metricResult")
            if isinstance(result_str, (int, float)) and not isinstance(
                result_str, bool
            ):
                value = result_str
            elif result_str:
                try:
                    parsed = json.loads(result_str)
                    if isinstance(parsed, dict):
                        value = parsed.get("value")
                    elif isinstance(parsed, (int, float)) and not isinstance(
                        parsed, bool
                    ):
                        value = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            metrics_dict[m["metricName"]] = value

        neighbors.append(
            NeighborSession(
                session_id=row["sessionId"],
                distance=row["distance"],
                metrics=metrics_dict or None,
                embedding=row.get("embedding"),
                execution_graph=row.get("executionGraph"),
            )
        )

    return NeighborsResponse(neighbors=neighbors)


@router.get("/info")
def kg_info(request: Request, kg_client=Depends(_client)) -> Any:  # noqa: B008
    """Return descriptive information about this endpoint."""
    return kg_client.info(domain="kg")


# ── Generic KG node query (used by remote OXPApiRawProvider) ──────────────


@router.post("/query", response_model=KGQueryResponse)
def query_kg_nodes(body: KGQueryRequest) -> Any:
    """Execute a parameterized node query against the knowledge graph.

    Translates the request into a Cypher query identical to
    :meth:`Neo4jRawProvider.query_nodes`.  Intended for use by the
    ``OXPApiRawProvider`` in ``mce-client`` so that compute workers
    don't need a direct Neo4j connection.
    """
    from oxp.dependencies import get_neo4j_db

    db = next(get_neo4j_db())

    label_part = (
        f":{body.entity_type}" if body.entity_type and body.entity_type != "*" else ""
    )
    clauses = [f"MATCH (n{label_part})"]
    params: dict = {}

    where_parts: list[str] = []
    if body.filters:
        for k, v in body.filters.items():
            pk = f"filter_{k}"
            where_parts.append(
                f"n.{k} IN ${pk}" if isinstance(v, list) else f"n.{k} = ${pk}"
            )
            params[pk] = v
    if body.where_clause:
        wc = body.where_clause.strip()
        if not wc.lower().startswith("where"):
            where_parts.append(f"({wc})")
    if where_parts:
        clauses.append("WHERE " + " AND ".join(where_parts))

    if body.columns and body.columns != ["*"]:
        ret_parts = []
        for col in body.columns:
            if "(" in col or " AS " in col.upper() or "." in col:
                ret_parts.append(col)
            else:
                ret_parts.append(f"n.{col} AS {col}")
        clauses.append("RETURN " + ", ".join(ret_parts))
    else:
        clauses.append("RETURN n")

    if body.order_by:
        sort_parts = []
        for field in body.order_by:
            direction = "DESC" if field.startswith("-") else "ASC"
            f_clean = field.lstrip("-")
            if "." not in f_clean:
                f_clean = f"n.{f_clean}"
            sort_parts.append(f"{f_clean} {direction}")
        clauses.append("ORDER BY " + ", ".join(sort_parts))

    if body.limit:
        clauses.append(f"LIMIT {int(body.limit)}")

    cypher = "\n".join(clauses)

    try:
        with db.driver.session() as s:
            result = s.run(cypher, **params)
            rows = []
            for record in result:
                row = dict(record)
                if "n" in row and hasattr(row["n"], "items") and len(row) == 1:
                    rows.append(dict(row["n"].items()))
                else:
                    safe: dict = {}
                    for k, v in row.items():
                        safe[k] = dict(v.items()) if hasattr(v, "items") else v
                    rows.append(safe)
        return KGQueryResponse(results=rows, total=len(rows))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
