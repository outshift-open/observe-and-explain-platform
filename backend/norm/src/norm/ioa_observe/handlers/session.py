#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handlers for the "session.start" / "session.end" span names."""

from __future__ import annotations

from typing import Any

from oxp_ontology.models.edges import executesSession
from oxp_ontology.models.nodes import MAS, Session

from ..fields import (
    _to_float,
    get_application_id,
    get_session_id,
    get_start_time,
    get_success,
)
from ..registry import Registry


def handle_session_start(
    span: dict[str, Any], span_attrs: dict[str, Any], registry: Registry
) -> None:
    session_id = get_session_id(span, span_attrs)
    application_id = get_application_id(span, span_attrs)
    if not session_id or registry.get(Session, session_id) is not None:
        return
    start_time = get_start_time(span, span_attrs)
    session = registry.add(
        Session(
            id=session_id,
            name=f"Session {session_id}",
            sessionId=session_id,
            startTime=start_time,
            endTime=start_time,
            duration=0.0,
            spanId=str(span.get("SpanId") or ""),
            parentSpanId=str(span.get("ParentSpanId") or ""),
            success=get_success(span, span_attrs),
        )
    )
    if application_id:
        registry.add_if_not_exists(
            MAS(
                id=application_id,
                name=application_id,
                description=application_id,
            )
        )
        registry.add_edge(
            executesSession(
                source_id=session.id,
                target_id=application_id,
            )
        )


def handle_session_end(
    span: dict[str, Any], span_attrs: dict[str, Any], registry: Registry
) -> None:
    session_id = get_session_id(span, span_attrs)
    application_id = get_application_id(span, span_attrs)
    session: Session = registry.get(Session, session_id)
    if session is None:
        return  # no matching session seen yet -- nothing to update
    ended_at = _to_float(span_attrs.get("session.ended_at")) or get_start_time(
        span,
        span_attrs,
    )
    session.endTime = ended_at  # type: ignore[attr-defined]
    session.duration = max(0.0, (ended_at - session.startTime) * 1000.0)  # type: ignore[attr-defined]
    end_success = get_success(span, span_attrs)
    if end_success is not None:
        session.success = end_success  # type: ignore[attr-defined]
    if application_id:
        registry.add_if_not_exists(
            MAS(
                id=application_id,
                name=application_id,
                description=application_id,
            )
        )
        registry.add_edge(
            executesSession(
                source_id=session.id,
                target_id=application_id,
            )
        )
