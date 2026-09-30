#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Concrete data-access providers for oxp-api.

Two focused providers, each implementing one set of ABCs:

* :class:`OXPMetricsProvider` — metric CRUD only (``MetricsProvider`` ABC).
* :class:`OXPKGProvider` — KG reads + span fetching
  (``KGProvider`` + ``DataProvider`` ABCs).

All Cypher is centralised in ``oxp.query_builders``.

Dependency graph (acyclic)
--------------------------
::

    mce-core   ← no oxp imports
    mce-helper ← oxp.interfaces (ABCs only)
    mce-client ← mce-helper + oxp.providers
    oxp-api ← no mce imports
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from numbers import Real
from typing import Any, Literal

from oxp.connectors.base import Connector
from oxp.interfaces import MetricsProvider
from oxp.interfaces.models import MetricResult
from oxp.providers.kg import OXPKGProvider, _resolve_connector
from oxp.query_builders import metrics as metrics_qb

logger = logging.getLogger(__name__)


def _parse_stored_metric_result(
    raw_result: Any,
) -> tuple[Any, str | None, str | None, str | None]:
    """Parse both legacy JSON payloads and the new scalar metricResult shape."""
    if raw_result is None:
        return None, None, None, None

    if isinstance(raw_result, Real) and not isinstance(raw_result, bool):
        return float(raw_result), None, None, None

    parsed = raw_result
    if isinstance(raw_result, str):
        try:
            parsed = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError):
            return None, None, None, None

    if isinstance(parsed, Real) and not isinstance(parsed, bool):
        return float(parsed), None, None, None

    if not isinstance(parsed, dict):
        return None, None, None, None

    return (
        parsed.get("value"),
        parsed.get("metric_id"),
        parsed.get("source"),
        parsed.get("reasoning"),
    )


