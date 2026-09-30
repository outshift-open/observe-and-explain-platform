#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared payload models for trajectory-context extension metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

CONTEXT_COMPONENTS = frozenset(
    {
        "policy",
        "intents",
        "claims",
        "fact_store",
        "user_statements",
        "final_answer",
        "operations",
        "coordination",
    }
)


@dataclass(frozen=True)
class MetricInputConfig:
    """Controls which trajectory-context components a metric may inspect."""

    components: frozenset[str] = CONTEXT_COMPONENTS
    max_claims: int | None = None
    max_facts: int | None = None

    def includes(self, component: str) -> bool:
        return component in self.components

    def to_payload(self) -> dict[str, Any]:
        return {
            "components": sorted(self.components),
            "max_claims": self.max_claims,
            "max_facts": self.max_facts,
        }


def metric_input_config(
    *components: str,
    max_claims: int | None = None,
    max_facts: int | None = None,
) -> MetricInputConfig:
    """Build a metric input config with validation."""
    selected = frozenset(components) if components else CONTEXT_COMPONENTS
    unknown = selected - CONTEXT_COMPONENTS
    if unknown:
        raise ValueError(f"Unknown trajectory context components: {sorted(unknown)}")
    return MetricInputConfig(
        components=selected,
        max_claims=max_claims,
        max_facts=max_facts,
    )


@dataclass(frozen=True)
class EvidenceRef:
    """Compact pointer to the context item behind a metric decision."""

    span_index: int
    source_name: str
    kind: str
    content: str = ""
    artifact_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "span_index": self.span_index,
            "source_name": self.source_name,
            "kind": self.kind,
            "content": self.content,
            "artifact_id": self.artifact_id,
        }


@dataclass
class HighLevelMetricFailure:
    """Stateful-eval-style failure record for a high-level metric."""

    classification: str
    high_level_metric: str
    span_index: int
    entity_name: str
    reasoning: str
    explanation: str = ""
    observed_impact: str = ""
    confidence: float = 0.7
    evidence: list[EvidenceRef] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "high_level_metric": self.high_level_metric,
            "span_index": self.span_index,
            "entity_name": self.entity_name,
            "reasoning": self.reasoning,
            "explanation": self.explanation,
            "observed_impact": self.observed_impact,
            "confidence": self.confidence,
            "evidence": [ref.to_payload() for ref in self.evidence],
        }


@dataclass
class HighLevelMetricResult:
    """Binary result payload for a trajectory-context extension metric."""

    high_level_metric: str
    score: int | None
    reasoning: str
    status: str = ""
    fatal_failures: list[HighLevelMetricFailure] = field(default_factory=list)
    minor_failures: list[HighLevelMetricFailure] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status:
            self.status = (
                "unknown"
                if self.score is None
                else "pass"
                if self.score == 1
                else "fail"
            )
        if self.status not in {"pass", "fail", "not_applicable", "unknown"}:
            raise ValueError(f"Unknown metric result status: {self.status!r}")

    def to_payload(self) -> dict[str, Any]:
        return {
            "high_level_metric": self.high_level_metric,
            "score": int(self.score) if self.score is not None else None,
            "status": self.status,
            "reasoning": self.reasoning,
            "fatal_failures": [f.to_payload() for f in self.fatal_failures],
            "minor_failures": [f.to_payload() for f in self.minor_failures],
            "evidence": [ref.to_payload() for ref in self.evidence],
            "total_fatal": len(self.fatal_failures),
            "total_minor": len(self.minor_failures),
            "metadata": self.metadata,
        }


class TrajectoryContextMetric(Protocol):
    """Metric implementation that reads the accumulated trajectory context."""

    name: str

    def evaluate(
        self,
        context: Any,
        *,
        stateful_result: Mapping[str, Any] | Any | None = None,
    ) -> HighLevelMetricResult:
        """Return a binary high-level metric result."""
