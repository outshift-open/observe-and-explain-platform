#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Request and response models for the Stateful Evals service.

Mirrors the MCE request model pattern: credentials + data fetching + metric options.
Reuses MCE's LLMJudgeConfig and DataFetchingConfig directly.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from metrics_computation_engine.models.requests import (
    LLMJudgeConfig,
    DataFetchingConfig,
)


# ============================================================================
# Request Models
# ============================================================================


class SamplingConfig(BaseModel):
    """Adaptive span sampling for trajectory evaluation.

    Implements tail-weighted bucket sampling: spans near the end of a trajectory
    carry more diagnostic signal (errors cascade forward), so they are evaluated
    at a higher rate than early spans.

    Anchor spans are always evaluated regardless of zone rate:
    - First and last evaluable span (controlled by always_eval_first/last)
    - Spans adjacent to any error-flagged span
    - LLM spans that immediately follow a large tool output
    """

    strategy: Literal["none", "tail_weighted"] = Field(
        default="none",
        description=(
            "'none' evaluates every span (current behaviour). "
            "'tail_weighted' applies bucket sampling with dense evaluation at the tail."
        ),
    )
    early_rate: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Fraction of evaluable spans to assess in the early zone (positions 0–40%).",
    )
    mid_rate: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Fraction of evaluable spans to assess in the mid zone (positions 40–70%).",
    )
    always_eval_first: bool = Field(
        default=True,
        description="Anchor: always evaluate the first evaluable span.",
    )
    always_eval_last: bool = Field(
        default=True,
        description="Anchor: always evaluate the last evaluable span.",
    )
    large_tool_output_chars: int = Field(
        default=2000,
        description=(
            "If a tool span's output payload exceeds this character count, "
            "anchor the next LLM span (evidence base changed significantly)."
        ),
    )


class TemporalMetricOptions(BaseModel):
    """Configuration options for temporal metric computation."""

    span_context_mode: Literal["focused", "legacy"] = Field(
        default="focused",
        description="Select task-linked span context, or the previous recency-based view.",
    )
    span_context_max_chars: int = Field(
        default=14000,
        ge=2000,
        description=(
            "Soft character budget for retrieved span context. Direct evidence and "
            "active instructions are retained in full even when they exceed it."
        ),
    )

    high_level_metric_suite: Literal[
        "legacy_v1",
        "paper_v1",
        "paper_v2",
    ] = Field(
        default="legacy_v1",
        description=(
            "Trajectory-context metric definitions used by the unified final audit. "
            "legacy_v1 preserves the existing suite; paper_v1 selects the revised "
            "13-metric suite; paper_v2 selects its targeted metric refresh."
        ),
    )
    trajectory_metrics: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional trajectory-level metrics evaluated over the accumulated "
            "state. Configure stable metric codes or ['all']. These results are "
            "diagnostic and never change trajectory_score or trajectory_reasoning."
        ),
    )
    use_fatal_mode: bool = Field(
        default=True,
        description="Use trajectory-level fatal/minor audit and binary scoring.",
    )
    fatality_threshold: float = Field(
        default=0.69,
        ge=0.0,
        le=1.0,
        description="Severity threshold (0.0-1.0). Scores >= this are FATAL.",
    )
    batch_size: int = Field(
        default=50,
        description="Batch size for parallel session processing",
    )
    max_messages: Optional[int] = Field(
        default=2,
        ge=1,
        description=(
            "Max non-system messages retained in the compact current-span delta. "
            "The accumulated conversation is never sent to the span judge."
        ),
    )
    span_judge_max_tokens: int = Field(
        default=1200,
        ge=256,
        le=8192,
        description="Maximum output tokens for the combined three-primitive span judge.",
    )
    span_judge_max_attempts: int = Field(
        default=3,
        ge=1,
        le=5,
        description=(
            "Maximum attempts when a combined span judge returns invalid JSON "
            "or omits requested primitive metrics."
        ),
    )
    final_judge_max_tokens: int = Field(
        default=4096,
        ge=512,
        le=16384,
        description="Maximum output tokens for the shared final metric audit.",
    )
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = Field(
        default="low",
        description="Reasoning effort for final audits and trajectory metric judges.",
    )
    span_reasoning_effort: Optional[Literal["none", "low", "medium", "high"]] = Field(
        default="none",
        description=(
            "Reasoning effort for span judgments only. 'none' requests disabled "
            "thinking where supported; null omits the setting and uses the provider "
            "default. Does not change final-audit or trajectory-metric reasoning."
        ),
    )
    use_unified_final_audit: bool = Field(
        default=True,
        description=(
            "Replace inter-step, cross-span, and final-outcome LLM reviews with "
            "one shared trajectory-context metric audit."
        ),
    )
    write_to_db: Optional[bool] = Field(
        default=False,
        description="Whether to write results back to the DB",
    )
    sampling: Optional[SamplingConfig] = Field(
        default=None,
        description=(
            "Adaptive span sampling configuration. "
            "None or strategy='none' disables sampling (default behaviour)."
        ),
    )

    @field_validator("trajectory_metrics")
    @classmethod
    def validate_trajectory_metrics(
        cls,
        value: Optional[List[str]],
    ) -> Optional[List[str]]:
        if value is None:
            return None
        from stateful_evals_be.evaluation.trajectory_context_metrics.trajectory_metrics import (
            resolve_trajectory_metric_codes,
        )

        return list(resolve_trajectory_metric_codes(value))


