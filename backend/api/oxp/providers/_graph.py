#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""How a metric becomes ontology ``Metric`` / ``MetricResult`` properties, shared by the metric writers."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from oxp.interfaces.models import MetricResult
from oxp.query_builders import metric_graph

logger = logging.getLogger(__name__)


def _metric_property_value(value: Any) -> str:
    """Serialize complex metric metadata into a Neo4j property-safe value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _graph_properties(
    metric: MetricResult, resource_id: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """The metric as the ontology's ``Metric`` and ``MetricResult``; ``None`` (logged) if it does not fit."""
    provider = metric.provider or "API"
    timestamp = getattr(metric, "timestamp", None)
    if isinstance(timestamp, datetime):
        timestamp = timestamp.astimezone(UTC)
    else:
        timestamp = None
    try:
        return (
            metric_graph.metric_definition_properties(metric.metric_id, provider),
            metric_graph.metric_result_properties(
                metric_name=metric.metric_id,
                provider=provider,
                resource_id=resource_id,
                value=metric.value,
                reasoning=_metric_property_value(metric.reasoning),
                metadata=metric.metadata,
                timestamp=timestamp,
            ),
        )
    except ValidationError as exc:
        logger.error(
            "Not saving %s for %s: it does not match the ontology Metric/MetricResult: %s",
            metric.metric_id,
            resource_id,
            exc,
        )
        return None
