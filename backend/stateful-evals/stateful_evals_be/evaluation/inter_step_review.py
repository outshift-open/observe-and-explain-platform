#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Inter-step review: post-processing analysis of metric failures.

After span-level metrics identify failures (score=0), this module reviews
them in the context of the full trajectory and policy to determine:
1. Which failures are genuinely trajectory-breaking (FATAL)
2. Which are recoverable intermediate missteps (MINOR)
3. Whether trajectory-level failure patterns exist (loops, abandonment, etc.)

Replaces the old per-failure fatal_failure analysis with a single
trajectory-aware review pass.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List

import litellm
from metrics_computation_engine.llm_judge.llm import LLMClient

from stateful_evals_be.models.requests import FailureDetail, MetricFailure
from stateful_evals_be.prompts.inter_step_review import (
    INTER_STEP_REVIEW_SYSTEM_PROMPT,
    INTER_STEP_REVIEW_USER_PROMPT,
)

litellm.drop_params = True

logger = logging.getLogger("stateful_evals_be.inter_step_review")

_MAX_FAILURES_PER_BATCH = 15


def _compact_preview(payload: Any, max_chars: int = 400) -> str:
    if payload is None:
        return "None"
    try:
        text = json.dumps(payload, ensure_ascii=True, default=str)
    except Exception:
        text = str(payload)
    text = re.sub(r"\s+", " ", text).strip()
    return f"{text[:max_chars]}... [truncated]" if len(text) > max_chars else text


def _format_failures_for_review(failures: List[MetricFailure]) -> str:
    """Format failures into a structured string for the LLM reviewer."""
    lines: List[str] = []
    for i, f in enumerate(failures):
        lines.append(
            f"### Failure {i + 1}\n"
            f"- Span index: {f.span_index} (step {f.span_index + 1})\n"
            f"- Span type: {f.span_type}\n"
            f"- Entity: {f.entity_name}\n"
            f"- Metric: {f.metric_name}\n"
            f"- Score: {f.score}\n"
            f"- Reasoning: {f.reasoning}\n"
            f"- Input excerpt: {_compact_preview(f.input_payload)}\n"
            f"- Output excerpt: {_compact_preview(f.output_payload)}\n"
        )
    return "\n".join(lines)


