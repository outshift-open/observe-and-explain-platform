# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""Ordered spans, parallel primitive judges, then parallel final metrics."""

import logging
import time
from copy import deepcopy
from functools import partial

from stateful_evals_be.evaluation.coordination import COORDINATION_CONTEXT_ATTRIBUTE
from stateful_evals_be.evaluation.cost_estimator import estimate_token_cost
from stateful_evals_be.evaluation.llm_state import LLMState
from stateful_evals_be.evaluation.span_judge import SpanJudgeError, SpanJudge
from stateful_evals_be.evaluation.trajectory_context import _timestamp_ns
from stateful_evals_be.models.requests import (
    IntentState,
    MetricFailure,
    SessionResult,
    SpanMetricResult,
    TokenUsage,
)

logger = logging.getLogger(__name__)


def _completion_order(spans):
    """Order completed observations using only the public OTel envelope.

    An enclosing span's output must not become prior evidence before its
    children finish. Without complete timing, preserve caller order explicitly.
    """
    completion = []
    starts = []
    for span in spans:
        start = _timestamp_ns(span.get("Timestamp"))
        duration = span.get("Duration")
        if start is None or not isinstance(duration, (int, float)) or duration < 0:
            return spans
        completion.append(start + int(duration))
        starts.append(start)
    parents = {
        span.get("SpanId"): span.get("ParentSpanId")
        for span in spans
        if span.get("SpanId")
    }

    def depth(index):
        seen = set()
        parent = spans[index].get("ParentSpanId")
        while parent and parent not in seen:
            seen.add(parent)
            parent = parents.get(parent)
        return len(seen)

    # Equal end times still expose children before enclosing wrapper outputs.
    return [
        spans[i]
        for i in sorted(
            range(len(spans)), key=lambda i: (completion[i], -depth(i), -starts[i])
        )
    ]


