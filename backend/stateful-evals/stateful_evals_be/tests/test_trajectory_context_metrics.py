#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from typing import Any

from stateful_evals_be.evaluation.trajectory_context import (
    ClaimEntry,
    EvidenceFact,
    IntentEntry,
    TrajectoryContext,
)
from stateful_evals_be.evaluation.trajectory_context_metrics import (
    CapabilityTaskAlignmentMetric,
    ComponentConflictMetric,
    ContextPreservationMetric,
    CorrectnessMetric,
    CrossAgentTermConsistencyMetric,
    DelegationExecutionAlignmentMetric,
    EpistemicPolicySafetyMetric,
    HallucinationMetric,
    InformationPrecisionRetentionMetric,
    OrchestrationVerificationMetric,
    RoleAdherenceMetric,
    RoleAllocationCoverageMetric,
    SycophancyMetric,
    TaskCompletenessMetric,
    build_default_metrics,
    evaluate_high_level_metric_payloads,
    evaluate_high_level_metrics_batched,
    metric_input_config,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    JudgeUsage,
    build_shared_context_payload,
    resolve_batch_evidence_refs,
)


class FakeMetricJudge:
    def __init__(self, responses: Mapping[str, Mapping[str, Any]] | None = None):
        self.responses = dict(responses or {})
        self.calls: list[dict[str, Any]] = []

    def judge(
        self,
        *,
        metric_name: str,
        rubric: str,
        context_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "metric_name": metric_name,
                "rubric": rubric,
                "context_payload": context_payload,
            }
        )
        return self.responses.get(
            metric_name,
            {
                "score": 1,
                "reasoning": f"{metric_name} passes.",
                "fatal_failures": [],
                "minor_failures": [],
                "metadata": {"fake_judge": True},
            },
        )


class FakeBatchJudge:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_usage = JudgeUsage(
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
        )

    def judge_batch(
        self,
        *,
        metrics_payload: list[Mapping[str, Any]],
        shared_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "metrics_payload": metrics_payload,
                "shared_context": shared_context,
            }
        )
        return {
            "metrics": [
                {
                    "high_level_metric": item["high_level_metric"],
                    "score": 1,
                    "reasoning": "passes",
                    "fatal_failures": [],
                    "minor_failures": [],
                }
                for item in metrics_payload
            ]
        }


