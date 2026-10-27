#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""How Cognition protocol reports are stored in the knowledge graph.

::

    (r:CognitionProtocolReport {id, sessionId, protocolsEnabled, protocolsActivated, reportedAt})
        -[:reportsOn]-> (s:Session)
    (p:CognitionProtocolExecutionReport {id, sessionId, protocol, enabledEvidence, skillsEnabled,
                                  skillsActivated, agentsEnabled, agentsActivated,
                                  metricCount, reportedAt})
        -[:reportsOn]-> (s:Session)
    (m:MetricResult) -[:measures]-> (p:CognitionProtocolExecutionReport)

An ``CognitionProtocolReport`` says which Cognition protocols were enabled and which activated in a
session: lists of protocol names, so a new protocol adds an entry, not a
property. An ``CognitionProtocolExecutionReport`` is everything about one protocol in
one session: who had it, who used it, and its evaluation metrics (see
``metric_graph``, which writes the ``MetricResult`` nodes that measure it).

Both are keyed by session (and protocol), so writing again overwrites. The node
properties are exactly the fields of the models generated from the ontology
(``oxp_ontology.models.nodes.CognitionProtocolReport`` / ``CognitionProtocolExecutionReport``); every
write is validated against them. Different writers fill different properties of
the same protocol report (who took part, the metrics), so each builder returns
only the properties its writer owns and the others are left as they are.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from oxp_ontology.models.nodes import (
    CognitionProtocolExecutionReport as ProtocolReportModel,
)
from oxp_ontology.models.nodes import (
    CognitionProtocolReport as CognitionProtocolReportModel,
)

QueryPair = tuple[str, dict[str, Any]]

COGNITION_PROTOCOL_REPORT = "CognitionProtocolReport"
COGNITION_PROTOCOL_EXECUTION_REPORT = "CognitionProtocolExecutionReport"

_PARTICIPATION_FIELDS = {
    "id",
    "name",
    "sessionId",
    "protocol",
    "enabledEvidence",
    "skillsEnabled",
    "skillsActivated",
    "agentsEnabled",
    "agentsActivated",
    "reportedAt",
}
_METRICS_FIELDS = {"id", "name", "sessionId", "protocol", "metricCount", "reportedAt"}


def _digest(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def cognition_protocol_report_id(session_id: str) -> str:
    """Id of the ``CognitionProtocolReport`` of a session."""
    return f"cognitionprotocolreport:{_digest(session_id)}"


def protocol_execution_report_id(session_id: str, protocol: str) -> str:
    """Id of the ``CognitionProtocolExecutionReport`` of a protocol in a session."""
    return f"cognitionprotocolexecutionreport:{_digest(protocol, session_id)}"


def _names(values: Iterable[str]) -> list[str]:
    return sorted({str(v) for v in values})


def cognition_protocol_report_properties(
    session_id: str,
    protocols_enabled: Iterable[str],
    protocols_activated: Iterable[str],
    reported_at: datetime | None = None,
) -> dict[str, Any]:
    """Properties of the ontology ``CognitionProtocolReport`` (validated against the model)."""
    return CognitionProtocolReportModel(
        id=cognition_protocol_report_id(session_id),
        name="Cognition protocol report",
        sessionId=session_id,
        protocolsEnabled=_names(protocols_enabled),
        protocolsActivated=_names(protocols_activated),
        reportedAt=reported_at or datetime.now(UTC),
    ).model_dump()


def protocol_participation_properties(
    session_id: str,
    protocol: str,
    *,
    enabled_evidence: str = "",
    skills_enabled: Iterable[str] = (),
    skills_activated: Iterable[str] = (),
    agents_enabled: Iterable[str] = (),
    agents_activated: Iterable[str] = (),
    reported_at: datetime | None = None,
) -> dict[str, Any]:
    """Who had a protocol and who used it: the participation properties of its execution report."""
    model = ProtocolReportModel(
        id=protocol_execution_report_id(session_id, protocol),
        name=protocol,
        sessionId=session_id,
        protocol=protocol,
        enabledEvidence=enabled_evidence,
        skillsEnabled=_names(skills_enabled),
        skillsActivated=_names(skills_activated),
        agentsEnabled=_names(agents_enabled),
        agentsActivated=_names(agents_activated),
        reportedAt=reported_at or datetime.now(UTC),
    )
    return model.model_dump(include=_PARTICIPATION_FIELDS)


def protocol_metrics_properties(
    session_id: str,
    protocol: str,
    metric_count: int,
    reported_at: datetime | None = None,
) -> dict[str, Any]:
    """The metrics-side properties of an execution report: its identity and how many metrics it has."""
    model = ProtocolReportModel(
        id=protocol_execution_report_id(session_id, protocol),
        name=protocol,
        sessionId=session_id,
        protocol=protocol,
        metricCount=metric_count,
        reportedAt=reported_at or datetime.now(UTC),
    )
    return model.model_dump(include=_METRICS_FIELDS)


def session_exists_query(session_id: str) -> QueryPair:
    """One row (``sessionId``) if the session is in the graph, none otherwise."""
    return (
        "MATCH (s:Session {sessionId: $session_id}) RETURN s.sessionId AS sessionId LIMIT 1",
        {"session_id": session_id},
    )


def write_cognition_protocol_report_query(
    session_id: str, props: dict[str, Any]
) -> QueryPair:
    """MERGE the session's ``CognitionProtocolReport`` and link it to the session. Nothing is written if the session is missing."""
    query = f"""
    MATCH (s:Session {{sessionId: $session_id}})
    MERGE (r:{COGNITION_PROTOCOL_REPORT} {{id: $props.id}})
    SET r += $props
    MERGE (r)-[:reportsOn]->(s)
    RETURN r.id AS id
    """
    return query, {"session_id": session_id, "props": props}


def write_protocol_execution_report_query(
    session_id: str, props: dict[str, Any]
) -> QueryPair:
    """MERGE a protocol's execution report and link it to the session.

    ``props`` holds only the properties the caller owns (see ``protocol_participation_properties``
    and ``protocol_metrics_properties``): the others stay as they are. Nothing is written if the
    session is missing.
    """
    query = f"""
    MATCH (s:Session {{sessionId: $session_id}})
    MERGE (p:{COGNITION_PROTOCOL_EXECUTION_REPORT} {{id: $props.id}})
    SET p += $props
    MERGE (p)-[:reportsOn]->(s)
    RETURN p.id AS id
    """
    return query, {"session_id": session_id, "props": props}


def clear_protocol_execution_report_metrics_query(report_id: str) -> QueryPair:
    """Delete the metric results measuring a protocol execution report (the ``Metric`` definitions stay)."""
    query = f"""
    MATCH (r:MetricResult)-[:measures]->(p:{COGNITION_PROTOCOL_EXECUTION_REPORT} {{id: $report_id}})
    DETACH DELETE r
    RETURN count(r) AS deleted
    """
    return query, {"report_id": report_id}
