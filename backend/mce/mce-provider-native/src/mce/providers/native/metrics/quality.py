#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.metric import (
    Metric,
    MetricMetadata,
    MetricLayer,
    MetricNature,
    MetricScope,
    MetricResult,
    MetricRequirements,
)


class Tonality(Metric):
    """Evaluates whether the output matches the intended communication style.

    .. note:: Not yet implemented — returns an error result when computed.
    """

    def __init__(self) -> None:
        self.metadata = MetricMetadata(
            name="Tonality",
            description="Evaluates whether the output matches the intended communication style.",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.STOCHASTIC,
            scope=MetricScope.EXECUTION_ELEMENT,
            ontology_class="Tonality",
        )

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(text_fields=["input", "output"])

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=0.0,
            metric_class=self.ontology_class,
            error="Tonality is not yet implemented.",
        )


class UncertaintyScore(Metric):
    """Quantifies the model's overall confidence score.

    .. note:: Not yet implemented — returns an error result when computed.
              For a working logprob-based implementation see ``LLMAverageConfidence``.
    """

    def __init__(self) -> None:
        self.metadata = MetricMetadata(
            name="UncertaintyScore",
            description="Quantifies the model's confidence.",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.DETERMINISTIC,
            attachment_point="mas:LLMCall",
            scope=MetricScope.EXECUTION_ELEMENT,
            ontology_class="UncertaintyScore",
        )

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(scalar_fields=["llm_spans"])

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=0.0,
            metric_class=self.ontology_class,
            error="UncertaintyScore is not yet implemented. Use LLMAverageConfidence instead.",
        )