class BrokenBatchJudge:
    def __init__(self) -> None:
        self.last_usage = JudgeUsage()

    def judge_batch(
        self,
        *,
        metrics_payload: list[Mapping[str, Any]],
        shared_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise ValueError("truncated batch JSON")

    def judge(
        self,
        *,
        metric_name: str,
        rubric: str,
        context_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise ValueError("truncated fallback JSON")


def test_batch_attribution_resolves_ids_to_local_context_entries() -> None:
    context = _context()
    context.latest_root_answer = "The final grounded answer."
    context.latest_root_answer_span_index = 7
    shared_context = build_shared_context_payload(
        context,
        [metric_input_config()],
    )
    claim_id = shared_context["claims"][0]["artifact_id"]

    resolved = resolve_batch_evidence_refs(
        {
            "evidence_refs": [claim_id, "final_answer"],
            "fatal_failures": [{"evidence_refs": [claim_id]}],
            "minor_failures": [],
        },
        shared_context,
    )

    assert [item["artifact_id"] for item in resolved["evidence"]] == [
        claim_id,
        "final_answer",
    ]
    assert resolved["evidence"][1]["span_index"] == 7
    assert resolved["fatal_failures"][0]["evidence"][0]["content"]


def _failure(
    *,
    reasoning: str = "Rubric judged this metric as failing.",
    observed_impact: str = "metric_failure",
) -> dict[str, Any]:
    return {
        "score": 0,
        "reasoning": reasoning,
        "fatal_failures": [
            {
                "span_index": 2,
                "entity_name": "assistant",
                "reasoning": reasoning,
                "explanation": "The judge identified a context-grounded issue.",
                "observed_impact": observed_impact,
                "confidence": 0.8,
                "evidence": [
                    {
                        "span_index": 2,
                        "source_name": "assistant",
                        "kind": "claim",
                        "content": "supporting excerpt",
                    }
                ],
            }
        ],
        "minor_failures": [],
        "metadata": {"fake_judge": True},
    }


def _context() -> TrajectoryContext:
    ctx = TrajectoryContext(
        policy_text="Never bypass refund policy. Do not change orders without confirmation."
    )
    ctx.evidence.append(
        EvidenceFact(
            span_index=0,
            fact_type="user_statement",
            content="Book an affordable Celestia trip under 500 EUR with a museum.",
            source_name="user",
        )
    )
    ctx.evidence.append(
        EvidenceFact(
            span_index=1,
            fact_type="tool_output",
            content="Museum of Celestial Arts costs $18. Route LC-air costs $85.",
            source_name="trip_tool",
        )
    )
    ctx.claims.append(
        ClaimEntry(
            span_index=2,
            claim_type="assertion",
            content="The trip includes the Museum of Celestial Arts and costs $103.",
            entity_name="moderator",
        )
    )
    return ctx


def test_metric_payload_shape() -> None:
    judge = FakeMetricJudge()
    payloads = evaluate_high_level_metric_payloads(
        _context(),
        stateful_result={
            "trajectory_score": 1,
            "fatal_failures": [],
            "minor_failures": [],
        },
        metrics=build_default_metrics(judge=judge),
    )

    names = {payload["high_level_metric"] for payload in payloads}
    assert {
        "Role Adherence",
        "Epistemic Policy Safety",
        "Context Preservation",
        "Component Conflict",
        "Cross-Agent Term Consistency",
        "Information Precision Retention",
        "Capability-Task Alignment",
        "Role Allocation Coverage",
        "Delegation Execution Alignment",
        "Orchestration Verification",
        "Sycophancy",
        "Task Completeness",
        "Hallucination",
        "Correctness",
    } <= names
    assert all(payload["score"] in (0, 1) for payload in payloads)
    assert all("fatal_failures" in payload for payload in payloads)
    assert all("minor_failures" in payload for payload in payloads)
    assert len(judge.calls) == 13


def test_correctness_adapts_stateful_failures() -> None:
    result = CorrectnessMetric().evaluate(
        _context(),
        stateful_result={
            "trajectory_score": 0,
            "fatal_failures": [
                {
                    "metric": "FinalOutcomeRelevancy",
                    "span_index": 7,
                    "reasoning": "Final answer did not resolve the user request.",
                    "observed_impact": "incomplete_resolution",
                }
            ],
            "minor_failures": [{"metric": "Groundedness", "reasoning": "Minor issue."}],
        },
    )

    payload = result.to_payload()
    assert payload["high_level_metric"] == "Correctness"
    assert payload["score"] == 0
    assert payload["total_fatal"] == 1
    assert payload["total_minor"] == 1


def test_correctness_ignores_unsupported_unified_audit_placeholders() -> None:
    placeholders = [
        {
            "metric": metric,
            "span_index": 0,
            "entity_name": "final_answer",
            "reasoning": "Unified audit metric failed.",
            "explanation": "The shared final audit returned a failing verdict.",
            "observed_impact": "metric_failure",
            "confidence": 0.7,
        }
        for metric in ("Role Adherence", "Component Conflict", "Hallucination")
    ]

    result = CorrectnessMetric().evaluate(
        _context(),
        stateful_result={
            "trajectory_score": 0,
            "fatal_failures": placeholders,
            "minor_failures": [],
        },
    )

    assert result.score == 1
    assert result.fatal_failures == []
    assert result.metadata["reported_trajectory_score"] == 0
    assert result.metadata["ignored_placeholder_failure_count"] == 3


def test_minor_only_judge_result_cannot_fail_binary_metric() -> None:
    judge = FakeMetricJudge(
        {
            "Capability-Task Alignment": {
                "score": 0,
                "reasoning": "The first prompt was vague but the retry succeeded.",
                "fatal_failures": [],
                "minor_failures": [
                    {
                        "span_index": 3,
                        "entity_name": "delegate_to_telemetry",
                        "reasoning": "Missing context was supplied on retry.",
                    }
                ],
            }
        }
    )

    result = CapabilityTaskAlignmentMetric(judge=judge).evaluate(_context())

    assert result.score == 1
    assert result.fatal_failures == []
    assert len(result.minor_failures) == 1
    assert result.metadata["requested_score"] == 0
    assert result.metadata["score_was_normalized"] is True


def test_role_adherence_judges_adherence_not_policy_quality() -> None:
    judge = FakeMetricJudge()

    result = RoleAdherenceMetric(judge=judge).evaluate(_context())

    assert result.score == 1
    assert "policy is well designed" in judge.calls[0]["rubric"]
    assert "information actually present in its own input" in judge.calls[0]["rubric"]


def test_epistemic_policy_safety_allows_scoped_authority() -> None:
    context = TrajectoryContext(
        policy_text=(
            "The itinerary agent is authoritative for published fares. "
            "Cross-check conflicting values before booking."
        )
    )
    judge = FakeMetricJudge()

    result = EpistemicPolicySafetyMetric(judge=judge).evaluate(context)

    assert result.score == 1
    assert result.fatal_failures == []
    assert len(judge.calls) == 1


def test_context_preservation_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {"Context Preservation": _failure(observed_impact="lost_user_constraints")}
    )

    result = ContextPreservationMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert result.fatal_failures
    assert judge.calls[0]["metric_name"] == "Context Preservation"
    assert "user_statements" in judge.calls[0]["context_payload"]
    assert "intents" in judge.calls[0]["context_payload"]
    assert "fact_store" in judge.calls[0]["context_payload"]
    assert "final_answer" in judge.calls[0]["context_payload"]
    assert "retention and traceability, not task completion" in judge.calls[0]["rubric"]


def test_component_conflict_uses_llm_judge_rubric() -> None:
    ctx = TrajectoryContext(policy_text="")
    ctx.claims.extend(
        [
            ClaimEntry(
                span_index=1,
                claim_type="assertion",
                content="The refund for order ABC-123 is allowed and approved.",
                entity_name="policy_agent",
            ),
            ClaimEntry(
                span_index=2,
                claim_type="assertion",
                content="The refund for order ABC-123 is not allowed and denied.",
                entity_name="refund_agent",
            ),
        ]
    )
    judge = FakeMetricJudge(
        {
            "Component Conflict": _failure(
                observed_impact="unresolved_component_conflict"
            )
        }
    )

    result = ComponentConflictMetric(judge=judge).evaluate(ctx)

    assert result.score == 0
    assert result.fatal_failures[0].observed_impact == "unresolved_component_conflict"
    assert "Semantic disagreement" in judge.calls[0]["rubric"]
    assert "incompatible downstream claims" in judge.calls[0]["rubric"]
    assert "recommendation that is revised or replaced" in judge.calls[0]["rubric"]


def test_component_conflict_can_exclude_fact_store_inputs() -> None:
    ctx = TrajectoryContext(policy_text="")
    ctx.evidence.append(
        EvidenceFact(
            span_index=1,
            fact_type="tool_output",
            content="Route LC-air: from Luminos to Celestia. Departure time 11:00.",
            source_name="itinerary_agent",
        )
    )
    ctx.claims.append(
        ClaimEntry(
            span_index=2,
            claim_type="assertion",
            content="Route LC-air goes from Luminos to Celestia.",
            entity_name="moderator",
        )
    )
    judge = FakeMetricJudge()

    result = ComponentConflictMetric(
        input_config=metric_input_config("claims", max_claims=10),
        judge=judge,
    ).evaluate(ctx)

    assert result.score == 1
    assert result.metadata["input_config"]["components"] == ["claims"]
    assert "fact_store" not in judge.calls[0]["context_payload"]


def test_cross_agent_term_consistency_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {
            "Cross-Agent Term Consistency": _failure(
                reasoning="The shared term affordable drifted across agents.",
                observed_impact="cross_agent_term_drift",
            )
        }
    )

    result = CrossAgentTermConsistencyMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert result.metadata["metric_code"] == "CATCS"
    assert "same material term" in judge.calls[0]["rubric"]
    assert "explicitly labelled" in judge.calls[0]["rubric"]
    assert "five-day trip and four nights" in judge.calls[0]["rubric"]
    assert "different scopes" in judge.calls[0]["rubric"]
    assert "user_statements" in judge.calls[0]["context_payload"]


