#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Legacy route migrations preserved at their historical API paths."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.connectors.base import Connector
from oxp.dependencies import get_neo4j_db

router = APIRouter()


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Resolve a Neo4j-backed client for migrated legacy routes."""
    return get_client(api_client=db)


@router.get("/session-reasoning-path", tags=["symbolic"])
def get_session_reasoning_path(
    session_id: str = Query(
        ..., description="Session ID to build the reasoning path for"
    ),
    symbolic_client=Depends(_client),  # noqa: B008
) -> dict[str, Any]:
    return symbolic_client.get_session_reasoning_path(session_id=session_id)


@router.get("/application-reasoning-path", tags=["symbolic"])
def get_application_reasoning_path(
    mas_name: str = Query(..., description="MAS name (e.g. noa-trip-planner-mas)"),
    symbolic_client=Depends(_client),  # noqa: B008
) -> dict[str, Any]:
    return symbolic_client.get_application_reasoning_path(mas_name=mas_name)


@router.get("/timeline-reasoning-path", tags=["symbolic"])
def get_timeline_reasoning_path(
    session_id: str = Query(..., description="Session ID"),
    symbolic_client=Depends(_client),  # noqa: B008
) -> dict[str, Any]:
    return symbolic_client.get_timeline_reasoning_path(session_id=session_id)


@router.get("/applications-with-stateful-eval", tags=["stateful-eval"])
def get_applications_with_stateful_eval(
    start_time: int | None = Query(
        default=None, description="Start of date range (unix epoch seconds)"
    ),
    end_time: int | None = Query(
        default=None, description="End of date range (unix epoch seconds)"
    ),
    symbolic_client=Depends(_client),  # noqa: B008
) -> list[dict[str, Any]]:
    return symbolic_client.get_applications_with_stateful_eval(
        start_time=start_time,
        end_time=end_time,
    )
