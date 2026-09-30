#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""KG-domain methods for :class:`LocalClient`."""

from __future__ import annotations

import logging

from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.query_builders import kg as kg_queries

logger = logging.getLogger(__name__)


class KGClient:
    """KG (knowledge-graph) operations mixed into :class:`LocalClient`."""

    db: Connector

    def get_state_by_session_id(self, session_id: str) -> dict:
        stmt = kg_queries.get_state_from_sessionId(session_id)
        try:
            rows = self.db.execute(stmt)
            return rows[0]["s"] if rows else {}
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get state for session '{session_id}': {exc}"
            ) from exc

    def get_embedding_by_session_id(self, session_id: str) -> list[float] | None:
        """Fetch the embedding vector for *session_id*, or *None* if absent."""
        query, params = kg_queries.get_embedding_by_session_id(session_id)
        try:
            rows = self.db.execute(query, params)
            if rows and rows[0].get("embedding"):
                return rows[0]["embedding"]
            return None
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get embedding for session '{session_id}': {exc}"
            ) from exc

    def get_neighbors(
        self,
        *,
        embedding: list[float],
        max_distance: float = 1.0,
        max_neighbors: int = 10,
        metric_names: list[str] | None = None,
        distance_metric: str = "cosine",
    ) -> list[dict]:
        """Return nearby sessions ranked by embedding distance."""
        query, params = kg_queries.neighbors_query(
            embedding=embedding,
            max_distance=max_distance,
            max_neighbors=max_neighbors,
            metric_names=metric_names,
            distance_metric=distance_metric,
        )
        try:
            return self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(f"Failed to get neighbors: {exc}") from exc