def test_information_precision_retention_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {"Information Precision Retention": _failure(observed_impact="precision_loss")}
    )

    result = InformationPrecisionRetentionMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert result.metadata["metric_code"] == "IPR"
    assert "fact_store" in judge.calls[0]["context_payload"]


def test_capability_task_alignment_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {
            "Capability-Task Alignment": _failure(
                observed_impact="capability_blind_delegation"
            )
        }
    )

    result = CapabilityTaskAlignmentMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert result.metadata["metric_code"] == "CTAS"
    assert "declared or context-inferred capabilities" in judge.calls[0]["rubric"]
    assert "capability-task alignment passes" in judge.calls[0]["rubric"]


def test_role_allocation_coverage_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {
            "Role Allocation Coverage": _failure(
                observed_impact="unowned_verification_responsibility"
            )
        }
    )

    result = RoleAllocationCoverageMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert result.metadata["metric_code"] == "role_allocation_coverage"
    assert "about assignment, not execution quality" in judge.calls[0]["rubric"]
    assert "intents" in judge.calls[0]["context_payload"]


def test_delegation_execution_alignment_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {
            "Delegation Execution Alignment": _failure(
                observed_impact="delegated_output_answered_wrong_task"
            )
        }
    )

    result = DelegationExecutionAlignmentMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert result.metadata["metric_code"] == "delegation_execution_alignment"
    assert "asked for one thing but returns" in judge.calls[0]["rubric"]
    assert "successful retry is a recovered minor issue" in judge.calls[0]["rubric"]
    assert "fact_store" in judge.calls[0]["context_payload"]


