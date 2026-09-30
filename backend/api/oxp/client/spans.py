#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Span-related private implementations for :class:`UIClient`."""

from __future__ import annotations

import logging

from oxp.client.constants import (
    SPAN_TYPE_AGENT,
    SPAN_TYPE_CHAT,
    SPAN_TYPE_TOOL,
)
from oxp.client.utils import (
    build_agent_attributes,
    build_chat_attributes,
    build_tool_attributes,
    parse_events_attributes,
    parse_span_attributes,
)
from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.models.otel_traces import (
    SpanDetailsItem,
    SpanDetailsResponse,
)
from oxp.query_builders import ui as ui_queries
from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)


# ── get_spans ────────────────────────────────────────────────────────────────


def _get_spans(
    db: Connector,
    dialect: Dialect,
    *,
    span_id: str,
) -> SpanDetailsResponse:
    """Return detailed information about a single span."""
    stmt = ui_queries.span_details_query(
        dialect,
        span_id=span_id,
    )

    try:
        rows = db.execute(stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get span details for '{span_id}': {exc}"
        ) from exc

    if not rows:
        from oxp.core.exceptions import NotFoundError

        raise NotFoundError(f"Span with id '{span_id}' not found")

    row = rows[0]
    raw_span_id = str(row[0])
    span_name = str(row[1])
    raw_attrs = str(row[2]) if row[2] else ""
    status_code = str(row[3]) if row[3] else ""
    raw_events = str(row[4]) if row[4] else ""
    scope_name = str(row[5]) if row[5] else ""

    # Derive span type from span name (last segment after ".")
    span_type = span_name.rsplit(".", 1)[-1] if "." in span_name else span_name

    attrs = parse_span_attributes(raw_attrs)
    events_attrs = parse_events_attributes(raw_events)

    # Build attributes and exception based on span type
    exception = ""
    if span_type == SPAN_TYPE_CHAT:
        attributes = build_chat_attributes(attrs)
    elif span_type == SPAN_TYPE_AGENT:
        attributes = build_agent_attributes(attrs)
    elif span_type == SPAN_TYPE_TOOL:
        attributes, exception = build_tool_attributes(
            attrs, status_code, events_attrs, scope_name
        )
    else:
        attributes = []

    return SpanDetailsResponse(
        spanDetails=SpanDetailsItem(
            spanId=raw_span_id,
            spanName=span_name,
            spanType=span_type,
            exception=exception,
            attributes=attributes,
        )
    )
