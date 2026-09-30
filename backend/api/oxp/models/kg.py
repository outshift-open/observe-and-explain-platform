#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Optional

from pydantic import BaseModel, Field


class NeighborsRequest(BaseModel):
    """Request body for the ``POST /kg/neighbors`` endpoint."""

    session_id: Optional[str] = Field(
        None, description="Session whose embedding is used as the query vector"
    )
    embedding_vector: Optional[list[float]] = Field(
        None, description="Raw embedding vector to use as the query vector"
    )
    metric_names: Optional[list[str]] = Field(
        None,
        description="If provided, only return metrics whose name is in this list",
    )
    max_distance: float = Field(
        1.0, ge=0.0, description="Maximum distance (1 − similarity) to a neighbor"
    )
    max_neighbors: int = Field(
        10, ge=1, description="Maximum number of returned neighbor sessions"
    )
    distance_metric: str = Field(
        "cosine", description="Distance metric: 'cosine' or 'euclidean'"
    )
    embedding_type: Optional[str] = Field(
        None, description="Embedding algorithm / type to select"
    )


class NeighborSession(BaseModel):
    """A single neighbor session returned by the neighbors endpoint."""

    session_id: str
    distance: float
    metrics: Optional[dict] = None
    embedding: Optional[list[float]] = None
    execution_graph: Optional[dict] = None


class NeighborsResponse(BaseModel):
    """Response body for ``POST /kg/neighbors``."""

    neighbors: list[NeighborSession]