def _metric_property_value(value: Any) -> str:
    """Serialize complex metric metadata into a Neo4j property-safe value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class OXPMetricsProvider(MetricsProvider):
    """Neo4j-backed MetricsProvider.

    Handles metric CRUD on ``:Metric`` nodes only: retrieval, persistence,
    deletion, and time-series aggregation.  All Cypher lives in
    ``oxp.query_builders.metrics`` -- no raw strings in this class.
    """

    def __init__(
        self,
        db: Connector | None = None,
        *,
        connector: Connector | None = None,
    ) -> None:
        """Accept ``db=`` (canonical) or ``connector=`` (compat alias).

        When neither is supplied the connector is built from environment
        variables (``NEO4J_HOST``, ``NEO4J_USERNAME``, ``NEO4J_PASSWORD``).
        """
        self._db = _resolve_connector(db, connector)

    # -- get_metrics ----------------------------------------------------------

    def get_metrics(
        self,
        resource_ids: str | list[str],
        metric_ids: str | list[str] | None = None,
        session_id: str | None = None,
        recursive: bool = False,
        **kwargs: Any,
    ) -> list[MetricResult]:
        """Retrieve metrics using the existing session/span query builders.

        This method delegates to ``session_metrics_query`` for session-level
        lookups.  The ``hops`` parameter can be passed via *kwargs*.
        """
        rids = [resource_ids] if isinstance(resource_ids, str) else resource_ids
        mids: list[str] | None = (
            [metric_ids] if isinstance(metric_ids, str) else metric_ids
        )
        hops = kwargs.get("hops", 1)

        results: list[MetricResult] = []
        for rid in rids:
            query, params = metrics_qb.session_metrics_query(rid, hops=hops)
            try:
                rows = self._db.execute(query, params)
            except Exception as exc:
                logger.warning("get_metrics query failed for %s: %s", rid, exc)
                continue

            if not rows:
                continue

            row = rows[0]
            for m in row.get("metrics") or []:
                if not m or not m.get("name"):
                    continue

                name = m["name"]
                if mids and name not in mids:
                    continue

                value, metric_id, source, reasoning = _parse_stored_metric_result(
                    m.get("result")
                )
                if value is None:
                    value = m.get("value")
                if metric_id is None:
                    metric_id = m.get("metric_id") or name
                if source is None:
                    source = m.get("source")
                if reasoning is None:
                    reasoning = m.get("reasoning")
                provider = m.get("provider") or source or "oxp"

                results.append(
                    MetricResult(
                        metric_id=name,
                        resource_id=rid,
                        provider=provider,
                        value=value,
                        reasoning=reasoning,
                        metadata={
                            "metric_id": metric_id,
                            "source": source,
                            "subgraph": row.get("subgraph"),
                        },
                    )
                )

        return results

    # ── MetricsProvider: save_metrics ─────────────────────────────────────

    def save_metrics(self, metrics: MetricResult | list[MetricResult]) -> bool:
        """Persist metrics using the existing write query builders."""
        items = [metrics] if isinstance(metrics, MetricResult) else metrics
        if not items:
            return True

        ok = True
        for m in items:
            if m.error or m.value is None:
                continue
            query, params = metrics_qb.write_generic_metric_query(
                resource_id=m.resource_id,
                metric_name=m.metric_id,
                metric_value=m.value if isinstance(m.value, (int, float)) else None,
                provider=m.provider,
                metric_id=m.metadata.get("metric_id") or m.metric_id,
                source=m.metadata.get("source"),
                reasoning=_metric_property_value(m.reasoning),
            )
            try:
                self._db.execute_command(query, params)
            except Exception as exc:
                logger.error(
                    "save_metrics failed for %s/%s: %s", m.resource_id, m.metric_id, exc
                )
                ok = False
        return ok

    def save_span_metrics(
        self,
        session_id: str,
        span_id: str,
        metrics: MetricResult | list[MetricResult],
    ) -> bool:
        """Persist span-level metrics (convenience beyond the ABC)."""
        items = [metrics] if isinstance(metrics, MetricResult) else metrics
        ok = True
        for m in items:
            if m.error or m.value is None:
                continue
            query, params = metrics_qb.write_span_metric_query(
                session_id=session_id,
                span_id=span_id,
                metric_name=m.metric_id,
                metric_value=m.value if isinstance(m.value, (int, float)) else None,
                provider=m.provider,
                metric_id=m.metadata.get("metric_id") or m.metric_id,
                source=m.metadata.get("source"),
                reasoning=_metric_property_value(m.reasoning),
            )
            try:
                self._db.execute_command(query, params)
            except Exception as exc:
                logger.error(
                    "save_span_metrics failed for %s/%s: %s", span_id, m.metric_id, exc
                )
                ok = False
        return ok

    # ── MetricsProvider: clean_metrics ────────────────────────────────────

    def clean_metrics(self, session_id: str | None = None) -> int:
        query, params = metrics_qb.clean_metrics_query(session_id)
        try:
            rows = self._db.execute(query, params)
            return rows[0]["deleted"] if rows else 0
        except Exception as exc:
            logger.error("clean_metrics failed: %s", exc)
            return 0

    # -- get_metrics_over_time ------------------------------------------------

    def get_metrics_over_time(
        self,
        metric_id: str,
        start: datetime,
        end: datetime | None = None,
        bucket: Literal["minute", "hour", "day"] = "hour",
        app_name: str | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query, params = metrics_qb.metrics_over_time_query(
            metric_id, start, end, bucket, app_name, agent_id
        )
        try:
            rows = self._db.execute(query, params)
            return [
                {
                    "bucket": r["bucket"],
                    "avg_value": float(r["avg_value"]),
                    "min_value": float(r["min_value"]),
                    "max_value": float(r["max_value"]),
                    "n_sessions": int(r["n_sessions"]),
                }
                for r in (rows or [])
            ]
        except Exception as exc:
            logger.error("get_metrics_over_time failed: %s", exc)
            return []


class Neo4jGraphProvider(OXPKGProvider, OXPMetricsProvider):
    """Combined Neo4j provider (KG + Data + Metrics).

    Used by endpoints/CLI that need full MCE capabilities in one object.
    Combines :class:`OXPKGProvider` (read-only KG/data access)
    and :class:`OXPMetricsProvider` (metric CRUD).
    """

    pass


OXPGraphProvider = Neo4jGraphProvider


__all__ = [
    "OXPMetricsProvider",
    "OXPKGProvider",
    "OXPGraphProvider",
    "Neo4jGraphProvider",
]
