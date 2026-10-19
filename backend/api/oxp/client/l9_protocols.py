"""L9-protocol implementations for :class:`UIClient`.

L9 protocols are stored in the KG as (see ``oxp.query_builders.l9_graph``):

* one ``L9Report`` per session, listing the protocols enabled and those activated;
* one ``L9ProtocolExecutionReport`` per activated protocol and session: the agents and skills
  that had / used the protocol, plus the protocol's evaluation metrics, stored as
  ``MetricResult`` nodes that measure the report.

The API returns the metrics as a generic list, so that a new protocol or metric needs no API
change. A name-to-section map only groups the metrics for display.
"""

from __future__ import annotations

import json
import logging
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

# Section of the metrics that are not listed.
_OTHER_SECTION = "other"

# Section of each metric, by name. Extensible: an unlisted metric goes to ``other``.
_METRIC_SECTIONS = {
    # Convergence and quality of the lock.
    "AccordConverged": "convergence",
    "AccordPhaseCoverage": "convergence",
    "AccordLockedTerms": "convergence",
    "AccordLockPrecision": "convergence",
    "AccordLockRecall": "convergence",
    "AccordFabricatedLock": "convergence",
    "AccordOverSelected": "convergence",
    "AccordUnderSelected": "convergence",
    "AccordTermUtilization": "convergence",
    # Validity of the intent contract.
    "AccordCanonicalValid": "contract",
    "AccordRelayedValid": "contract",
    "AccordContractWarnings": "contract",
    # Token cost of the protocol.
    "AccordProtocolPromptTokens": "cost",
    "AccordProtocolFreshTokens": "cost",
    "AccordProtocolCachedTokens": "cost",
    "AccordProtocolCompletionTokens": "cost",
    "AccordContractOverheadTokens": "cost",
    "AccordContractOverheadShare": "cost",
    "AccordContractOverheadPerCall": "cost",
    # What the protocol brings to the agents.
    "AccordGlossaryInfluence": "benefits",
    "AccordGlossaryUptake": "benefits",
    # CONCORD: did the run reach a commit, following the protocol.
    "ConcordCommitted": "convergence",
    "ConcordReachedEnd": "convergence",
    "ConcordAllSteps": "convergence",
    "ConcordUsedAllCandidates": "convergence",
    "ConcordRounds": "convergence",
    "ConcordRepairRounds": "convergence",
    "ConcordRepairsAfterMarkMissing": "convergence",
    "ConcordBudgetUsed": "convergence",
    # CONCORD: how satisfied and fairly treated the agents are.
    "ConcordWorstOffSatisfaction": "benefits",
    "ConcordWorstOffAboveTau": "benefits",
    "ConcordMeanSatisfaction": "benefits",
    "ConcordSatisfiedAgents": "benefits",
    "ConcordOutcomeSatisfied": "benefits",
    "ConcordScoreFair": "benefits",
    "ConcordUnfairScoreShare": "benefits",
    "ConcordSelfPreferenceGap": "benefits",
    # CONCORD: token cost of the run and of each phase.
    "ConcordRunTokens": "cost",
    "ConcordProtocolTokens": "cost",
    "ConcordProtocolShare": "cost",
    "ConcordTokensBeforeConcord": "cost",
    "ConcordTokensAnchors": "cost",
    "ConcordTokensSeeds": "cost",
    "ConcordTokensScores": "cost",
    "ConcordTokensRepair": "cost",
    "ConcordTokensAfterCommit": "cost",
}


def _normalize_protocol(name: object) -> str:
    """``accord`` / ``L9_ACCORD`` / ``L9-ACCORD`` -> ``L9-ACCORD``."""
    text = str(name).strip().upper().replace("_", "-").replace(" ", "-")
    return text if text.startswith("L9-") else f"L9-{text}"


def _names(raw: object) -> set[str]:
    """Normalized protocol names of a list property."""
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {_normalize_protocol(n) for n in raw if n}


