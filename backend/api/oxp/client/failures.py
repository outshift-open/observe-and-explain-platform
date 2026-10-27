#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Writing the cognitive failures detected in a session."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.query_builders import failure_graph

logger = logging.getLogger(__name__)


def write_cognitive_failure_reports(
    db: Connector,
    session_id: str,
    detections: Iterable[Mapping[str, Any]],
) -> int:
    """Write the cognitive failure reports of a session.

    Each detection has a failure ``code``, a ``confidence`` (``low``, ``medium`` or ``high``),
    a ``reasoning`` and, when the failure happened in one call, that call's ``call_id``.
    A report is keyed by session, failure and call, so writing the same detection again
    overwrites it; reports of earlier runs that are not detected again stay. Every detection is
    validated against the ontology before anything is written.

    Returns the number of reports written (0 if the session is not in the graph).
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty")

    prepared = []
    seen: set[str] = set()
    for detection in detections:
        call_id = detection.get("call_id") or None
        props = failure_graph.failure_report_properties(
            session_id,
            detection["code"],
            detection["confidence"],
            detection["reasoning"],
            call_id,
        )
        if (
            props["id"] not in seen
        ):  # the same failure twice in one place is one report
            seen.add(props["id"])
            prepared.append((props, call_id))

    try:
        written = 0
        for props, call_id in prepared:
            rows = db.execute(
                *failure_graph.write_failure_report_query(
                    session_id, props, call_id
                )
            )
            written += 1 if rows else 0
    except Exception as exc:
        raise DatabaseError(
            f"Failed to write cognitive failure reports of session '{session_id}': {exc}"
        ) from exc
    if written < len(prepared):
        logger.warning(
            "Session %s is not in the graph: %d failure report(s) not written",
            session_id,
            len(prepared) - written,
        )
    return written
