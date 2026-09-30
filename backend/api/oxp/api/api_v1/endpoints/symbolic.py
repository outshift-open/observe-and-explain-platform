#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /symbolic endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.connectors.base import Connector
from oxp.dependencies import get_neo4j_db
from oxp.models.otel_traces import (
    SymbolicModelDeleteResponse,
    SymbolicModelResponse,
    SymbolicModelsResponse,
    SymbolicModelWriteRequest,
    SymbolicModelWriteResponse,
    SymbolicSessionStateResponse,
    SymbolicSessionValuesResponse,
    SymbolicSessionValuesWriteRequest,
    SymbolicSessionValuesWriteResponse,
    SymbolicVariablesResponse,
    SymbolicVariablesWriteRequest,
    SymbolicVariablesWriteResponse,
)

router = APIRouter()


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Resolve a Neo4j-backed client for symbolic endpoints."""
    return get_client(api_client=db)


@router.get(
    "/applications/{application_id}/variables", response_model=SymbolicVariablesResponse
)
def get_application_symbolic_variables(
    application_id: str,
    model_id: str | None = Query(None, alias="modelId"),
    evaluation_only: bool = Query(False, alias="evaluationOnly"),
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return symbolic variable definitions for an application model."""
    return symbolic_client.get_application_symbolic_variables(
        application_id,
        model_id=model_id,
        evaluation_only=evaluation_only,
    )


@router.post(
    "/applications/{application_id}/variables",
    response_model=SymbolicVariablesWriteResponse,
)
def post_application_symbolic_variables(
    application_id: str,
    body: SymbolicVariablesWriteRequest,
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Upsert symbolic variable definitions for an application."""
    return symbolic_client.write_application_symbolic_variables(
        application_id,
        model_id=body.modelId,
        variables=[variable.model_dump() for variable in body.variables],
        dependencies=[dependency.model_dump() for dependency in body.dependencies],
        min_discriminative_score=body.minDiscriminativeScore,
    )


@router.post(
    "/applications/{application_id}/models", response_model=SymbolicModelWriteResponse
)
def post_application_symbolic_model(
    application_id: str,
    body: SymbolicModelWriteRequest,
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Create or update symbolic model metadata for an application."""
    return symbolic_client.write_application_symbolic_model(
        application_id,
        model_id=body.modelId,
        version=body.version,
        is_active=body.isActive,
        model_name=body.modelName,
        task_description=body.taskDescription,
        updated_at=body.updatedAt,
        created_at=body.createdAt,
    )


@router.get(
    "/applications/{application_id}/models", response_model=SymbolicModelsResponse
)
def get_application_symbolic_models(
    application_id: str,
    active_only: bool = Query(False, alias="activeOnly"),
    latest: bool = Query(False),
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return symbolic models attached to an application.

    Default returns all models (active and inactive).
    Set ``activeOnly=true`` to filter to active models.
    """
    return symbolic_client.get_application_symbolic_models(
        application_id,
        active_only=active_only,
        latest=latest,
    )


@router.get(
    "/applications/{application_id}/models/{model_id}",
    response_model=SymbolicModelResponse,
)
def get_application_symbolic_model(
    application_id: str,
    model_id: str,
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return one symbolic model by identifier for an application."""
    return symbolic_client.get_application_symbolic_model(application_id, model_id)


@router.delete(
    "/applications/{application_id}/models/{model_id}",
    response_model=SymbolicModelDeleteResponse,
)
def delete_application_symbolic_model(
    application_id: str,
    model_id: str,
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Delete one symbolic model for an application."""
    return symbolic_client.delete_application_symbolic_model(application_id, model_id)


@router.post(
    "/sessions/{session_id}/values", response_model=SymbolicSessionValuesWriteResponse
)
def post_session_symbolic_values(
    session_id: str,
    body: SymbolicSessionValuesWriteRequest,
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Append symbolic value changes derived during session inference."""
    return symbolic_client.write_session_symbolic_values(
        session_id,
        model_id=body.modelId,
        values=[value.model_dump() for value in body.values],
    )


@router.get(
    "/sessions/{session_id}/values", response_model=SymbolicSessionValuesResponse
)
def get_session_symbolic_values(
    session_id: str,
    model_id: str | None = Query(None, alias="modelId"),
    variable_id: str | None = Query(None, alias="variableId"),
    variable_name: str | None = Query(None, alias="variableName"),
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return symbolic value events for a session."""
    return symbolic_client.get_session_symbolic_values(
        session_id,
        model_id=model_id,
        variable_id=variable_id,
        variable_name=variable_name,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}/state", response_model=SymbolicSessionStateResponse)
def get_session_symbolic_state(
    session_id: str,
    symbolic_client=Depends(_client),  # noqa: B008
) -> Any:
    """Return the final symbolic state for a session."""
    return symbolic_client.get_session_symbolic_state(session_id)
