#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Agentic-protocols metrics implementation for :class:`UIClient`."""

from __future__ import annotations

import logging
import math
from typing import Optional

from oxp.client.utils import epoch_to_dt_str, parse_epoch_range
from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.models.otel_traces import (
    AgenticProtocolsMetricsResponse,
    SLIMMetricsData,
    SingleValueData,
)
from oxp.query_builders import ui as ui_queries

logger = logging.getLogger(__name__)

# ── metric name constants ──────────────────────────────────────────────────────

_SLIM_MESSAGES_PROCESSED = "slim.messages.processed"
_SLIM_MESSAGES_RECEIVED = "slim.messages.received"
_SLIM_PROCESSING_TIME = "slim.message.processing_time"

# ── reset-aware aggregation helpers ───────────────────────────────────────────


def _aggregate_sum_values(values: list[float]) -> float:
    """Aggregate a monotonically-increasing counter sequence, handling resets.

    Mirrors the Go ``GetSLIMSumMetricByAgent`` logic: the counter may reset to
    zero when an agent restarts.  The total is the sum of each monotone segment.
    """
    if not values:
        return 0.0

    first_sequence = True
    old = -1.0
    first_val = 0.0
    total = 0.0

    for v in values:
        if old == -1.0:
            first_val = v
        if v < old:
            if first_sequence:
                total += old - first_val
                first_sequence = False
            else:
                total += old
        old = v

    if first_sequence:
        total += old - first_val
    else:
        total += old

    return total


def _aggregate_histogram_values(
    pairs: list[tuple[float, float]],
) -> tuple[float, float]:
    """Aggregate ``(Count, Sum)`` histogram pairs, handling resets.

    Mirrors Go ``GetSLIMHistogramMetricByAgent``.  Returns ``(total_sum,
    total_count)``.
    """
    if not pairs:
        return 0.0, 0.0

    first_sequence = True
    old_count = -1.0
    old_sum = -1.0
    first_count = 0.0
    first_sum = 0.0
    total_count = 0.0
    total_sum = 0.0

    for count, s in pairs:
        if old_count == -1.0:
            first_count = count
            first_sum = s
        if count < old_count:
            if first_sequence:
                total_sum += old_sum - first_sum
                total_count += old_count - first_count
                first_sequence = False
            else:
                total_sum += old_sum
                total_count += old_count
        old_count = count
        old_sum = s

    if first_sequence:
        total_sum += old_sum - first_sum
        total_count += old_count - first_count
    else:
        total_sum += old_sum
        total_count += old_count

    return total_sum, total_count


# ── per-metric queries ─────────────────────────────────────────────────────────


def _get_slim_sum_metric(
    db: Connector,
    *,
    app_prefix: str,
    metric_name: str,
    start_time: str,
    end_time: str,
) -> float:
    """Return the total value for a SLIM sum metric across all agents."""
    agents_stmt = ui_queries.slim_agent_names_sum_query(
        app_prefix=app_prefix,
        metric_name=metric_name,
        start_time=start_time,
        end_time=end_time,
    )
    try:
        agent_rows = db.execute(agents_stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get SLIM agent names for metric '{metric_name}': {exc}"
        ) from exc

    total = 0.0
    for row in agent_rows:
        agent_name = str(row[0]) if row[0] else ""
        if not agent_name:
            continue

        values_stmt = ui_queries.slim_sum_values_by_agent_query(
            agent_name=agent_name,
            metric_name=metric_name,
            start_time=start_time,
            end_time=end_time,
        )
        try:
            value_rows = db.execute(values_stmt)
        except Exception as exc:
            logger.error(
                "Failed to get SLIM sum values for agent '%s': %s", agent_name, exc
            )
            continue

        values = [float(r[0]) for r in value_rows if r[0] is not None]
        total += _aggregate_sum_values(values)

    return total


def _get_slim_histogram_metric(
    db: Connector,
    *,
    app_prefix: str,
    metric_name: str,
    start_time: str,
    end_time: str,
) -> float:
    """Return the mean value for a SLIM histogram metric (sum/count) across all agents."""
    agents_stmt = ui_queries.slim_agent_names_histogram_query(
        app_prefix=app_prefix,
        metric_name=metric_name,
        start_time=start_time,
        end_time=end_time,
    )
    try:
        agent_rows = db.execute(agents_stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get SLIM histogram agent names for metric '{metric_name}': {exc}"
        ) from exc

    total_sum = 0.0
    total_count = 0.0

    for row in agent_rows:
        agent_name = str(row[0]) if row[0] else ""
        if not agent_name:
            continue

        values_stmt = ui_queries.slim_histogram_values_by_agent_query(
            agent_name=agent_name,
            metric_name=metric_name,
            start_time=start_time,
            end_time=end_time,
        )
        try:
            value_rows = db.execute(values_stmt)
        except Exception as exc:
            logger.error(
                "Failed to get SLIM histogram values for agent '%s': %s",
                agent_name,
                exc,
            )
            continue

        pairs = [
            (float(r[0]), float(r[1]))
            for r in value_rows
            if r[0] is not None and r[1] is not None
        ]
        agent_sum, agent_count = _aggregate_histogram_values(pairs)
        total_sum += agent_sum
        total_count += agent_count

    if total_count == 0:
        return 0.0
    return total_sum / total_count


# ── public entry point ────────────────────────────────────────────────────────


def _get_agentic_protocols_metrics(
    db: Connector,
    *,
    application: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> AgenticProtocolsMetricsResponse:
    """Return SLIM agentic-protocol metrics for *application*."""
    start_epoch, end_epoch = parse_epoch_range(start_time or "", end_time or "")
    start_dt = epoch_to_dt_str(start_epoch)
    end_dt = epoch_to_dt_str(end_epoch)

    app_prefix = application.lower()

    messages_processed = _get_slim_sum_metric(
        db,
        app_prefix=app_prefix,
        metric_name=_SLIM_MESSAGES_PROCESSED,
        start_time=start_dt,
        end_time=end_dt,
    )

    processing_time_raw = _get_slim_histogram_metric(
        db,
        app_prefix=app_prefix,
        metric_name=_SLIM_PROCESSING_TIME,
        start_time=start_dt,
        end_time=end_dt,
    )
    # Convert seconds → milliseconds, rounded to 2 decimal places
    processing_time = math.floor(processing_time_raw * 1000 * 100) / 100

    messages_received = _get_slim_sum_metric(
        db,
        app_prefix=app_prefix,
        metric_name=_SLIM_MESSAGES_RECEIVED,
        start_time=start_dt,
        end_time=end_dt,
    )

    if messages_received == 0:
        success_rate = 1.0
    else:
        success_rate = messages_processed / messages_received

    error_rate = 1.0 - success_rate

    return AgenticProtocolsMetricsResponse(
        slimMetrics=SLIMMetricsData(
            processingTime=SingleValueData(
                value=processing_time,
                unit="MILLISECONDS",
            ),
            messagesProcessed=SingleValueData(
                value=messages_processed,
                unit="SCALAR",
            ),
            successRate=SingleValueData(
                value=round(success_rate * 100, 2),
                unit="PERCENTAGE",
            ),
            errorRate=SingleValueData(
                value=round(error_rate * 100, 2),
                unit="PERCENTAGE",
            ),
        )
    )
