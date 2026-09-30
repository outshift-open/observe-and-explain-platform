#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics.safety.execution_error_support import (
    count_execution_errors,
)


class ToolErrorRate(Metric):
    """Calculates the percentage of tool spans that resulted in an error. Input: Session context with tool_spans."""

    metadata = SpecRegistry.require("ToolErrorRate").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            required_entities=["mas:ToolCall"],
            scalar_fields=["contains_error"],
            include_edges=True,
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        tool_spans = context.get("tool_spans", [])

        if not tool_spans:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning="No tool spans found",
            )

        total_count = len(tool_spans)
        error_count = count_execution_errors(tool_spans)

        rate = (error_count / total_count) if total_count > 0 else 0.0

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=rate,
            metric_class=self.ontology_class,
            reasoning=f"{error_count}/{total_count} tool calls failed.",
        )
