#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from abc import ABC, abstractmethod
import math
from statistics import mean
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry


def _find_logprobs_block(obj: Any, _depth: int = 0) -> Any:
    """Recursively search for a 'logprobs' dict block (max depth 5).

    Stops early to avoid traversing arbitrarily deep payloads.
    """
    if _depth > 5:
        return None
    if isinstance(obj, dict):
        if "logprobs" in obj and isinstance(obj["logprobs"], dict):
            return obj["logprobs"]
        for v in obj.values():
            result = _find_logprobs_block(v, _depth + 1)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_logprobs_block(item, _depth + 1)
            if result is not None:
                return result
    return None


def _extract_logprobs(span_dict: dict[str, Any]) -> list[float]:
    """Extract per-token logprobs from a span output dict.

    Tries ``output_payload.logprobs`` first; falls back to a deep search.
    Returns an empty list if no logprobs block is found.
    """
    output_payload = span_dict.get("output_payload") or span_dict.get("output")
    if not isinstance(output_payload, dict):
        return []

    logprobs_block = output_payload.get("logprobs")
    if not isinstance(logprobs_block, dict):
        logprobs_block = _find_logprobs_block(output_payload)
    if not isinstance(logprobs_block, dict):
        return []

    content = logprobs_block.get("content")
    if not isinstance(content, list):
        return []

    logprobs: list[float] = []
    for token_dict in content:
        logprob = token_dict.get("logprob")
        if isinstance(logprob, (int, float)):
            logprobs.append(float(logprob))
    return logprobs


def _session_logprobs(context: dict[str, Any]) -> list[float]:
    """Aggregate logprobs from all LLM spans present in *context*."""
    spans = context.get("llm_spans") or []
    if not spans:
        session = context.get("session")
        if session is not None and hasattr(session, "llm_spans"):
            spans = session.llm_spans or []

    logprobs: list[float] = []
    for span in spans:
        span_dict = span if isinstance(span, dict) else getattr(span, "__dict__", {})
        logprobs.extend(_extract_logprobs(span_dict))
    return logprobs


class _BaseUncertaintyMetric(Metric, ABC):
    """Base for logprobs-based confidence metrics."""

    @property
    def input_requirements(self) -> MetricRequirements:
        # Reads llm_spans (or session.llm_spans) from context.
        return MetricRequirements(scalar_fields=["llm_spans"])

    @abstractmethod
    def _score(self, logprobs: list[float]) -> float:
        """Compute a scalar confidence score from a list of token logprobs."""

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        logprobs = _session_logprobs(context)
        if not logprobs:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning="No logprobs found in llm_spans.",
            )
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=self._score(logprobs),
            metric_class=self.ontology_class,
        )


class LLMAverageConfidence(_BaseUncertaintyMetric):
    """Arithmetic mean of per-token probabilities across all LLM spans."""

    metadata = SpecRegistry.require("LLMAverageConfidence").metadata

    def _score(self, logprobs: list[float]) -> float:
        # exp(logprob) converts each token log-probability to a probability in [0,1].
        # Taking the arithmetic mean gives the average per-token confidence.
        return mean(math.exp(lp) for lp in logprobs)


class LLMMinimumConfidence(_BaseUncertaintyMetric):
    """Minimum per-token probability — the worst-case token confidence."""

    metadata = SpecRegistry.require("LLMMinimumConfidence").metadata

    def _score(self, logprobs: list[float]) -> float:
        return math.exp(min(logprobs))


class LLMMaximumConfidence(_BaseUncertaintyMetric):
    """Maximum per-token probability — the best-case token confidence."""

    metadata = SpecRegistry.require("LLMMaximumConfidence").metadata

    def _score(self, logprobs: list[float]) -> float:
        return math.exp(max(logprobs))
