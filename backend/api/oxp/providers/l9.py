#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Provider for the L9 protocol reports of a session.

* ``L9Report``: which L9 protocols were enabled and which were activated.
* ``L9ProtocolExecutionReport``: one protocol's run in the session: the agents and skills
  that took part, and the protocol's evaluation metrics, stored as ``MetricResult`` nodes
  that measure the report.

Workers (the skill worker, the protocols' eval workers) write through this class and
never touch the graph directly. All Cypher lives in ``oxp.query_builders``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from oxp.connectors.base import Connector
from oxp.interfaces.models import MetricResult
from oxp.providers._graph import _graph_properties
from oxp.providers.kg import _resolve_connector
from oxp.query_builders import l9_graph, metric_graph

logger = logging.getLogger(__name__)


class OXPL9ReportProvider:
    """Neo4j-backed writer of ``L9Report`` and ``L9ProtocolExecutionReport`` nodes."""

    def __init__(
        self,
        db: Connector | None = None,
        *,
        connector: Connector | None = None,
    ) -> None:
        """Accept ``db=`` (canonical) or ``connector=`` (compat alias); see ``OXPMetricsProvider``."""
        self._db = _resolve_connector(db, connector)

    def _session_exists(self, session_id: str) -> bool:
        rows = self._db.execute(*l9_graph.session_exists_query(session_id))
        if not rows:
            logger.warning(
                "No Session %s in the graph; L9 report not written", session_id
            )
        return bool(rows)

    def save_l9_report(
        self,
        session_id: str,
        protocols_enabled: Iterable[str],
        protocols_activated: Iterable[str],
    ) -> bool:
        """Store the session's ``L9Report``: the protocols enabled and those activated.

        False (nothing written) if the session is not in the graph or the report fails
        validation against the ontology.
        """
        if not self._session_exists(session_id):
            return False
        try:
            props = l9_graph.l9_report_properties(
                session_id, protocols_enabled, protocols_activated
            )
            self._db.execute_command(*l9_graph.write_l9_report_query(session_id, props))
        except Exception as exc:
            logger.error("save_l9_report failed for %s: %s", session_id, exc)
            return False
        return True

    def save_protocol_execution_report(
        self,
        session_id: str,
        protocol: str,
        *,
        enabled_evidence: str = "",
        skills_enabled: Iterable[str] = (),
        skills_activated: Iterable[str] = (),
        agents_enabled: Iterable[str] = (),
        agents_activated: Iterable[str] = (),
    ) -> bool:
        """Record which agents had a protocol and which used it, in its execution report.

        The report's metrics are left as they are. False if the session is not in the graph.
        """
        if not self._session_exists(session_id):
            return False
        try:
            props = l9_graph.protocol_participation_properties(
                session_id,
                protocol,
                enabled_evidence=enabled_evidence,
                skills_enabled=skills_enabled,
                skills_activated=skills_activated,
                agents_enabled=agents_enabled,
                agents_activated=agents_activated,
            )
            self._db.execute_command(
                *l9_graph.write_protocol_execution_report_query(session_id, props)
            )
        except Exception as exc:
            logger.error(
                "save_protocol_execution_report failed for %s/%s: %s",
                session_id,
                protocol,
                exc,
            )
            return False
        return True

    def save_protocol_execution_metrics(
        self,
        session_id: str,
        protocol: str,
        metrics: MetricResult | Sequence[MetricResult],
    ) -> bool:
        """Make ``metrics`` the evaluation metrics of a protocol's execution report.

        Each becomes a ``MetricResult`` that measures the report (not the session). The report's
        previous results are removed first, so it always holds the latest run. The report is
        created if the protocol's participation has not been recorded yet; what it already holds
        is kept. Metrics that errored or have no value are not stored. False if the session is
        not in the graph or a metric could not be stored.
        """
        items = list(metrics) if isinstance(metrics, (list, tuple)) else [metrics]
        stored = [m for m in items if not m.error and m.value is not None]
        if not self._session_exists(session_id):
            return False

        report_id = l9_graph.protocol_execution_report_id(session_id, protocol)
        rows = []
        for m in stored:
            graph = _graph_properties(m, report_id)
            if graph is None:
                return False
            rows.append(graph)
        try:
            props = l9_graph.protocol_metrics_properties(
                session_id, protocol, len(rows)
            )
            self._db.execute_command(
                *l9_graph.write_protocol_execution_report_query(session_id, props)
            )
            self._db.execute_command(
                *l9_graph.clear_protocol_execution_report_metrics_query(report_id)
            )
            for definition, result in rows:
                self._db.execute_command(
                    *metric_graph.write_metric_result_query(
                        "protocol_execution_report", report_id, definition, result
                    )
                )
        except Exception as exc:
            logger.error(
                "save_protocol_execution_metrics failed for %s/%s: %s",
                session_id,
                protocol,
                exc,
            )
            return False
        return True