def test_orchestration_verification_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {
            "Orchestration Verification": _failure(
                observed_impact="blind_final_synthesis"
            )
        }
    )

    result = OrchestrationVerificationMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert result.metadata["metric_code"] == "orchestration_verification"
    assert "does not present estimates" in judge.calls[0]["rubric"]
    assert "does not fulfill the request" in judge.calls[0]["rubric"]
    assert "explicit verifier approval" in judge.calls[0]["rubric"]
    assert "final_answer" in judge.calls[0]["context_payload"]


def test_sycophancy_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {"Sycophancy": _failure(observed_impact="unjustified_user_agreement")}
    )

    result = SycophancyMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert "policy" in judge.calls[0]["context_payload"]
    assert "user_statements" in judge.calls[0]["context_payload"]


def test_task_completeness_uses_llm_judge_rubric() -> None:
    ctx = _context()
    ctx.intents.append(
        IntentEntry(
            name="user_trip_request",
            source="user",
            first_seen=0,
            last_seen=3,
            status="dropped",
            events=[{"span_index": 3, "type": "user_message"}],
        )
    )
    judge = FakeMetricJudge(
        {"Task Completeness": _failure(observed_impact="incomplete_resolution")}
    )

    result = TaskCompletenessMetric(judge=judge).evaluate(ctx)

    assert result.score == 0
    assert result.metadata["judge_type"] == "deterministic_unresolved_intent_precheck"
    assert judge.calls == []


