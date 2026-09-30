#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics.safety.execution_error_support import (
    count_execution_errors,
)


class LLMErrorRate(Metric):
    """Calculates the percentage of LLM calls that resulted in an error."""

    metadata = SpecRegistry.require("LLMErrorRate").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return SpecRegistry.require("LLMErrorRate").input_requirements

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        llm_spans = context.get("llm_spans", [])

        if not llm_spans:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning="No LLM calls found",
            )

        error_count = count_execution_errors(llm_spans)
        total_count = len(llm_spans)
        rate = error_count / total_count if total_count else 0.0

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=rate,
            metric_class=self.ontology_class,
            reasoning=f"{error_count}/{total_count} LLM calls failed.",
            metadata={
                "error_count": error_count,
                "total_count": total_count,
            },
        )
