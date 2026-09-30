#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /agentic-protocols-metrics endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.connectors.base import Connector
from oxp.dependencies import get_db
from oxp.models.otel_traces import AgenticProtocolsMetricsResponse

router = APIRouter()


def _client(db: Connector = Depends(get_db)):  # noqa: B008
    """Lazily resolve the UI client from the current DB dependency."""
    return get_client(api_client=db)


@router.get(
    "/agentic-protocols-metrics",
    response_model=AgenticProtocolsMetricsResponse,
)
def get_agentic_protocols_metrics(
    application: str = Query(..., description="Application name"),
    start_time: str = Query("", description="Start time as Unix epoch (seconds)"),
    end_time: str = Query("", description="End time as Unix epoch (seconds)"),
    ui_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return SLIM agentic-protocol metrics for an application."""
    return ui_client.get_agentic_protocols_metrics(
        application=application,
        start_time=start_time or None,
        end_time=end_time or None,
    )