def test_batched_metrics_share_artifacts_and_count_usage_once() -> None:
    judge = FakeBatchJudge()
    metrics = build_default_metrics(judge=judge)

    results = evaluate_high_level_metrics_batched(
        _context(),
        stateful_result={
            "trajectory_score": 1,
            "fatal_failures": [],
            "minor_failures": [],
        },
        metrics=metrics,
        judge=judge,
    )

    assert len(judge.calls) == 1
    call = judge.calls[0]
    assert "policy" in call["shared_context"]
    assert all("context" not in item for item in call["metrics_payload"])
    usage = [result.metadata.get("usage", {}) for result in results]
    assert sum(int(item.get("total_tokens", 0)) for item in usage) == 120
    assert (
        sum(
            item.metadata.get("usage_scope") == "shared_batch_total" for item in results
        )
        == 1
    )


def test_batched_metric_parse_failures_are_invalid_not_behavioral_failures() -> None:
    judge = BrokenBatchJudge()

    results = evaluate_high_level_metrics_batched(
        _context(),
        stateful_result={
            "trajectory_score": 1,
            "fatal_failures": [],
            "minor_failures": [],
        },
        metrics=build_default_metrics(judge=judge),
        judge=judge,
    )

    invalid = [
        result
        for result in results
        if result.metadata.get("evaluation_invalid") is True
    ]
    assert len(invalid) == 13
    assert all(result.score is None for result in invalid)
    assert all(result.to_payload()["status"] == "unknown" for result in invalid)
    assert all(result.fatal_failures == [] for result in invalid)


def test_batched_correctness_does_not_duplicate_recomputed_metric_failure() -> None:
    judge = FakeBatchJudge()

    results = evaluate_high_level_metrics_batched(
        _context(),
        stateful_result={
            "trajectory_score": 0,
            "fatal_failures": [
                {
                    "metric": "Hallucination",
                    "span_index": 2,
                    "entity_name": "assistant",
                    "reasoning": "A stale hallucination finding.",
                    "observed_impact": "metric_failure",
                    "confidence": 0.8,
                }
            ],
            "minor_failures": [],
        },
        metrics=build_default_metrics(judge=judge),
        judge=judge,
    )

    correctness = next(
        result for result in results if result.high_level_metric == "Correctness"
    )
    assert correctness.score == 1
    assert correctness.fatal_failures == []


def test_hallucination_uses_llm_judge_rubric() -> None:
    judge = FakeMetricJudge(
        {"Hallucination": _failure(observed_impact="unsupported_specific_claim")}
    )

    result = HallucinationMetric(judge=judge).evaluate(_context())

    assert result.score == 0
    assert "fact_store" in judge.calls[0]["context_payload"]
    assert "high-confidence evidence" in judge.calls[0]["rubric"]
    assert "absence of a particular symptom" in judge.calls[0]["rubric"]
    assert "forward-looking actions" in judge.calls[0]["rubric"]
    assert "next update in 15 minutes" in judge.calls[0]["rubric"]
    assert "even a minor hallucination finding" in judge.calls[0]["rubric"]


def test_hallucination_reuses_conclusive_grounding_failure_without_llm() -> None:
    judge = FakeMetricJudge()

    result = HallucinationMetric(judge=judge).evaluate(
        _context(),
        stateful_result={
            "fatal_failures": [
                {
                    "metric": "Groundedness",
                    "span_index": 2,
                    "entity_name": "final_answer",
                    "reasoning": "The stated $999 price contradicts tool evidence.",
                    "observed_impact": "contradicted_material_value",
                    "confidence": 0.95,
                }
            ]
        },
    )

    assert result.score == 0
    assert result.metadata["judge_type"] == "deterministic_grounding_failure_precheck"
    assert judge.calls == []
