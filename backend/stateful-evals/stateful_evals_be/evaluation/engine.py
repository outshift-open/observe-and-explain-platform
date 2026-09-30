#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Reusable evaluation engine with independent state for every trajectory."""

import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock

from metrics_computation_engine.models.requests import LLMJudgeConfig

from stateful_evals_be.evaluation.cost_estimator import estimate_token_cost
from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
from stateful_evals_be.models.requests import (
    EvalSummary,
    SessionResult,
    TemporalMetricOptions,
    TokenUsage,
)
from stateful_evals_be.models.spans import SpanInput

SpanLoader = Callable[[str], Iterable[SpanInput]]


class EvaluationEngine:
    """Evaluate trajectories without owning storage or changing caller inputs.

    Configuration is copied at construction; each evaluation creates a fresh
    processor, context, judge client and usage ledger. An engine can be reused
    across sequential or concurrent calls. Model calls can incur costs.
    """

    def __init__(
        self,
        *,
        llm_config: LLMJudgeConfig,
        options: TemporalMetricOptions | None = None,
    ) -> None:
        self._llm_config = deepcopy(llm_config)
        self._options = (
            deepcopy(options) if options is not None else TemporalMetricOptions()
        )

    def evaluate_spans(
        self,
        spans: Iterable[SpanInput],
        *,
        session_id: str,
        policy_override: str | None = None,
    ) -> SessionResult:
        """Evaluate one trajectory; return the existing SessionResult schema."""
        with TemporalMetricsProcessor(
            llm_config=deepcopy(self._llm_config), options=deepcopy(self._options)
        ) as processor:
            return processor.evaluate_spans(
                spans, session_id=session_id, policy_override=policy_override
            )

    def evaluate_sessions(
        self,
        session_ids: Iterable[str],
        *,
        span_loader: SpanLoader,
        policy_overrides: dict[str, str] | None = None,
    ) -> EvalSummary:
        """Load completed sessions and evaluate them with bounded concurrency.

        The loader remains caller-owned and is called serially within this batch,
        so a database client need not support concurrent reads. Evaluation runs
        concurrently. Results and errors retain their respective input order.
        """
        policies = dict(policy_overrides or {})
        loader_lock = Lock()

        def evaluate_one(session_id: str) -> SessionResult:
            started = time.monotonic()
            try:
                with loader_lock:
                    spans = deepcopy([dict(span) for span in span_loader(session_id)])
                result = self.evaluate_spans(
                    spans,
                    session_id=session_id,
                    policy_override=policies.get(session_id),
                )
            except Exception as exc:
                result = SessionResult(session_id=session_id, error=str(exc))
            result.eval_duration_seconds = round(time.monotonic() - started, 3)
            return result

        successful_results: list[SessionResult] = []
        errors: list[dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=self._options.batch_size) as executor:
            for result in executor.map(evaluate_one, session_ids):
                if result.error:
                    errors.append(
                        {"session_id": result.session_id, "error": result.error}
                    )
                else:
                    successful_results.append(result)
        return self._summarize_results(successful_results, errors)

    def _summarize_results(
        self,
        successful_results: list[SessionResult],
        errors: list[dict[str, str]],
    ) -> EvalSummary:
        total_fatal = sum(len(r.fatal_failures) for r in successful_results)
        total_minor = sum(len(r.minor_failures) for r in successful_results)
        total_spans = sum(r.total_spans for r in successful_results)

        agg_tokens = TokenUsage()
        for r in successful_results:
            tu = r.token_usage
            agg_tokens.prompt_tokens += tu.prompt_tokens
            agg_tokens.completion_tokens += tu.completion_tokens
            agg_tokens.total_tokens += tu.total_tokens
            agg_tokens.mce_prompt_tokens += tu.mce_prompt_tokens
            agg_tokens.mce_completion_tokens += tu.mce_completion_tokens
            agg_tokens.mce_total_tokens += tu.mce_total_tokens
            agg_tokens.review_prompt_tokens += tu.review_prompt_tokens
            agg_tokens.review_completion_tokens += tu.review_completion_tokens
            agg_tokens.review_total_tokens += tu.review_total_tokens
            agg_tokens.cross_span_prompt_tokens += tu.cross_span_prompt_tokens
            agg_tokens.cross_span_completion_tokens += tu.cross_span_completion_tokens
            agg_tokens.cross_span_total_tokens += tu.cross_span_total_tokens
            agg_tokens.final_outcome_prompt_tokens += tu.final_outcome_prompt_tokens
            agg_tokens.final_outcome_completion_tokens += (
                tu.final_outcome_completion_tokens
            )
            agg_tokens.final_outcome_total_tokens += tu.final_outcome_total_tokens
            agg_tokens.high_level_prompt_tokens += tu.high_level_prompt_tokens
            agg_tokens.high_level_completion_tokens += tu.high_level_completion_tokens
            agg_tokens.high_level_total_tokens += tu.high_level_total_tokens

        scoring_mode = (
            (
                "Unified Trajectory Audit"
                if self._options.use_unified_final_audit
                else "Inter-Step Review"
            )
            if self._options.use_fatal_mode
            else "Average Score"
        )
        total_cost_estimate = estimate_token_cost(
            agg_tokens,
            self._llm_config.LLM_MODEL_NAME,
        )

        return EvalSummary(
            scoring_mode=scoring_mode,
            fatality_threshold=self._options.fatality_threshold,
            total_sessions=len(successful_results),
            total_spans_processed=total_spans,
            total_fatal_failures=total_fatal,
            total_minor_failures=total_minor,
            total_token_usage=agg_tokens,
            total_cost_estimate=total_cost_estimate,
            results=successful_results,
            errors=errors,
        )
