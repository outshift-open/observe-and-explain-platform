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
import os
import re
from typing import Any, Dict, List

import litellm
from metrics_computation_engine.llm_judge.llm import LLMClient

from stateful_evals_be.evaluation.span_judge import SpanJudge
from stateful_evals_be.models.requests import FailureDetail, MetricFailure
from stateful_evals_be.prompts.inter_step_review import (
    INTER_STEP_REVIEW_SYSTEM_PROMPT,
    INTER_STEP_REVIEW_USER_PROMPT,
)

litellm.drop_params = True

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
    *,
    max_tokens: int = 4096,
    reasoning_effort: str | None = "low",
) -> Dict[str, Any]:
    """Review every span-level failure in bounded batches.

    An unavailable or incomplete judgment raises rather than inventing a
    severity. The processor reports that session as unscored.

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

    model_name = os.getenv("LLM_MODEL_NAME", "")
    temperature = 1.0 if "claude-sonnet" in model_name.casefold() else 0.0
    query_options = {"temperature": temperature, "max_tokens": max_tokens}
    if reasoning_effort is not None:
        query_options["reasoning_effort"] = reasoning_effort
    combined = {
        "fatal_failures": [],
        "minor_failures": [],
        "trajectory_patterns": [],
        "overall_assessment": "",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    assessments = []
    for start in range(0, len(failures), _MAX_FAILURES_PER_BATCH):
        review_failures = failures[start : start + _MAX_FAILURES_PER_BATCH]
        user_prompt = INTER_STEP_REVIEW_USER_PROMPT.format(
            policy=policy[:3000] if policy else "No policy provided.",
            trajectory_summary=trajectory_summary[:4000],
            failures=_format_failures_for_review(review_failures),
            aftermath=aftermath or "End of trajectory.",
        )
        messages = [
            {"role": "system", "content": INTER_STEP_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = llm_client.query(messages, **query_options)
            choice = response.choices[0]
            if getattr(choice, "finish_reason", None) in {"length", "max_tokens"}:
                raise ValueError("judge response exceeded its token budget")
            result_text = (choice.message.content or "").strip()
            if not result_text:
                raise ValueError("judge returned an empty response")
            if result_text.startswith("{{"):
                result_text = result_text.replace("{{", "{").replace("}}", "}")
            parsed = SpanJudge.parse_response(result_text)
            usage = getattr(response, "usage", None)
            usage_tokens = {
                key: getattr(usage, key, 0) or 0 for key in combined["usage"]
            }
            reviewed = _build_review_result(review_failures, parsed, usage_tokens)
        except Exception as exc:
            batch_number = start // _MAX_FAILURES_PER_BATCH + 1
            raise RuntimeError(
                f"Inter-step review failed in batch {batch_number}: {exc}"
            ) from exc

        combined["fatal_failures"].extend(reviewed["fatal_failures"])
        combined["minor_failures"].extend(reviewed["minor_failures"])
        for pattern in reviewed["trajectory_patterns"]:
            if pattern not in combined["trajectory_patterns"]:
                combined["trajectory_patterns"].append(pattern)
        for key, value in reviewed["usage"].items():
            combined["usage"][key] += value
        if reviewed["overall_assessment"]:
            assessments.append(reviewed["overall_assessment"])
    combined["overall_assessment"] = "\n".join(assessments)
    return combined


def _build_review_result(
    failures: List[MetricFailure],
    parsed: Dict[str, Any],
    usage: Dict[str, int],
) -> Dict[str, Any]:
    """Convert a complete review without silently dropping unmatched findings."""
    fatal_failures: List[FailureDetail] = []
    minor_failures: List[FailureDetail] = []

    items = parsed.get("failures")
    if not isinstance(items, list):
        raise ValueError("judge must return a 'failures' array")
    patterns = parsed.get("trajectory_patterns", [])
    if not isinstance(patterns, list) or any(not isinstance(p, str) for p in patterns):
        raise ValueError("judge 'trajectory_patterns' must be an array of strings")
    reviewed_indices = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("judge failure entries must be objects")
        span_idx = int(item.get("span_index", -1))
        metric = str(item.get("metric", "")).strip().rsplit(".", 1)[-1].casefold()
        verdict = str(item.get("verdict", "")).strip().upper()
        if verdict not in {"FATAL", "MINOR"}:
            raise ValueError("judge failure verdict must be FATAL or MINOR")
        severity = float(item.get("severity", 0.5))
        severity = max(0.0, min(1.0, severity))
        explanation = str(item.get("explanation", ""))
        pattern = item.get("pattern", "none")
        self_corrected = bool(item.get("self_corrected", False))
        policy_compliant = bool(item.get("policy_compliant", False))
        is_hard_rule = bool(item.get("hard_rule_violation", False))

        candidates = [
            i
            for i, failure in enumerate(failures)
            if i not in reviewed_indices and failure.span_index == span_idx
        ]
        matching = [
            i
            for i in candidates
            if failures[i].metric_name.rsplit(".", 1)[-1].casefold() == metric
        ]
        if matching:
            matched_index = matching[0]
        elif (
            len(candidates) == 1
            and sum(failure.span_index == span_idx for failure in failures) == 1
        ):
            # Preserve the old span-only fallback when it is unambiguous.
            matched_index = candidates[0]
        else:
            raise ValueError(
                f"judge finding does not identify an unreviewed failure at span {span_idx}"
            )
        reviewed_indices.add(matched_index)
        matching_failure = failures[matched_index]

        # Metadata alone must not turn the judge's explicit MINOR into FATAL.
        if is_hard_rule and verdict == "FATAL":
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

    if len(reviewed_indices) != len(failures):
        raise ValueError(
            f"judge reviewed {len(reviewed_indices)} of {len(failures)} requested failures"
        )

    return {
        "fatal_failures": fatal_failures,
        "minor_failures": minor_failures,
        "trajectory_patterns": patterns,
        "overall_assessment": str(parsed.get("overall_assessment", "")),
        "usage": usage,
    }
