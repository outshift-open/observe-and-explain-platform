#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""L9-protocol implementations for :class:`UIClient`.

L9 protocols are stored in the KG as one ``L9Report`` node per protocol and
session.  Each report says whether the protocol was ``enabled`` / ``activated``
and carries the metrics of the protocol, either as a ``metrics`` JSON string or
as one JSON string property per section (``compliance``, ``correctness``...).
"""

from __future__ import annotations

import json
import logging
from numbers import Real
from typing import Any

from oxp.client.applications import (
    _build_cognitive_failures,
    _build_cognitive_metrics,
    _build_session_metrics_single_query,
)
from oxp.client.constants import TASK_STATUS_DONE
from oxp.client.utils import parse_epoch_range
from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError, NotFoundError
from oxp.models.otel_traces import (
    SessionL9ProtocolsResponse,
    SessionsWithL9ProtocolsResponse,
    SessionWithL9ProtocolsItem,
)
from oxp.query_builders import ui as ui_queries
from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)

# Metric sections of a protocol report, as named by the UI.
_SECTIONS = (
    "compliance",
    "correctness",
    "cost",
    "outcome",
    "convergence",
    "benefits",
)
_CONCORD = "L9-CONCORD"


def _json(raw: object) -> Any:
    """Parse *raw* when it is a JSON string, otherwise return it unchanged."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw


def _normalize_protocol(name: object) -> str:
    """``concord`` / ``L9_CONCORD`` / ``L9-CONCORD`` -> ``L9-CONCORD``."""
    text = str(name).strip().upper().replace("_", "-").replace(" ", "-")
    return text if text.startswith("L9-") else f"L9-{text}"


def _build_protocol(props: dict[str, Any]) -> dict[str, Any] | None:
    """Map one ``L9Report`` node's properties to a UI ``L9Protocol`` dict."""
    name = props.get("protocol") or props.get("name")
    if not name:
        return None

    protocol: dict[str, Any] = {
        "protocol": _normalize_protocol(name),
        "enabled": bool(props.get("enabled", False)),
        "activated": bool(props.get("activated", False)),
    }
    for key in ("displayName", "description", "activatedAt"):
        if props.get(key) is not None:
            protocol[key] = str(props[key])

    expected = _json(props.get("expected"))
    if isinstance(expected, dict):
        protocol["expected"] = expected
    elif isinstance(expected, bool):
        protocol["expected"] = {"expected": expected}

    # Metrics: the ``metrics`` blob first, section properties override it.
    metrics = _json(props.get("metrics"))
    if isinstance(metrics, dict):
        for section in _SECTIONS:
            if isinstance(metrics.get(section), dict):
                protocol[section] = metrics[section]
    for section in _SECTIONS:
        value = _json(props.get(section))
        if isinstance(value, dict):
            protocol[section] = value
    return protocol


def _build_protocols(raw_reports: object) -> list[dict[str, Any]]:
    """One protocol per report, one entry per protocol, sorted by name."""
    by_name: dict[str, dict[str, Any]] = {}
    for props in raw_reports if isinstance(raw_reports, (list, tuple)) else []:
        if isinstance(props, dict) and (protocol := _build_protocol(props)):
            by_name[protocol["protocol"]] = protocol
    return [by_name[n] for n in sorted(by_name)]


def _concord_summary(protocol: dict[str, Any]) -> dict[str, Any]:
    """Terminal state and worst-off satisfaction of an activated CONCORD run."""
    terminal = (protocol.get("compliance") or {}).get("completion") or {}
    scores = (protocol.get("outcome") or {}).get("agentScores") or []
    values = [a.get("score") for a in scores if isinstance(a, dict)]
    # The worst-off agent is only known when every agent has a score.
    worst = (
        min(values)
        if values
        and all(isinstance(v, Real) and not isinstance(v, bool) for v in values)
        else None
    )
    return {
        "terminalState": terminal.get("terminalState"),
        "worstOffSatisfaction": worst,
    }


def _get_session_l9_protocols(
    db: Connector, dialect: Dialect, *, session_id: str
) -> SessionL9ProtocolsResponse:
    """Return the L9 protocols (with their metrics) of one session."""
    del dialect  # Neo4j-only query.
    query, params = ui_queries.neo4j_session_l9_reports_query(session_id=session_id)
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get L9 protocols for session '{session_id}': {exc}"
        ) from exc

    row = rows[0] if rows else {}
    if not row.get("found"):
        raise NotFoundError(f"Session '{session_id}' not found.")
    return SessionL9ProtocolsResponse(
        sessionId=session_id, protocols=_build_protocols(row.get("reports"))
    )


def _get_application_sessions_with_l9_protocols(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    start_time: str = "",
    end_time: str = "",
) -> SessionsWithL9ProtocolsResponse:
    """Return the sessions of an application with their L9 protocol status."""
    del dialect  # Neo4j-only query.
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)
    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    query, params = ui_queries.neo4j_sessions_with_cognitive_observability_query(
        application_id=application_id, start_epoch=start_epoch, end_epoch=end_epoch
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get L9 protocols for '{application_id}': {exc}"
        ) from exc

    sessions: list[SessionWithL9ProtocolsItem] = []
    for row in rows or []:
        protocols = _build_protocols(row.get("l9Reports"))
        concord = next(
            (p for p in protocols if p["protocol"] == _CONCORD and p["activated"]),
            None,
        )
        sessions.append(
            SessionWithL9ProtocolsItem(
                sessionId=str(row["sessionId"]),
                timestamp=str(row["startTime"]),
                agents=row.get("agents") or [],
                llms=[],
                tokens=row.get("tokens") or 0,
                status=TASK_STATUS_DONE,
                cost=row.get("cost") or 0.0,
                duration=row.get("duration") or 0.0,
                session_metrics=_build_session_metrics_single_query(
                    row.get("sessionMetrics")
                ),
                l9Protocols=[
                    {
                        "protocol": p["protocol"],
                        "enabled": p["enabled"],
                        "activated": p["activated"],
                    }
                    for p in protocols
                ],
                cognitiveObservabilityMetrics=_build_cognitive_metrics(
                    row.get("sessionMetrics")
                ),
                cognitiveFailures=_build_cognitive_failures(row.get("failures")),
                concord=_concord_summary(concord) if concord else None,
            )
        )
    return SessionsWithL9ProtocolsResponse(sessions=sessions)
