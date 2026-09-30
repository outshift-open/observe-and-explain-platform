#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry


class ToolError(Metric):
    """Checks if a specific tool execution resulted in an error. Input: mas:ToolCall"""

    metadata = SpecRegistry.require("ToolError").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            scalar_fields=["contains_error"],
            required_entities=["mas:ToolCall"],
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        # contains_error is derived by the provider from the ToolCall's own
        # `success` field (contains_error = success is False; no signal
        # recorded is not a failure) -- there is no raw status_code/error
        # field on the KG node itself.
        is_error = bool(context.get("contains_error"))

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=1.0 if is_error else 0.0,
            metric_class=self.ontology_class,
            reasoning="Tool execution failed" if is_error else "Success",
        )
