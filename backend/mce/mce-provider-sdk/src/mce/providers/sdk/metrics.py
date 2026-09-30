#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any

from mce.core.metric import Metric, MetricRequirements
from mce.core.metadata import MetricMetadata, MetricLayer, MetricNature, MetricScope
from mce.core.types import MetricResult

# SDK-backed telemetry metrics sourced directly from OTel attributes.


def _first_number(context: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        value = context.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


class DurationMetric(Metric):
    metadata = MetricMetadata(
        name="duration_ms",
        description="Measures span duration/latency.",
        layer=MetricLayer.EXECUTION,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.EXECUTION_ELEMENT,
        ontology_class="Duration",
    )

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            scalar_fields=["duration_ms", "latency", "duration"],
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        val = _first_number(context, ["duration_ms", "latency", "duration"])
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="SDK",
            value=val,
            metric_class=self.ontology_class,
        )


class TokenCountMetric(Metric):
    metadata = MetricMetadata(
        name="token_count",
        description="Counts total tokens usage.",
        layer=MetricLayer.EXECUTION,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.EXECUTION_ELEMENT,
        ontology_class="TokenCount",
    )

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            scalar_fields=["total_tokens", "prompt_tokens", "completion_tokens"],
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        total_tokens = _first_number(
            context,
            [
                "total_tokens",
                "token_count",
            ],
        )

        if total_tokens == 0.0:
            prompt_tokens = _first_number(context, ["prompt_tokens", "input_tokens"])
            completion_tokens = _first_number(
                context,
                ["completion_tokens", "output_tokens"],
            )
            total_tokens = prompt_tokens + completion_tokens

        if total_tokens == 0.0 and isinstance(context.get("token_usage"), dict):
            total_tokens = float(context["token_usage"].get("total", 0.0))
        if total_tokens == 0.0 and isinstance(context.get("usage"), dict):
            total_tokens = float(context["usage"].get("total_tokens", 0.0))

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="SDK",
            value=total_tokens,
            metric_class=self.ontology_class,
        )


class CostMetric(Metric):
    metadata = MetricMetadata(
        name="cost",
        description="Measures the cost associated with a span.",
        layer=MetricLayer.RAW,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.EXECUTION_ELEMENT,
        ontology_class="Cost",
    )

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            scalar_fields=["cost", "total_cost", "cost_usd", "cost_per_token"],
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        cost = _first_number(context, ["cost", "total_cost", "cost_usd"])
        if cost == 0.0:
            cost_per_token = _first_number(context, ["cost_per_token"])
            total_tokens = _first_number(context, ["total_tokens", "token_count"])
            if cost_per_token and total_tokens:
                cost = cost_per_token * total_tokens

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="SDK",
            value=cost,
            metric_class=self.ontology_class,
        )
