#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Utility helpers for deterministic trajectory-context metrics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from stateful_evals_be.evaluation.trajectory_context import (
    ClaimEntry,
    EvidenceFact,
    IntentEntry,
    TrajectoryContext,
)

from .base import EvidenceRef, HighLevelMetricFailure, MetricInputConfig


def compact(text: str, limit: int = 240) -> str:
    normalized = " ".join(str(text).split())
    return normalized[: limit - 3] + "..." if len(normalized) > limit else normalized


def selected_claims(
    context: TrajectoryContext, config: MetricInputConfig | None = None
) -> list[ClaimEntry]:
    if config is None:
        return list(context.claims)
    if not config.includes("claims"):
        return []
    claims = list(context.claims)
    if config.max_claims is not None:
        claims = claims[-config.max_claims :]
    return claims


def selected_evidence(
    context: TrajectoryContext, config: MetricInputConfig | None = None
) -> list[EvidenceFact]:
    if config is None:
        return list(context.evidence)
    selected: list[EvidenceFact] = []
    fact_count = 0
    for fact in context.evidence:
        if fact.fact_type == "policy_rule" and config.includes("policy"):
            selected.append(fact)
            continue
        if fact.fact_type == "user_statement" and config.includes("user_statements"):
            selected.append(fact)
            continue
        if fact.fact_type not in {"policy_rule", "user_statement"} and config.includes(
            "fact_store"
        ):
            selected.append(fact)
            fact_count += 1

    if config.max_facts is None or fact_count <= config.max_facts:
        return selected

    non_fact = [
        fact for fact in selected if fact.fact_type in {"policy_rule", "user_statement"}
    ]
    facts = [
        fact
        for fact in selected
        if fact.fact_type not in {"policy_rule", "user_statement"}
    ]
    return non_fact + facts[-config.max_facts :]


def user_text(
    context: TrajectoryContext, config: MetricInputConfig | None = None
) -> str:
    if config is not None and not config.includes("user_statements"):
        return ""
    return "\n".join(
        f.content
        for f in selected_evidence(context, config)
        if f.fact_type == "user_statement"
    )


def final_answer_text(
    context: TrajectoryContext, config: MetricInputConfig | None = None
) -> str:
    if config is not None and not config.includes("final_answer"):
        return ""
    try:
        return str(context.get_final_answer_context().get("final_answer") or "")
    except Exception:
        return "\n\n".join(
            c.content
            for c in context.claims
            if c.claim_type in {"assertion", "completion_claim"}
        )


def all_claim_text(
    context: TrajectoryContext, config: MetricInputConfig | None = None
) -> str:
    return "\n".join(claim.content for claim in selected_claims(context, config))


def all_evidence_text(
    context: TrajectoryContext, config: MetricInputConfig | None = None
) -> str:
    return "\n".join(fact.content for fact in selected_evidence(context, config))


def fact_store_text(
    context: TrajectoryContext, config: MetricInputConfig | None = None
) -> str:
    if config is not None and not config.includes("fact_store"):
        return ""
    return "\n".join(
        fact.content
        for fact in selected_evidence(context, config)
        if fact.fact_type in {"tool_output", "policy_rule", "user_statement"}
    )


def evidence_ref(
    item: EvidenceFact | ClaimEntry | IntentEntry, kind: str
) -> EvidenceRef:
    if isinstance(item, EvidenceFact):
        return EvidenceRef(
            span_index=item.span_index,
            source_name=item.source_name,
            kind=kind or item.fact_type,
            content=compact(item.content),
        )
    if isinstance(item, ClaimEntry):
        return EvidenceRef(
            span_index=item.span_index,
            source_name=item.entity_name,
            kind=kind or item.claim_type,
            content=compact(item.content),
        )
    return EvidenceRef(
        span_index=item.last_seen,
        source_name=item.name,
        kind=kind or item.source,
        content=compact("; ".join(str(e) for e in item.events[-3:])),
    )


def fatal(
    metric_name: str,
    *,
    span_index: int = -1,
    entity_name: str = "",
    reasoning: str,
    explanation: str = "",
    observed_impact: str = "",
    confidence: float = 0.7,
    evidence: Iterable[EvidenceRef] = (),
) -> HighLevelMetricFailure:
    return HighLevelMetricFailure(
        classification="FATAL",
        high_level_metric=metric_name,
        span_index=span_index,
        entity_name=entity_name,
        reasoning=reasoning,
        explanation=explanation,
        observed_impact=observed_impact,
        confidence=confidence,
        evidence=list(evidence),
    )


def minor(
    metric_name: str,
    *,
    span_index: int = -1,
    entity_name: str = "",
    reasoning: str,
    explanation: str = "",
    observed_impact: str = "",
    confidence: float = 0.4,
    evidence: Iterable[EvidenceRef] = (),
) -> HighLevelMetricFailure:
    return HighLevelMetricFailure(
        classification="MINOR",
        high_level_metric=metric_name,
        span_index=span_index,
        entity_name=entity_name,
        reasoning=reasoning,
        explanation=explanation,
        observed_impact=observed_impact,
        confidence=confidence,
        evidence=list(evidence),
    )


def get_field(
    obj: Mapping[str, Any] | Any | None, field: str, default: Any = None
) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(field, default)
    return getattr(obj, field, default)


def normalize_failures(items: Any) -> list[dict[str, Any]]:
    if not items:
        return []
    output: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            output.append(dict(item))
        elif hasattr(item, "model_dump"):
            output.append(item.model_dump())
        elif hasattr(item, "__dict__"):
            output.append(dict(item.__dict__))
        else:
            output.append({"reasoning": str(item)})
    return output
