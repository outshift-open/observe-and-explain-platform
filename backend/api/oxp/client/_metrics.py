#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Metrics-domain methods for :class:`LocalClient`.

These methods query the Neo4j knowledge graph for session-level and
span-level metrics, with optional sub-graph expansion (``hops``).

All operations delegate to the :class:`MetricsProvider` instance on
``self.metrics_provider``.  The provider is always set — ``LocalClient``
auto-defaults to :class:`OXPMetricsProvider` when none is supplied.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, time, timezone
from numbers import Real
from typing import Any

from oxp.client.constants import PERIODS_COUNT
from oxp.core.config import settings
from oxp.core.exceptions import DatabaseError
from oxp.interfaces.metrics_provider import MetricsProvider
from oxp.interfaces.models import MetricResult
from oxp.models.otel_traces import (
    ApplicationMetricsSummary,
    ApplicationMetricsTimeline,
    MetricItem,
    SessionMetricsResponse,
    SingleValueData,
    SpanMetricsResponse,
    TimelineData,
)
from oxp.query_builders import metrics as metrics_queries

# ── helpers ───────────────────────────────────────────────────────────────────


def _decode_json_like(value: Any) -> Any:
    """Decode JSON objects/lists stored in scalar KG properties when present."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return value


def _decode_reasoning_payload(value: Any) -> Any:
    """Decode stored reasoning and unwrap legacy combined reasoning payloads."""
    decoded = _decode_json_like(value)
    if isinstance(decoded, dict) and "reasoning" in decoded:
        return decoded.get("reasoning")
    return decoded


def _metric_results_to_items(
    results: list[MetricResult],
    metric_names: list[str] | None = None,
) -> list[MetricItem]:
    """Convert a list of :class:`MetricResult` to Pydantic :class:`MetricItem`."""
    items = []
    for r in results:
        items.append(
            MetricItem(
                name=r.metric_id,
                value=r.value if isinstance(r.value, (int, float)) else None,
                metric_id=r.metadata.get("metric_id"),
                source=r.metadata.get("source") or r.provider,
                reasoning=_decode_reasoning_payload(r.reasoning),
                error=r.error,
            )
        )
    if metric_names:
        allowed = set(metric_names)
        items = [m for m in items if m.name in allowed]
        order = {name: index for index, name in enumerate(metric_names)}
        items.sort(key=lambda item: order.get(item.name, len(order)))
    return items


logger = logging.getLogger(__name__)


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _parse_metric_result(
    result: object,
) -> tuple[float | None, str | None, str | None, str | None]:
    """Parse serialized metric payload and return normalized fields.

    Metric payloads can contain complex structures under ``value``. The
    response model only accepts numeric values, so non-numeric values are
    normalized to ``None``.
    """
    if result is None:
        return None, None, None, None

    if isinstance(result, str) and result == "":
        return None, None, None, None

    if isinstance(result, Real) and not isinstance(result, bool):
        return float(result), None, None, None

    parsed = None
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return None, None, None, None
    elif isinstance(result, dict):
        parsed = result

    if isinstance(parsed, Real) and not isinstance(parsed, bool):
        return float(parsed), None, None, None

    if not isinstance(parsed, dict):
        return None, None, None, None

    raw_value = parsed.get("value")
    value = (
        float(raw_value)
        if isinstance(raw_value, Real) and not isinstance(raw_value, bool)
        else None
    )
    return (
        value,
        parsed.get("metric_id"),
        parsed.get("source"),
        parsed.get("reasoning"),
    )


def _parse_metric_payload(result: object) -> Any:
    """Return the decoded metric payload when possible."""
    if result is None or result == "":
        return None
    if isinstance(result, Real) and not isinstance(result, bool):
        return float(result)
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        current: Any = result
        for _ in range(3):
            if isinstance(current, dict):
                return current
            if isinstance(current, Real) and not isinstance(current, bool):
                return float(current)
            if not isinstance(current, str):
                return current
            try:
                current = json.loads(current)
            except (json.JSONDecodeError, TypeError):
                return None
        return current
    return None


def _path_value(payload: Any, path: list[str] | None) -> Any:
    """Read a nested value from a decoded metric payload."""
    if not path:
        return payload

    current = payload
    for part in path:
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, Real) and not isinstance(value, bool):
        return float(value)
    return None


def _apply_value_scale(value: float, metric_def: dict[str, Any]) -> float:
    scale = metric_def.get("value_scale")
    if isinstance(scale, Real) and not isinstance(scale, bool):
        return value * float(scale)
    return value


def _apply_value_bounds(value: float, metric_def: dict[str, Any]) -> float | None:
    min_value = metric_def.get("min_value")
    max_value = metric_def.get("max_value")

    if isinstance(min_value, Real) and not isinstance(min_value, bool):
        if value < float(min_value):
            return None

    if isinstance(max_value, Real) and not isinstance(max_value, bool):
        if value > float(max_value):
            return None

    return value


def _entry_value(payload: Any, metric_def: dict[str, Any]) -> float | None:
    """Extract or derive the numeric value for one metric entry."""
    formula = metric_def.get("formula")
    value_path = metric_def.get("value_path")

    if formula == "ratio":
        numerator = _numeric_value(
            _path_value(payload, metric_def.get("numerator_path"))
        )
        denominator = _numeric_value(
            _path_value(payload, metric_def.get("denominator_path"))
        )
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator

    raw_value = _path_value(payload, value_path)
    if value_path is None and isinstance(payload, dict):
        raw_value = payload.get("value")

    numeric = _numeric_value(raw_value)
    if numeric is None:
        return None

    if formula == "inverse_one_plus":
        return _apply_value_bounds(
            _apply_value_scale(1.0 / (1.0 + numeric), metric_def),
            metric_def,
        )

    return _apply_value_bounds(_apply_value_scale(numeric, metric_def), metric_def)


class MetricsClient:
    """Metrics operations mixed into :class:`LocalClient`.

    All operations delegate to ``self.metrics_provider``.
    """

    metrics_provider: MetricsProvider

    # ── session-level metrics ─────────────────────────────────────────────

    def get_session_metrics(
        self,
        session_id: str,
        *,
        hops: int = 1,
        metric_names: list[str] | None = None,
    ) -> SessionMetricsResponse:
        """Return metrics attached to *session_id* in the KG."""
        results = self.metrics_provider.get_metrics(session_id, hops=hops)
        return SessionMetricsResponse(
            session_id=session_id,
            metrics=_metric_results_to_items(results, metric_names),
        )

    # ── span-level metrics ────────────────────────────────────────────────

    def get_span_metrics(
        self,
        span_id: str,
        *,
        session_id: str | None = None,
        hops: int = 1,
        metric_names: list[str] | None = None,
    ) -> SpanMetricsResponse:
        """Return metrics attached to a span in the KG."""
        results = self.metrics_provider.get_metrics(
            span_id,
            session_id=session_id,
            hops=hops,
        )
        return SpanMetricsResponse(
            session_id=session_id or "",
            span_id=span_id,
            metrics=_metric_results_to_items(results, metric_names),
        )

    # ── write metrics ─────────────────────────────────────────────────────

    def write_session_metrics(
        self,
        session_id: str,
        metrics: list[dict],
    ) -> dict:
        """Write metrics to a session node in the KG."""
        results = [
            MetricResult(
                metric_id=m["name"],
                resource_id=session_id,
                provider=m.get("provider", "API"),
                value=m.get("value"),
                reasoning=m.get("reasoning"),
                metadata={
                    "metric_id": m.get("metric_id"),
                    "source": m.get("source"),
                },
            )
            for m in metrics
        ]
        ok = self.metrics_provider.save_metrics(results)
        if ok:
            return {"written": len(results), "errors": []}
        return {"written": 0, "errors": ["provider save_metrics returned False"]}

    # ── category-level metrics ────────────────────────────────────────────

    def get_metrics_per_category(
        self,
        application_id: str,
        cat_key: str,
        *,
        agent_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        """Return metrics for a named category by delegating to ``get_metrics``.

        Looks up the configured metric definitions for ``cat_key`` in
        :data:`settings.METRIC_CATEGORIES` and calls ``get_metrics`` with the
        list of metric names.
        """
        categories = getattr(settings, "METRIC_CATEGORIES", {}) or {}
        cat_defs = categories.get(cat_key)
        if not cat_defs:
            raise DatabaseError(f"Unknown metric category '{cat_key}'")

        metric_names = list(cat_defs.keys())
        return self.get_metrics(
            application_id,
            metric_names,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )

    def get_metrics(
        self,
        application_id: str,
        metric_names: list[str],
        *,
        agent_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        """Return metric values in the same timeline structure as ``/charts``.

        Accepts an explicit list of metric names. Timeline metrics (those with
        an ``operation`` when a full metric definition is available) are
        time-bucketed into ``PERIODS_COUNT`` intervals and returned as
        ``list[TimelineData]``. Card-only metrics (``is_card=True`` or
        ``operation=None``) are returned as a single ``SingleValueData``.
        """
        metric_names = sorted({name for name in metric_names})
        query, params = metrics_queries.metrics_query(
            application_id,
            metric_names,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )
        logger.debug("query:\n%s", query)
        logger.debug("params: %s", params)
        try:
            rows = self.db.execute(query, params)
            logger.debug("rows returned: %d", len(rows) if rows else 0)
            if rows:
                logger.debug("first row: %s", rows[0])
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get metrics by category for '{application_id}': {exc}"
            ) from exc

        # Parse raw entries and collect epochs for bucketing
        entries_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        all_epochs: list[float] = []

        for row in rows:
            name = row.get("metricName", "")
            if not name:
                continue
            payload = _parse_metric_payload(row.get("metricResult"))
            value, _, _, _ = _parse_metric_result(row.get("metricResult"))
            if value is None:
                raw_value = row.get("value")
                if isinstance(raw_value, Real) and not isinstance(raw_value, bool):
                    value = float(raw_value)
            if payload is None and value is not None:
                payload = {"value": value}

            ts = row.get("timestamp")
            epoch = 0.0
            if hasattr(ts, "timestamp"):
                epoch = ts.timestamp()
            elif isinstance(ts, str):
                from oxp.client.utils import timestamp_to_epoch

                epoch = timestamp_to_epoch(ts)

            session_id = row.get("sessionId", "")
            entries_by_name[name].append(
                {
                    "payload": payload,
                    "epoch": epoch,
                    "session_id": session_id,
                }
            )
            if epoch > 0:
                all_epochs.append(epoch)

        # Determine time range for bucketing
        if all_epochs:
            data_start = min(all_epochs)
            data_end = max(all_epochs)
            if data_end - data_start < 10:
                data_end = data_start + 10
            period_size = (data_end - data_start) / (PERIODS_COUNT - 2)
            start_epoch = max(data_start - period_size, 0)
            end_epoch = data_end + period_size
        else:
            from oxp.client.utils import parse_epoch_range

            start_epoch, end_epoch = parse_epoch_range(start_time or "", end_time or "")

        period_size = (end_epoch - start_epoch) / PERIODS_COUNT

        result: dict[str, Any] = {}
        for metric_name in metric_names:
            mdef: dict[str, Any] = {}
            is_card = mdef.get("is_card", False)
            operation = mdef.get("operation")
            response_key = mdef.get("response_key", metric_name)
            unit = mdef.get("unit", "SCALAR")
            source_names = mdef.get("source_metrics", [metric_name])
            entries = [
                entry
                for source_name in source_names
                for entry in entries_by_name.get(source_name, [])
            ]
            values = [
                value
                for entry in entries
                if (value := _entry_value(entry.get("payload"), mdef)) is not None
            ]

            if is_card or operation is None:
                # Single value card
                agg_value = 0.0
                if values:
                    agg_value = sum(values) / len(values)
                result[response_key] = SingleValueData(value=agg_value, unit=unit)
            else:
                # Timeline with time buckets
                timeline: list[TimelineData] = []
                current = start_epoch
                while current < end_epoch:
                    bucket_end = current + period_size
                    bucket_entries = [
                        e for e in entries if current <= e["epoch"] < bucket_end
                    ]
                    bucket_values = [
                        value
                        for entry in bucket_entries
                        if (value := _entry_value(entry.get("payload"), mdef))
                        is not None
                    ]
                    bucket_sessions = list(
                        {e["session_id"] for e in bucket_entries if e["session_id"]}
                    )

                    agg_val = 0.0
                    if bucket_values:
                        if operation == "sum":
                            agg_val = sum(bucket_values)
                        elif operation == "average":
                            agg_val = sum(bucket_values) / len(bucket_values)

                    timestamp_iso = datetime.fromtimestamp(
                        current,
                        tz=timezone.utc,
                    ).isoformat()

                    timeline.append(
                        TimelineData(
                            timestamp=timestamp_iso,
                            sessionIDs=bucket_sessions,
                            value=SingleValueData(value=agg_val, unit=unit),
                        )
                    )
                    current = bucket_end

                result[response_key] = timeline

        return result

    def write_span_metrics(
        self,
        session_id: str,
        span_id: str,
        metrics: list[dict],
    ) -> dict:
        """Write metrics to a span node in the KG."""
        from oxp.providers import OXPMetricsProvider

        results = [
            MetricResult(
                metric_id=m["name"],
                resource_id=span_id,
                provider=m.get("provider", "API"),
                value=m.get("value"),
                reasoning=m.get("reasoning"),
                metadata={
                    "metric_id": m.get("metric_id"),
                    "source": m.get("source"),
                },
            )
            for m in metrics
        ]
        # Use span-specific save if the provider supports it
        if isinstance(self.metrics_provider, OXPMetricsProvider):
            ok = self.metrics_provider.save_span_metrics(
                session_id,
                span_id,
                results,
            )
        else:
            ok = self.metrics_provider.save_metrics(results)
        if ok:
            return {"written": len(results), "errors": []}
        return {"written": 0, "errors": ["provider save_metrics returned False"]}

    def get_application_metrics_summary(
        self,
        application_id: str,
    ) -> ApplicationMetricsSummary:
        """Return summary metrics grouped into reliability, quality, and performance."""

        reliability = []
        query, params = metrics_queries.reliability_metrics(
            application_id=application_id,
        )
        try:
            rows = self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get application reliability metrics for '{application_id}': {exc}"
            ) from exc

        for row in rows:
            metric_name = row["metricName"]
            if metric_name is None:
                # The reliability aggregation can emit rows with a null
                # metricName (e.g. a ConsistencyReport with no dataType, or the
                # completion-rate branch aggregating over zero matched metrics).
                # These are not meaningful metrics, so skip them instead of
                # letting MetricItem raise a ValidationError (which surfaces as
                # an unhandled 500 / misleading CORS error in the browser).
                continue
            reliability.append(MetricItem(name=metric_name, value=row["metricResult"]))

        quality = []
        query, params = metrics_queries.get_application_metrics_timeline(
            application_id=application_id,
            metrics=[
                "IntentRecognitionAccuracy",
                "Groundedness",
                "ToolUtilizationAccuracy",
                "AnswerRelevancy",
                "ResponseCompleteness",
            ],
        )
        try:
            rows = self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get application quality metrics for '{application_id}': {exc}"
            ) from exc

        for row in rows:
            quality.append(
                ApplicationMetricsTimeline(
                    metric_name=row["metricName"], values=row["dataPoints"]
                )
            )

        performance = []
        query, params = metrics_queries.get_application_metrics_timeline(
            application_id=application_id,
            metrics=[
                "WorkflowEfficiency",
                "CyclesCount",
                "LLMErrorRate",
                "ToolErrorRate",
            ],
        )
        try:
            rows = self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get application performance metrics for '{application_id}': {exc}"
            ) from exc

        for row in rows:
            performance.append(
                ApplicationMetricsTimeline(
                    metric_name=row["metricName"], values=row["dataPoints"]
                )
            )

        return ApplicationMetricsSummary(
            quality=quality,
            reliability=reliability,
            performance=performance,
        )