class TemporalEvalRequest(BaseModel):
    """Main request model for temporal evaluation.

    Three core metrics:
    - Groundedness: factual claims trace to evidence
    - IntentRecognition: requirements identified, tracked, and addressed
    - Relevancy: no contradictions, valid reasoning
    """

    metrics: List[str] = Field(
        default=[
            "mdt.Groundedness",
            "mdt.IntentRecognition",
            "mdt.Relevancy",
        ],
        description="List of metric names to compute.",
    )
    llm_judge_config: LLMJudgeConfig = LLMJudgeConfig()
    data_fetching_infos: DataFetchingConfig = DataFetchingConfig()
    metric_options: Optional[TemporalMetricOptions] = None

    def validate(self) -> bool:
        if not self.data_fetching_infos.validate():
            return False
        return True

    def is_batch_request(self) -> bool:
        return self.data_fetching_infos.is_batch()

    def get_batch_config(self):
        return self.data_fetching_infos.get_batch_config()

    def get_session_ids(self) -> List[str]:
        return self.data_fetching_infos.get_session_ids()

    def get_metric_options(self) -> TemporalMetricOptions:
        if self.metric_options is None:
            return TemporalMetricOptions()
        return self.metric_options


# ============================================================================
# Response Models
# ============================================================================


class FailureDetail(BaseModel):
    """Details of a single metric failure after inter-step review."""

    metric: str
    metric_score: float
    fatality_score: float
    reasoning: str
    explanation: str
    span_index: int = 0
    span_id: str = ""
    span_type: str = ""
    entity_name: str = ""
    observed_impact: str = "none"
    confidence: float = 0.5
    self_corrected: bool = False
    affects_trajectory_score: bool = True
    policy_compliant: bool = False
    hard_rule_violation: bool = False
    prompt_params: Optional[Dict[str, Any]] = None


class TokenUsage(BaseModel):
    """Aggregated token usage for LLM calls during evaluation."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    mce_prompt_tokens: int = 0
    mce_completion_tokens: int = 0
    mce_total_tokens: int = 0
    review_prompt_tokens: int = 0
    review_completion_tokens: int = 0
    review_total_tokens: int = 0
    cross_span_prompt_tokens: int = 0
    cross_span_completion_tokens: int = 0
    cross_span_total_tokens: int = 0
    final_outcome_prompt_tokens: int = 0
    final_outcome_completion_tokens: int = 0
    final_outcome_total_tokens: int = 0
    high_level_prompt_tokens: int = 0
    high_level_completion_tokens: int = 0
    high_level_total_tokens: int = 0


class TokenCostEstimate(BaseModel):
    """Approximate USD cost derived from token usage and model pricing."""

    model_name: str = ""
    pricing_model_name: str = ""
    pricing_source: str = "unavailable"
    input_cost_per_1m_tokens: Optional[float] = None
    output_cost_per_1m_tokens: Optional[float] = None
    prompt_cost_usd: float = 0.0
    completion_cost_usd: float = 0.0
    estimated_cost_usd: float = 0.0
    currency: str = "USD"
    is_estimate: bool = True
    by_phase: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class IntentEvent(BaseModel):
    """Single span-level observation of intent recognition."""

    span_index: int
    span_type: str  # tool | llm
    entity_name: str
    score: float
    reasoning: str = ""


class IntentState(BaseModel):
    """Resolved status of a single tracked intent across the trajectory."""

    name: str
    # fulfilled | failed | drifting | dormant. Older saved results may hold a
    # policy-rejection state that is no longer produced.
    state: str
    first_span: int = 0
    last_span: int = 0
    occurrences: int = 0
    final_score: float = 0.0
    timeline: List[IntentEvent] = Field(default_factory=list)


class SpanMetricResult(BaseModel):
    """Individual metric result for a single span."""

    span_index: int
    span_id: str = ""
    trace_id: str = ""
    span_type: str = ""
    entity_name: str = ""
    metric_name: str
    score: float
    reasoning: str = ""


class SessionResult(BaseModel):
    """Result for a single session evaluation."""

    session_id: str
    app_name: str = ""
    trajectory_score: Optional[int] = None
    trajectory_reasoning: Optional[str] = None
    unsatisfied_intents: int = 0
    intent_states: List[IntentState] = Field(default_factory=list)
    total_spans: int = 0
    mce_spans_evaluated: int = 0
    mce_calls: int = 0
    spans_sampled_out: int = 0
    current_score: float = 0.0
    avg_score: float = 0.0
    use_fatal_mode: bool = True
    total_failures: int = 0
    fatal_failures: List[FailureDetail] = Field(default_factory=list)
    minor_failures: List[FailureDetail] = Field(default_factory=list)
    span_metric_results: List[SpanMetricResult] = Field(default_factory=list)
    trajectory_patterns: List[str] = Field(default_factory=list)
    high_level_metric_suite: str = "legacy_v1"
    high_level_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    trajectory_metric_set: Optional[str] = None
    trajectory_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_estimate: TokenCostEstimate = Field(default_factory=TokenCostEstimate)
    eval_duration_seconds: Optional[float] = None
    error: Optional[str] = None


class EvalSummary(BaseModel):
    """Summary of a temporal evaluation run."""

    scoring_mode: str
    fatality_threshold: float = 0.69
    total_sessions: int = 0
    total_spans_processed: int = 0
    total_fatal_failures: int = 0
    total_minor_failures: int = 0
    total_token_usage: TokenUsage = Field(default_factory=TokenUsage)
    total_cost_estimate: TokenCostEstimate = Field(default_factory=TokenCostEstimate)
    results: List[SessionResult] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# Internal Dataclasses (used within evaluation logic)
# ============================================================================


@dataclass
class MetricFailure:
    """Represents a metric that scored less than 1."""

    metric_name: str
    score: float
    reasoning: str
    span_index: int
    span_type: str
    input_payload: Any
    output_payload: Any
    eval_context: Optional[str] = None
    entity_name: Optional[str] = None
    span_id: Optional[str] = None
    policy: Optional[str] = None