def run_inter_step_review(
    failures: List[MetricFailure],
    trajectory_summary: str,
    policy: str,
    llm_client: LLMClient,
    aftermath: str = "",
) -> Dict[str, Any]:
    """Review all span-level failures in trajectory context.

    Returns:
        Dict with:
        - fatal_failures: List[FailureDetail]
        - minor_failures: List[FailureDetail]
        - trajectory_patterns: List[str]
        - overall_assessment: str
        - usage: token usage dict
    """
    if not failures:
        return {
            "fatal_failures": [],
            "minor_failures": [],
            "trajectory_patterns": [],
            "overall_assessment": "No failures to review.",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    review_failures = failures[:_MAX_FAILURES_PER_BATCH]
    failures_text = _format_failures_for_review(review_failures)

    user_prompt = INTER_STEP_REVIEW_USER_PROMPT.format(
        policy=policy[:3000] if policy else "No policy provided.",
        trajectory_summary=trajectory_summary[:4000],
        failures=failures_text,
        aftermath=aftermath or "End of trajectory.",
    )

    messages = [
        {"role": "system", "content": INTER_STEP_REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    usage_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    model_name = os.getenv("LLM_MODEL_NAME", "")
    temperature = 1.0 if "claude-sonnet" in model_name.casefold() else 0.0

    try:
        response = llm_client.query(
            messages,
            temperature=temperature,
            max_tokens=2000,
            reasoning_effort="low",
        )
        result_text = response.choices[0].message.content

        if hasattr(response, "usage") and response.usage:
            usage_tokens["prompt_tokens"] = (
                getattr(response.usage, "prompt_tokens", 0) or 0
            )
            usage_tokens["completion_tokens"] = (
                getattr(response.usage, "completion_tokens", 0) or 0
            )
            usage_tokens["total_tokens"] = (
                getattr(response.usage, "total_tokens", 0) or 0
            )

        if not result_text:
            return _fallback_all_fatal(review_failures, usage_tokens)

        result_text = result_text.strip()
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        if result_text.startswith("{{"):
            result_text = result_text.replace("{{", "{").replace("}}", "}")

        parsed = json.loads(result_text)
        return _build_review_result(review_failures, parsed, usage_tokens)

    except json.JSONDecodeError:
        logger.warning(
            "Inter-step review returned non-JSON; falling back to heuristic."
        )
        return _fallback_heuristic(review_failures, usage_tokens)
    except Exception as e:
        logger.error(f"Inter-step review failed: {e}")
        return _fallback_heuristic(review_failures, usage_tokens)


def _build_review_result(
    failures: List[MetricFailure],
    parsed: Dict[str, Any],
    usage: Dict[str, int],
) -> Dict[str, Any]:
    """Convert parsed LLM review into structured result."""
    fatal_failures: List[FailureDetail] = []
    minor_failures: List[FailureDetail] = []

    reviewed_indices = set()
    for item in parsed.get("failures", []):
        span_idx = item.get("span_index", -1)
        metric = item.get("metric", "")
        verdict = str(item.get("verdict", "MINOR")).upper()
        severity = float(item.get("severity", 0.5))
        severity = max(0.0, min(1.0, severity))
        explanation = str(item.get("explanation", ""))
        pattern = item.get("pattern", "none")
        self_corrected = bool(item.get("self_corrected", False))
        policy_compliant = bool(item.get("policy_compliant", False))
        is_hard_rule = bool(item.get("hard_rule_violation", False))

        matching_failure = next(
            (
                f
                for f in failures
                if f.span_index == span_idx and f.metric_name == metric
            ),
            None,
        )
        if not matching_failure:
            matching_failure = next(
                (f for f in failures if f.span_index == span_idx),
                None,
            )
        if not matching_failure:
            continue

        reviewed_indices.add(failures.index(matching_failure))

        if is_hard_rule:
            verdict = "FATAL"
            severity = max(severity, 1.0)
        elif self_corrected or policy_compliant:
            verdict = "MINOR"

        detail = FailureDetail(
            metric=matching_failure.metric_name,
            metric_score=matching_failure.score,
            fatality_score=severity,
            reasoning=matching_failure.reasoning,
            explanation=explanation,
            span_index=matching_failure.span_index,
            span_id=matching_failure.span_id or "",
            span_type=matching_failure.span_type,
            entity_name=matching_failure.entity_name or "",
            observed_impact=pattern if pattern != "none" else "none",
            confidence=severity,
            self_corrected=self_corrected,
            policy_compliant=policy_compliant,
            hard_rule_violation=is_hard_rule,
        )

        if verdict == "FATAL" and severity >= 0.5:
            fatal_failures.append(detail)
        else:
            minor_failures.append(detail)

    for i, failure in enumerate(failures):
        if i in reviewed_indices:
            continue
        minor_failures.append(
            FailureDetail(
                metric=failure.metric_name,
                metric_score=failure.score,
                fatality_score=0.3,
                reasoning=failure.reasoning,
                explanation="Not reviewed in inter-step analysis; defaulting to minor.",
                span_index=failure.span_index,
                span_id=failure.span_id or "",
                span_type=failure.span_type,
                entity_name=failure.entity_name or "",
                observed_impact="none",
                confidence=0.3,
            )
        )

    return {
        "fatal_failures": fatal_failures,
        "minor_failures": minor_failures,
        "trajectory_patterns": parsed.get("trajectory_patterns", []),
        "overall_assessment": parsed.get("overall_assessment", ""),
        "usage": usage,
    }


def _fallback_all_fatal(
    failures: List[MetricFailure], usage: Dict[str, int]
) -> Dict[str, Any]:
    """When LLM returns empty, conservatively mark all as fatal."""
    fatal = [
        FailureDetail(
            metric=f.metric_name,
            metric_score=f.score,
            fatality_score=1.0,
            reasoning=f.reasoning,
            explanation="Empty LLM response; defaulting to fatal.",
            span_index=f.span_index,
            span_id=f.span_id or "",
            span_type=f.span_type,
            entity_name=f.entity_name or "",
            observed_impact="none",
            confidence=0.5,
        )
        for f in failures
    ]
    return {
        "fatal_failures": fatal,
        "minor_failures": [],
        "trajectory_patterns": [],
        "overall_assessment": "Review failed.",
        "usage": usage,
    }


def _fallback_heuristic(
    failures: List[MetricFailure], usage: Dict[str, int]
) -> Dict[str, Any]:
    """Conservative classification when LLM review fails.

    When the review LLM returns non-JSON or errors out we lack reliable
    signal to distinguish fatal from minor.  Default everything to minor
    so that a review infrastructure hiccup does not force trajectory_score
    to 0.  Genuine fatal failures will still surface through unsatisfied
    intent tracking.
    """
    minor: List[FailureDetail] = []

    for f in failures:
        minor.append(
            FailureDetail(
                metric=f.metric_name,
                metric_score=f.score,
                fatality_score=0.3,
                reasoning=f.reasoning,
                explanation="LLM review failed; defaulting to minor (low confidence).",
                span_index=f.span_index,
                span_id=f.span_id or "",
                span_type=f.span_type,
                entity_name=f.entity_name or "",
                observed_impact="none",
                confidence=0.3,
            )
        )

    return {
        "fatal_failures": [],
        "minor_failures": minor,
        "trajectory_patterns": [],
        "overall_assessment": "Heuristic fallback (all minor).",
        "usage": usage,
    }
