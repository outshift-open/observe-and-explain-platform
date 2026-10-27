#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""How cognitive failure reports are stored in the knowledge graph.

::

    (r:CognitiveFailureReport {id, name, code, confidence,
                                 reasoning, reportedAt})
        -[:reportsOn]-> (s:Session)
    (r) -[:atCall]-> (c:LLMCall | ToolCall | AgentCall | ...)      only when it happened in one call

A report is one detection of one failure of the challenges taxonomy in a
session. Its id comes from the session, the failure and the call, so writing
the same detection again overwrites it. The node properties are exactly the
fields of the model generated from the ontology
(``oxp_ontology.models.nodes.CognitiveFailureReport``); every write is
validated against it.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from oxp_ontology.models.nodes import CognitiveFailureReport as ReportModel

QueryPair = tuple[str, dict[str, Any]]

CONFIDENCES = ("low", "medium", "high")

# Execution elements (calls) a report can point at.
CALL_LABELS = [
    "LLMCall",
    "ToolCall",
    "AgentCall",
    "CapabilityCall",
    "MASCall",
    "ProcessingCall",
]


def _failure_report_id(session_id: str, code: str, call_id: str | None) -> str:
    """Id of the report of failure ``code`` in a session, at a call or (``None``) for the whole session."""
    digest = hashlib.sha1(
        "\x1f".join((session_id, code, call_id or "")).encode("utf-8")
    )
    return f"failurereport:{digest.hexdigest()[:12]}"


def failure_report_properties(
    session_id: str,
    code: str,
    confidence: str,
    reasoning: str,
    call_id: str | None = None,
    reported_at: datetime | None = None,
) -> dict[str, Any]:
    """Properties of the ontology ``CognitiveFailureReport`` (validated against the model).

    Raises ``ValueError`` if ``confidence`` is not ``low``, ``medium`` or ``high``, and
    ``pydantic.ValidationError`` if the report does not fit the model (for example an empty code).
    """
    if confidence not in CONFIDENCES:
        raise ValueError(f"confidence must be one of {CONFIDENCES}, not {confidence!r}")
    if not code.strip() or not reasoning.strip():
        raise ValueError("a failure report needs a code and a reasoning")
    return ReportModel(
        id=_failure_report_id(session_id, code, call_id),
        name=code,
        code=code,
        confidence=confidence,
        reasoning=reasoning,
        reportedAt=reported_at or datetime.now(UTC),
    ).model_dump()


def write_failure_report_query(
    session_id: str, props: dict[str, Any], call_id: str | None = None
) -> QueryPair:
    """MERGE a report and link it to the session and, when ``call_id`` names one of its calls, to that call.

    Nothing is written if the session is missing. A ``call_id`` that is not a call of the session
    leaves the report on the session only.
    """
    query = """
    MATCH (s:Session {sessionId: $session_id})
    MERGE (r:CognitiveFailureReport {id: $props.id})
    SET r = $props
    MERGE (r)-[:reportsOn]->(s)
    WITH r
    OPTIONAL MATCH (c {id: $call_id})
    WHERE c.sessionId = $session_id AND any(label IN labels(c) WHERE label IN $call_labels)
    FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END | MERGE (r)-[:atCall]->(c))
    RETURN r.id AS id, c IS NOT NULL AS atCall
    """
    return query, {
        "session_id": session_id,
        "props": props,
        "call_id": call_id,
        "call_labels": CALL_LABELS,
    }
