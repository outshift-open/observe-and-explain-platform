#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for waste estimation and related insights endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from oxp.connectors.base import Connector
from oxp.dependencies import ApplicationName, get_neo4j_db
from oxp.query_builders import waste_estimation as waste_qb

router = APIRouter()


def _db(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Resolve the shared Neo4j connector dependency."""
    return db


@router.get("/waste-estimations", tags=["waste-estimation"])
def get_waste_estimations(
    limit: int = Query(default=1000, ge=1, le=1000),
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return WasteEstimation nodes from Neo4j."""
    query, params = waste_qb.waste_estimations_query(limit=limit)
    rows = db.execute(query, params)
    return [row["waste_estimation"] for row in rows]


@router.get("/{application_name}/top-wasteful-sessions", tags=["waste-estimation"])
def get_top_wasteful_sessions(
    application_name: ApplicationName,
    threshold: float = Query(default=0, description="Minimum estimatedWaste value"),
    limit: int = Query(default=25, ge=1, le=1000),
    start_time: int | None = Query(
        default=None, description="Start of date range (unix epoch seconds)"
    ),
    end_time: int | None = Query(
        default=None, description="End of date range (unix epoch seconds)"
    ),
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return wasteful sessions and semantic-group information."""
    query, params = waste_qb.top_wasteful_sessions_query(
        threshold=threshold,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        application_name=application_name,
    )
    rows = db.execute(query, params)
    return [
        {
            **row["waste_estimation"],
            "semanticGroup": row.get("semanticGroup"),
            "semanticGroupId": row.get("semanticGroupId"),
        }
        for row in rows
    ]


@router.get("/waste-estimations-semantic-groups", tags=["waste-estimation"])
def get_waste_estimations_by_semantic_group(
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return the sum of WasteEstimation actualCost per leaf semantic group."""
    query, params = waste_qb.waste_estimations_semantic_groups_query()
    return db.execute(query, params)


@router.get(
    "/{application_name}/cost-efficiency-groupped-sessions",
    tags=["waste-estimation"],
)
def get_cost_efficiency_grouped_sessions(
    application_name: ApplicationName,
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return costEfficiency per session with its semantic group."""
    query, params = waste_qb.cost_efficiency_grouped_sessions_query(
        application_name=application_name,
    )
    return db.execute(query, params)


@router.get("/wasted-resources-features-score", tags=["waste-estimation"])
def get_wasted_resources_features_score(
    session_id: str = Query(..., description="Session ID to look up"),
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return top-5 and bottom-5 feature scores by rank per quality target."""
    query, params = waste_qb.wasted_resources_features_score_query(
        session_id=session_id
    )
    rows = db.execute(query, params)
    return [row["item"] for row in rows]


@router.get("/{application_name}/semantic-groups-insights", tags=["insights"])
def get_semantic_groups_insights(
    application_name: ApplicationName,
    start_time: int | None = Query(
        default=None, description="Start of date range (unix epoch seconds)"
    ),
    end_time: int | None = Query(
        default=None, description="End of date range (unix epoch seconds)"
    ),
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return insights linked to semantic groups ordered by priority desc."""
    query, params = waste_qb.semantic_groups_insights_query(
        start_time=start_time,
        end_time=end_time,
        application_name=application_name,
    )
    return db.execute(query, params)


@router.get("/{application_name}/sessions-insights", tags=["insights"])
def get_session_insights(
    application_name: ApplicationName,
    start_time: int | None = Query(
        default=None, description="Start of date range (unix epoch seconds)"
    ),
    end_time: int | None = Query(
        default=None, description="End of date range (unix epoch seconds)"
    ),
    semantic_group_id: str | None = Query(
        default=None, description="Filter by semantic group ID"
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=1000,
        description="Maximum number of results to return",
    ),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return insights linked to sessions, ordered by priority asc."""
    query, params = waste_qb.sessions_insights_query(
        start_time=start_time,
        end_time=end_time,
        semantic_group_id=semantic_group_id,
        limit=limit,
        offset=offset,
        application_name=application_name,
    )
    return db.execute(query, params)


@router.get("/session-insights", tags=["insights"])
def get_single_session_insights(
    session_id: str = Query(..., description="Session ID to look up insights for"),
    start_time: int | None = Query(
        default=None, description="Start of date range (unix epoch seconds)"
    ),
    end_time: int | None = Query(
        default=None, description="End of date range (unix epoch seconds)"
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=1000,
        description="Maximum number of results to return",
    ),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    db: Connector = Depends(_db),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return insights for a specific session, ordered by priority asc."""
    query, params = waste_qb.session_insights_query(
        session_id=session_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return db.execute(query, params)