def _protocol_statuses(l9_reports: object) -> dict[str, dict[str, bool]]:
    """``{protocol: {enabled, activated}}`` from the session's ``L9Report`` (latest wins)."""
    reports = [r for r in (l9_reports or []) if isinstance(r, dict)]
    reports.sort(key=lambda r: str(r.get("reportedAt") or ""))
    statuses: dict[str, dict[str, bool]] = {}
    for report in reports:
        enabled = _names(report.get("protocolsEnabled"))
        activated = _names(report.get("protocolsActivated"))
        statuses = {
            name: {
                "enabled": name in enabled or name in activated,
                "activated": name in activated,
            }
            for name in sorted(enabled | activated)
        }
    return statuses


def _parse_json_container(raw: str) -> dict[str, Any] | list[Any] | None:
    """The JSON object or array in *raw*, None if it is anything else."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _split_reasoning(reasoning: str) -> tuple[str, dict[str, Any] | list[Any] | None]:
    """Split a reasoning into its text and its structured part.

    The reasoning is free text, a JSON document, or a text followed by one
    (``"FAIR; {...}"``).
    """
    whole = _parse_json_container(reasoning)
    if whole is not None:
        return "", whole
    head, sep, tail = reasoning.partition("; ")
    parsed = _parse_json_container(tail) if sep else None
    if parsed is not None:
        return head.strip(), parsed
    return reasoning, None


def _build_metric(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Map one ``MetricResult`` row to a UI metric.

    ``reasoning`` is the text explaining the value; the structured data some metrics add to
    it (a JSON document) is returned parsed as ``details``.
    """
    name = raw.get("name")
    if not name:
        return None
    metric: dict[str, Any] = {
        "name": str(name),
        "section": _METRIC_SECTIONS.get(str(name), _OTHER_SECTION),
        "value": raw.get("result"),
    }
    for key in ("provider", "unit", "timestamp"):
        if raw.get(key):
            metric[key] = str(raw[key])
    reasoning = raw.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        text, details = _split_reasoning(reasoning)
        if details is not None:
            metric["details"] = details
        if text:
            metric["reasoning"] = text
    return metric


def _build_protocols(
    l9_reports: object, execution_reports: object
) -> list[dict[str, Any]]:
    """One protocol per name, sorted by name: its status and, if executed, its report."""
    protocols = {
        name: {"protocol": name, **status}
        for name, status in _protocol_statuses(l9_reports).items()
    }
    for item in execution_reports or []:
        report = item.get("report") if isinstance(item, dict) else None
        if not isinstance(report, dict) or not (
            report.get("protocol") or report.get("name")
        ):
            continue
        name = _normalize_protocol(report.get("protocol") or report.get("name"))
        # A protocol with an execution report ran, even if the L9Report is missing.
        protocol = protocols.setdefault(
            name, {"protocol": name, "enabled": True, "activated": True}
        )
        for key in (
            "enabledEvidence",
            "skillsEnabled",
            "skillsActivated",
            "agentsEnabled",
            "agentsActivated",
            "reportedAt",
        ):
            if report.get(key) not in (None, "", []):
                protocol[key] = (
                    str(report[key])
                    if key in {"enabledEvidence", "reportedAt"}
                    else report[key]
                )
        metrics = (_build_metric(m) for m in item.get("metrics") or [])
        protocol["metrics"] = sorted(
            (m for m in metrics if m), key=lambda m: (m["section"], m["name"])
        )
    return [protocols[n] for n in sorted(protocols)]


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
        sessionId=session_id,
        protocols=_build_protocols(row.get("l9Reports"), row.get("executionReports")),
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
        statuses = _protocol_statuses(row.get("l9Reports"))
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
                l9Protocols=[{"protocol": n, **st} for n, st in statuses.items()],
                cognitiveObservabilityMetrics=_build_cognitive_metrics(
                    row.get("sessionMetrics")
                ),
                cognitiveFailures=_build_cognitive_failures(row.get("failures")),
            )
        )
    return SessionsWithL9ProtocolsResponse(sessions=sessions)
