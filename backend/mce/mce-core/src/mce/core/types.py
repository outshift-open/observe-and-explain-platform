#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime
from mce.core.metadata import format_metric_display_name


def normalize_metric_id(metric_id: str) -> str:
    """Strip a trailing ``Metric`` suffix from *metric_id* for backward-compat lookup.

    This is the single canonical normalisation used everywhere IDs are compared.
    ``removesuffix`` is safe — it only removes the suffix when it is present at
    the *end* of the string, unlike ``replace`` which would mangle a hypothetical
    ``MetricMetricFoo`` name.

    Examples::

        normalize_metric_id("AnswerRelevancyMetric") == "AnswerRelevancy"
        normalize_metric_id("AnswerRelevancy")       == "AnswerRelevancy"
    """
    return metric_id.removesuffix("Metric")


@dataclass
class MetricResult:
    """
    Unified result object for MCE v2.
    """

    # 1. Identity & Provenance (Common)
    metric_id: str
    resource_id: str
    provider: str
    timestamp: datetime = field(default_factory=datetime.now)

    # 2. Value (Common)
    value: float = 0.0
    # score is a read-only alias for value — kept for backward compat.
    # Do NOT pass score= to the constructor; it has no effect.
    reasoning: str = ""

    @property
    def score(self) -> float:
        """Normalized score — always equal to value (backward-compat alias)."""
        return self.value

    # 3. Metadata
    metric_class: str = "Metric"
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def display_name(self) -> str:
        """Human-readable name. Delegates to format_metric_display_name()."""
        return format_metric_display_name(self.metric_id)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Convert to the old dictionary format expected by V1 consumers/db."""
        return {
            "metricName": self.metric_id,
            "value": self.value,
            "score": self.value,  # derived from value — not a separate field
            "reasoning": self.reasoning,
            "provider": self.provider,
            "timestamp": self.timestamp.isoformat(),
            "type": self.metadata.get("legacy_type", "Quality"),
        }


# Aliases for backward compatibility with mce.core.types
NumericMetricResult = MetricResult
BaseMetricResult = MetricResult


@dataclass
class LLMJudgeResult(MetricResult):
    """
    Specific result for Generative Metrics (LLM-as-a-Judge).
    """

    input_text: str = ""
    output_text: str = ""
    evaluation_steps: list[str] = field(default_factory=list)
    tokens_used: int = 0
    model_name: str = ""

    def to_legacy_dict(self) -> dict[str, Any]:
        base = super().to_legacy_dict()
        base.update(
            {
                "model": self.model_name,
                "tokens": self.tokens_used,
                "input_preview": self.input_text[:50],
            }
        )
        return base
