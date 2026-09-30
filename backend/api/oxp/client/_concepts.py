#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Concepts-domain methods for :class:`LocalClient`.

These methods query the Neo4j knowledge graph for neurosymbolic
concepts / symbols, scoped by application and optionally by span.
"""

from __future__ import annotations

import logging

from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.models.otel_traces import (
    ConceptItem,
    ConceptsResponse,
    SpanConceptsResponse,
)
from oxp.query_builders import concepts as concepts_queries

logger = logging.getLogger(__name__)


class ConceptsClient:
    """Concepts operations mixed into :class:`LocalClient`."""

    db: Connector

    # ── app-level concepts ────────────────────────────────────────────────

    def get_app_concepts(self, app_id: str) -> ConceptsResponse:
        """Return all concepts for *app_id*."""
        query, params = concepts_queries.app_concepts_query(app_id)
        try:
            rows = self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get concepts for app '{app_id}': {exc}"
            ) from exc

        return ConceptsResponse(
            app_id=app_id,
            concepts=[
                ConceptItem(
                    name=r.get("name", ""),
                    type=r.get("type", ""),
                    properties=r.get("properties") or {},
                )
                for r in rows
            ],
        )

    # ── span-level concepts ───────────────────────────────────────────────

    def get_span_concepts(
        self,
        app_id: str,
        session_id: str,
        span_id: str,
    ) -> SpanConceptsResponse:
        """Return concepts for a specific span."""
        query, params = concepts_queries.span_concepts_query(
            app_id,
            session_id,
            span_id,
        )
        try:
            rows = self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get concepts for span '{span_id}': {exc}"
            ) from exc

        return SpanConceptsResponse(
            app_id=app_id,
            session_id=session_id,
            span_id=span_id,
            concepts=[
                ConceptItem(
                    name=r.get("name", ""),
                    type=r.get("type", ""),
                    properties=r.get("properties") or {},
                )
                for r in rows
            ],
        )

    # ── write concepts ────────────────────────────────────────────────────

    def write_app_concepts(
        self,
        app_id: str,
        concepts: list[dict],
    ) -> dict:
        """Write concepts to an application node in the KG."""
        written = 0
        errors: list[str] = []
        for c in concepts:
            query, params = concepts_queries.write_app_concept_query(
                app_id=app_id,
                name=c["name"],
                concept_type=c.get("type", ""),
                properties=c.get("properties"),
            )
            try:
                self.db.execute_command(query, params)
                written += 1
            except Exception as exc:
                errors.append(f"{c['name']}: {exc}")
        return {"written": written, "errors": errors}

    def write_span_concepts(
        self,
        app_id: str,
        session_id: str,
        span_id: str,
        concepts: list[dict],
    ) -> dict:
        """Write concepts to a span node in the KG."""
        written = 0
        errors: list[str] = []
        for c in concepts:
            query, params = concepts_queries.write_span_concept_query(
                app_id=app_id,
                session_id=session_id,
                span_id=span_id,
                name=c["name"],
                concept_type=c.get("type", ""),
                properties=c.get("properties"),
            )
            try:
                self.db.execute_command(query, params)
                written += 1
            except Exception as exc:
                errors.append(f"{c['name']}: {exc}")
        return {"written": written, "errors": errors}