async def evaluate_llm_spans(processor, spans, *, session_id, policy_override=None):
    started = time.monotonic()
    raw_spans = _completion_order(deepcopy([dict(span) for span in spans]))
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    final_usage = dict(usage)
    results, failures, intents, fatal, minor, patterns, high_metrics = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    trajectory_metrics, metric_set, score, error = [], None, None, None
    calls = evaluated = unsatisfied = 0
    options = processor.options

    def add_usage(target, value):
        for key in target:
            target[key] += int(value.get(key, 0) or 0)

    try:
        if not raw_spans:
            raise ValueError("No spans found for session")
        if options.sampling and options.sampling.strategy != "none":
            raise ValueError("LLM state requires every span; disable sampling")
        if options.use_fatal_mode and not options.use_unified_final_audit:
            raise ValueError("LLM state requires the final metric audit in fatal mode")
        # Whole-trajectory evaluator sidecars are not current-span observations.
        for span in raw_spans:
            if isinstance(span.get("SpanAttributes"), dict):
                span["SpanAttributes"].pop(COORDINATION_CONTEXT_ATTRIBUTE, None)
        if policy_override and policy_override.strip():
            raw_spans[0]["evaluation_policy_override"] = policy_override.strip()
        state = LLMState(raw_spans)
        processor.last_trajectory_context = state.context
        judge = SpanJudge(
            query=partial(processor._aquery_with_budget, span_processing=True),
            options=options,
            metric_names=processor.metric_names,
        )
        for index, span in enumerate(raw_spans):
            verdict = await judge.aevaluate_and_update(
                state, span_index=index, raw_span=span
            )
            calls += verdict["calls"]
            add_usage(usage, verdict["usage"])
            evaluated += 1
            operation = state.context.raw_spans[-1]
            for metric_index, metric in enumerate(verdict["metrics"]):
                result = SpanMetricResult(
                    span_index=index,
                    span_id=str(span.get("SpanId", "")),
                    trace_id=str(span.get("TraceId", "")),
                    span_type=operation["operation_type"],
                    entity_name=operation["entity_name"],
                    metric_name=metric["metric_name"],
                    score=metric["score"],
                    reasoning=metric["reasoning"],
                    **processor._metric_usage_share(
                        verdict["usage"],
                        metric_index,
                        len(verdict["metrics"]),
                        processor.llm_config.LLM_MODEL_NAME,
                    ),
                )
                results.append(result)
                if result.score == 0:
                    failures.append(
                        MetricFailure(
                            metric_name=result.metric_name,
                            score=0,
                            reasoning=result.reasoning,
                            span_index=index,
                            span_type=result.span_type,
                            entity_name=result.entity_name,
                            span_id=result.span_id,
                            input_payload=operation.get("input_payload"),
                            output_payload=operation.get("content", ""),
                            eval_context="span_state",
                        )
                    )
        context = state.context
        intents = [
            IntentState(
                name=item.name,
                state=item.status,
                first_span=item.first_seen,
                last_span=item.last_seen,
                occurrences=len(item.events),
                final_score=float(item.status in {"fulfilled", "completed"}),
            )
            for item in context.intents
        ]
        unsatisfied = sum(
            item.status not in {"fulfilled", "completed", "superseded"}
            for item in context.intents
        )
        final_args = dict(
            traj_ctx=context,
            failures=failures,
            intent_states=intents,
            unsatisfied_intents=unsatisfied,
            raw_spans=raw_spans,
            session_id=session_id,
        )
        if options.use_fatal_mode:
            (
                fatal,
                minor,
                patterns,
                high_metrics,
                final_tokens,
            ) = await processor._arun_unified_final_audit(**final_args)
            add_usage(final_usage, final_tokens)
            if any(
                item.observed_impact == "llm_judge_error" for item in fatal + minor
            ) or any(
                (item.get("metadata") or {}).get("evaluation_invalid")
                for item in high_metrics
            ):
                raise RuntimeError(
                    "A final metric judge failed; evaluation is incomplete"
                )
            score = int(not any(item.affects_trajectory_score for item in fatal))
            if options.high_level_metric_suite == "legacy_v1":
                from stateful_evals_be.evaluation.trajectory_context_metrics import (
                    CorrectnessMetric,
                )

                high_metrics.append(
                    CorrectnessMetric()
                    .evaluate(
                        context,
                        stateful_result={
                            "trajectory_score": score,
                            "fatal_failures": fatal,
                            "minor_failures": minor,
                        },
                    )
                    .to_payload()
                )
        if options.trajectory_metrics:
            from stateful_evals_be.evaluation.trajectory_context_metrics import (
                TRAJECTORY_METRIC_SET,
            )

            (
                trajectory_metrics,
                tokens,
            ) = await processor._arun_configured_trajectory_metrics(
                **final_args,
                fatal_failures=fatal,
                minor_failures=minor,
                trajectory_score=score,
                trajectory_reasoning=processor._build_trajectory_reasoning(
                    fatal, minor, score
                ),
            )
            add_usage(final_usage, tokens)
            if any(
                (item.get("metadata") or {}).get("evaluation_invalid")
                for item in trajectory_metrics
            ):
                raise RuntimeError(
                    "A configured metric judge failed; evaluation is incomplete"
                )
            metric_set = TRAJECTORY_METRIC_SET
    except Exception as exc:
        if isinstance(exc, SpanJudgeError):
            calls += exc.calls
            add_usage(usage, exc.usage)
        error, score = str(exc), None
        logger.exception("[%s] Evaluation failed", session_id)
    tokens = TokenUsage(
        **{
            **{key: usage[key] + final_usage[key] for key in usage},
            **{f"mce_{key}": value for key, value in usage.items()},
            **{f"high_level_{key}": value for key, value in final_usage.items()},
        }
    )
    current_score = sum(item.score for item in results) / max(
        1, len(processor.metric_names)
    )
    return SessionResult(
        session_id=session_id,
        app_name=str(raw_spans[0].get("ServiceName", "")) if raw_spans else "",
        trajectory_score=score,
        trajectory_reasoning=processor._build_trajectory_reasoning(fatal, minor, score),
        error=error,
        unsatisfied_intents=unsatisfied,
        intent_states=intents,
        total_spans=len(raw_spans),
        mce_spans_evaluated=evaluated,
        mce_calls=calls,
        current_score=current_score,
        avg_score=current_score / max(1, len(raw_spans)),
        use_fatal_mode=options.use_fatal_mode,
        total_failures=len(failures),
        fatal_failures=fatal,
        minor_failures=minor,
        span_metric_results=results,
        trajectory_patterns=patterns,
        high_level_metric_suite=options.high_level_metric_suite,
        high_level_metrics=high_metrics,
        trajectory_metrics=trajectory_metrics,
        trajectory_metric_set=metric_set,
        token_usage=tokens,
        cost_estimate=estimate_token_cost(tokens, processor.llm_config.LLM_MODEL_NAME),
        eval_duration_seconds=round(time.monotonic() - started, 3),
    )
