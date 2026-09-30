#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Session-domain methods for :class:`LocalClient`."""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Iterator
from typing import Any, Optional

from oxp.client.utils import parse_span_attributes, parse_time_filters
from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.models.otel_traces import (
    Filters,
    SessionSpansResponse,
    SessionSummaryItem,
    SessionSummaryResponse,
    SpanMetadataItem,
)
from oxp.query_builders import sessions as session_queries
from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)


def _parse_sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if not isinstance(value, str) or not value.strip():
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (list, tuple)):
            return list(parsed)
    return []


class SessionsClient:
    """Session operations mixed into :class:`LocalClient`."""

    db: Connector
    _dialect: Dialect

    # ── GET /sessions ─────────────────────────────────────────────────────

    def list_sessions(
        self,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SessionSummaryResponse:
        """Return ``(session_id, timestamp)`` tuples."""
        filters = Filters(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        start_dt, end_dt = parse_time_filters(filters)

        stmt = session_queries.list_sessions_query(
            self._dialect,
            start_time=start_dt,
            end_time=end_dt,
            limit=filters.limit,
            offset=filters.offset,
        )
        try:
            rows = self.db.execute(stmt)
        except Exception as exc:
            raise DatabaseError(f"Failed to list sessions: {exc}") from exc
        return SessionSummaryResponse(
            sessions=[
                SessionSummaryItem(
                    session_id=str(r[0]),
                    timestamp=str(r[1]),
                )
                for r in rows
            ]
        )

    # ── GET /sessions/spans ───────────────────────────────────────────────

    def iter_session_spans(
        self, session_id: str, *, page_size: int = 500
    ) -> Iterator[SpanMetadataItem]:
        """Yield every span in stable chronological order for a completed session.

        Offset pagination is not a snapshot of an actively growing trace.
        Database errors propagate; callers must not evaluate a partial iteration.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id must not be empty")
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        offset = 0
        while True:
            page = self.get_session_spans(
                session_ids=[session_id], limit=page_size, offset=offset, order="asc"
            ).spans
            yield from page
            if len(page) < page_size:
                return
            offset += len(page)

    def get_session_spans(
        self,
        *,
        session_ids: list[str] | None = None,
        span_types: list[str] | None = None,
        limit: int = 500,
        offset: int = 0,
        order: str = "asc",
    ) -> SessionSpansResponse:
        """Return span attributes + metadata for session(s) / type(s)."""
        stmt = session_queries.session_spans_query(
            self._dialect,
            session_ids=session_ids,
            span_types=span_types,
            limit=limit,
            offset=offset,
            order=order,
        )
        try:
            rows = self.db.execute(stmt)
        except Exception as exc:
            raise DatabaseError(f"Failed to fetch session spans: {exc}") from exc

        spans: list[SpanMetadataItem] = []
        for r in rows:
            span_name = str(r[2])
            span_type = span_name.rsplit(".", 1)[-1] if "." in span_name else span_name

            raw_attrs = str(r[8]) if r[8] else ""
            attrs = parse_span_attributes(raw_attrs)

            spans.append(
                SpanMetadataItem(
                    span_id=str(r[0]),
                    session_id=str(r[1]),
                    span_name=span_name,
                    span_type=span_type,
                    timestamp=str(r[3]),
                    duration=int(r[4]) if r[4] else 0,
                    status_code=str(r[5]) if r[5] else "",
                    parent_span_id=str(r[6]) if r[6] else "",
                    service_name=str(r[7]) if r[7] else "",
                    span_attributes=attrs,
                    links_trace_id=[str(item) for item in _parse_sequence(r[9])],
                    links_span_id=[str(item) for item in _parse_sequence(r[10])],
                    links_trace_state=[str(item) for item in _parse_sequence(r[11])],
                    links_attributes=[
                        dict(item)
                        for item in _parse_sequence(r[12])
                        if isinstance(item, dict)
                    ],
                )
            )

        return SessionSpansResponse(spans=spans)
