#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from stateful_evals_be.evaluation.trajectory_context import (
    AgentProfile,
    ClaimEntry,
    EvidenceFact,
    IntentEntry,
    TrajectoryContext,
    WorkUnit,
)
from stateful_evals_be.evaluation.trajectory_context_metrics import (
    PAPER_OUTCOME_METRICS,
    SUPPORTED_METRIC_SUITES,
    build_metric_suite,
    evaluate_metric_suite_batched,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.base import (
    HighLevelMetricResult,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    JudgeUsage,
    build_context_payload,
    build_delegation_context,
    build_instruction_execution_context,
    build_instruction_following_context,
    build_operation_context,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.trajectory_metrics import (
    UPDATED_METRIC_NAMES,
    CommunicationEfficiencyMetric,
    DelegationAccuracyMetric as DelegationAccuracyMetricV2,
    DelegationAccuracyMetricV1 as DelegationAccuracyMetric,
    GoalAlignmentMetric as GoalAlignmentMetricV2,
    GroundednessMetric,
    HandoffQualityMetric as HandoffQualityMetricV2,
    InstructionFollowingMetric,
)
from stateful_evals_be.models.requests import TemporalMetricOptions


PAPER_METRIC_NAMES = (
    "Policy Safety",
    "Delegation Accuracy",
    "Goal Alignment",
    "Instruction Following",
    "Handoff Quality",
    "Semantic Consistency",
    "Context Preservation",
    "Confidence Calibration",
    "Verification Quality",
    "Coordination Efficiency",
    "Groundedness",
    "Task Completion",
    "Constraint Satisfaction",
)

PAPER_V2_METRIC_NAMES = (
    "Policy Safety",
    "Delegation Accuracy",
    "Goal Alignment",
    "Instruction Following",
    "Handoff Quality",
    "Semantic Consistency",
    "Context Preservation",
    "Confidence Calibration",
    "Verification Quality",
    "Communication Efficiency",
    "Groundedness",
    "Task Completion",
    "Constraint Satisfaction",
)


class PassingBatchJudge:
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
        metrics_payload: Sequence[Mapping[str, Any]],
        shared_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "metrics_payload": metrics_payload,
                "shared_context": shared_context,
            }
        )
        operation_refs = [
            item["artifact_id"] for item in shared_context.get("operations") or []
        ]
        return {
            "metrics": [
                {
                    "high_level_metric": item["high_level_metric"],
                    "score": 1,
                    "reasoning": "The metric passes.",
                    "evidence_refs": operation_refs[:1],
                    "fatal_failures": [],
                    "minor_failures": [],
                }
                for item in metrics_payload
            ]
        }

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
        return {
            "score": 1,
            "reasoning": "The metric passes.",
            "fatal_failures": [],
            "minor_failures": [],
        }


class RoutingPassOwnershipFailJudge(PassingBatchJudge):
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
        if "ownership completeness only" not in rubric:
            return {
                "score": 1,
                "reasoning": "Every executed delegation used a capable owner.",
                "fatal_failures": [],
                "minor_failures": [],
            }
        return {
            "score": 0,
            "reasoning": "A material prerequisite had no accountable owner.",
            "fatal_failures": [
                {
                    "span_index": 5,
                    "entity_name": "root",
                    "reasoning": "Reservation work was unassigned.",
                    "explanation": "The selected plan required a reservation.",
                    "observed_impact": "unassigned_material_work",
                    "confidence": 0.9,
                    "evidence": [],
                }
            ],
            "minor_failures": [],
        }


def _context() -> TrajectoryContext:
    context = TrajectoryContext(
        "Agents may verify material claims before final synthesis."
    )
    context.evidence.append(
        EvidenceFact(
            span_index=0,
            fact_type="user_statement",
            content="Plan a four-night trip under 500 EUR.",
            source_name="user",
        )
    )
    repeated_content = (
        '[Tool: lookup_fares]\n  Called with: {"route": "A-B"}\n'
        '  Returned: {"fare": 80}'
    )
    for span_index in (2, 4):
        context.evidence.append(
            EvidenceFact(
                span_index=span_index,
                fact_type="tool_output",
                content=repeated_content,
                source_name="lookup_fares",
            )
        )
    context.claims.append(
        ClaimEntry(
            span_index=3,
            claim_type="assertion",
            content="The fare is 80 EUR.",
            entity_name="itinerary_agent",
        )
    )
    context.intents.append(
        IntentEntry(
            name="trip_plan",
            source="user",
            first_seen=0,
            last_seen=5,
            status="fulfilled",
            description="Produce the requested trip plan.",
        )
    )
    context.latest_root_answer = "A four-night trip is available for 80 EUR."
    context.latest_root_answer_span_index = 5
    return context


def test_named_suites_preserve_legacy_and_expose_paper_metrics() -> None:
    assert SUPPORTED_METRIC_SUITES == ("legacy_v1", "paper_v1", "paper_v2")
    assert len(build_metric_suite("legacy_v1")) == 14
    assert tuple(metric.name for metric in build_metric_suite("paper_v1")) == (
        PAPER_METRIC_NAMES
    )
    assert tuple(metric.name for metric in build_metric_suite("paper_v2")) == (
        PAPER_V2_METRIC_NAMES
    )


def test_paper_v2_revises_only_the_agreed_metrics() -> None:
    suite = build_metric_suite("paper_v2")
    versions = {metric.name: metric.definition_version for metric in suite}

    assert UPDATED_METRIC_NAMES == {
        "Delegation Accuracy",
        "Goal Alignment",
        "Handoff Quality",
        "Communication Efficiency",
    }
    assert {
        name for name, version in versions.items() if version == "paper_v2"
    } == UPDATED_METRIC_NAMES
    assert all(
        version == "paper_v1"
        for name, version in versions.items()
        if name not in UPDATED_METRIC_NAMES
    )


def test_paper_v2_delegation_payload_includes_root_ownership_context() -> None:
    payload = DelegationAccuracyMetricV2().to_judge_payload(_context())["context"]

    assert payload["user_statements"][0]["artifact_id"].startswith("user:")
    assert payload["intents"][0]["artifact_id"] == "intent:0"
    assert "ownership_audit_protocol" in payload
    assert "root_requirements" in payload["ownership_audit_protocol"]
    assert "no accountable owner" in DelegationAccuracyMetricV2.rubric


def test_paper_v2_delegation_combines_routing_and_ownership_subaudits() -> None:
    judge = RoutingPassOwnershipFailJudge()

    result = DelegationAccuracyMetricV2(judge=judge).evaluate(_context())

    assert len(judge.calls) == 2
    assert result.score == 0
    assert result.metadata["subscores"] == {
        "executed_routing_accuracy": 1,
        "ownership_completeness": 0,
    }
    assert result.metadata["executed_routing_result_reused"] is False
    assert result.metadata["usage"]["total_tokens"] == 240
    assert result.fatal_failures[0].observed_impact == "unassigned_material_work"


def test_paper_v2_rubrics_encode_revised_construct_boundaries() -> None:
    goal = " ".join(GoalAlignmentMetricV2.rubric.split())
    handoff = " ".join(HandoffQualityMetricV2.rubric.split())
    communication = " ".join(CommunicationEfficiencyMetric.rubric.split())

    assert "root goal contract" in goal
    assert "hard constraints, priority ordering" in goal
    assert "deliberately private constraint" in handoff
    assert "downstream consequence" in handoff
    assert "irrelevant payload" in communication
    assert "information and control value" in communication


def test_unknown_metric_suite_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown trajectory-context metric suite"):
        build_metric_suite("future_v9")


def test_paper_suite_uses_dedicated_delegation_and_grounding_calls() -> None:
    judge = PassingBatchJudge()

    results = evaluate_metric_suite_batched(
        _context(),
        metric_suite="paper_v1",
        stateful_result={},
        judge=judge,
    )

    assert len(judge.calls) == 3
    dedicated_calls = {
        call["metric_name"]: call for call in judge.calls if "metric_name" in call
    }
    assert set(dedicated_calls) == {"Delegation Accuracy"}
    assert set(dedicated_calls["Delegation Accuracy"]["context_payload"]) == {
        "delegation_audit",
        "delegation_summary",
    }
    grounding_call = next(
        call
        for call in judge.calls
        if "metrics_payload" in call
        and [item["high_level_metric"] for item in call["metrics_payload"]]
        == ["Groundedness"]
    )
    assert "direct_tool_evidence" in grounding_call["shared_context"]
    assert "monetary_claim_index" not in grounding_call["shared_context"]
    assert [result.high_level_metric for result in results] == list(PAPER_METRIC_NAMES)
    assert {
        result.high_level_metric
        for result in results
        if result.metadata["affects_trajectory_score"]
    } == PAPER_OUTCOME_METRICS
    assert {result.metadata["definition_version"] for result in results} == {"paper_v1"}
    assert {result.metadata["metric_suite"] for result in results} == {"paper_v1"}

    efficiency = next(
        result
        for result in results
        if result.high_level_metric == "Coordination Efficiency"
    )
    assert efficiency.metadata["coordination_summary"]["exact_repeated_call_count"] == 1


def test_operation_context_preserves_order_and_repeat_diagnostics() -> None:
    operations, summary = build_operation_context(_context())

    assert [item["span_index"] for item in operations] == [2, 3, 4]
    assert [item["artifact_id"] for item in operations] == [
        "operation:2",
        "operation:3",
        "operation:4",
    ]
    assert summary["tool_operations"] == 2
    assert summary["llm_operations"] == 1
    assert summary["exact_repeated_call_count"] == 1
    assert summary["exact_repeated_call_groups"][0]["span_indices"] == [2, 4]


def test_operation_context_recovers_peer_scope_for_legacy_context() -> None:
    context = TrajectoryContext("Delegate telemetry work to the telemetry agent.")
    context.evidence.extend(
        [
            EvidenceFact(
                span_index=0,
                fact_type="policy_rule",
                content="You are the root SRE orchestrator.",
                source_name="semantic_contract:sre",
            ),
            EvidenceFact(
                span_index=2,
                fact_type="policy_rule",
                content="You are the telemetry specialist. Use get_metrics.",
                source_name="semantic_contract:telemetry",
            ),
            EvidenceFact(
                span_index=1,
                fact_type="tool_output",
                content=(
                    "[Tool: delegate_to_telemetry]\n"
                    '  Called with: {"task": "Inspect service metrics."}\n'
                    '  Returned: {"status": "ok"}'
                ),
                source_name="delegate_to_telemetry",
            ),
            EvidenceFact(
                span_index=3,
                fact_type="tool_output",
                content=(
                    "[Tool: get_metrics]\n"
                    '  Called with: {"service": "payments"}\n'
                    '  Returned: {"error_rate": 0.2}'
                ),
                source_name="get_metrics",
            ),
            EvidenceFact(
                span_index=5,
                fact_type="tool_output",
                content=(
                    "[Tool: get_metrics]\n"
                    '  Called with: {"service": "payments"}\n'
                    '  Returned: {"error_rate": 0.2}'
                ),
                source_name="get_metrics",
            ),
        ]
    )
    context.work_units.append(
        WorkUnit(
            work_id="work:0",
            allocator_agent_id="sre",
            recipient_agent_ids=["telemetry"],
            request_span_index=1,
        )
    )
    context.claims.extend(
        [
            ClaimEntry(
                span_index=0,
                claim_type="assertion",
                content='Call delegate_to_telemetry with task "Inspect metrics".',
                entity_name="LLMCall",
            ),
            ClaimEntry(
                span_index=2,
                claim_type="peer_agent_assertion",
                content='Call get_metrics with service "payments".',
                entity_name="LLMCall",
            ),
            ClaimEntry(
                span_index=4,
                claim_type="assertion",
                content="Review the returned evidence.",
                entity_name="LLMCall",
            ),
        ]
    )

    operations, summary = build_operation_context(context)
    by_span = {operation["span_index"]: operation for operation in operations}

    assert by_span[0]["agent_id"] == "sre"
    assert by_span[0]["actor_scope"] == "root"
    assert by_span[1]["delegation_id"] == "delegation:1"
    assert by_span[1]["recipient_agent_id"] == "telemetry"
    assert by_span[2]["claim_type"] == "peer_agent_assertion"
    assert by_span[2]["agent_id"] == "telemetry"
    assert by_span[2]["actor_scope"] == "peer"
    assert by_span[2]["parent_delegation_id"] == "delegation:1"
    assert by_span[2]["delegator_agent_id"] == "sre"
    assert by_span[3]["agent_id"] == "telemetry"
    assert by_span[3]["actor_scope"] == "peer"
    assert by_span[3]["parent_delegation_id"] == "delegation:1"
    assert by_span[4]["agent_id"] == "sre"
    assert by_span[4]["actor_scope"] == "root"
    assert by_span[5]["agent_id"] == "sre"
    assert by_span[5]["actor_scope"] == "root"
    assert summary["root_operations"] == 4
    assert summary["peer_operations"] == 2
    assert summary["unscoped_operations"] == 0
    assert summary["exact_repeated_call_count"] == 0


def test_delegation_context_uses_structural_capability_evidence() -> None:
    shared_protocol = (
        "Shared protocol: tools include get_fares and query_graph_database."
    )
    context = TrajectoryContext("Route pricing through the appropriate specialist.")
    context.evidence.extend(
        [
            EvidenceFact(
                span_index=0,
                fact_type="policy_rule",
                source_name="semantic_contract:itinerary_agent",
                content=(
                    "Use query_graph_database for routes and travel times.\n"
                    "If asked for fares, provide a best-effort estimate.\n"
                    f"{shared_protocol}"
                ),
            ),
            EvidenceFact(
                span_index=0,
                fact_type="policy_rule",
                source_name="semantic_contract:concierge_agent",
                content=f"Use get_fares for transport fares.\n{shared_protocol}",
            ),
            EvidenceFact(
                span_index=2,
                fact_type="tool_output",
                source_name="delegate_to_itinerary_agent",
                agent_id="moderator",
                actor_scope="root",
                content=(
                    "[Tool: delegate_to_itinerary_agent]\n"
                    '  Called with: {"task": "Find a route and exact fare."}\n'
                    '  Returned: {"result": "The fare is $85."}'
                ),
                outcome="output",
            ),
            EvidenceFact(
                span_index=3,
                fact_type="tool_output",
                source_name="query_graph_database",
                agent_id="itinerary_agent",
                actor_scope="peer",
                content=(
                    "[Tool: query_graph_database]\n"
                    '  Called with: {"origin": "A", "destination": "B"}\n'
                    '  Returned: {"route_id": "AB"}'
                ),
                outcome="output",
            ),
        ]
    )
    context.work_units.append(
        WorkUnit(
            work_id="work:0",
            allocator_agent_id="moderator",
            recipient_agent_ids=["itinerary_agent"],
            request_span_index=2,
            outcome="completed",
        )
    )
    context.agents = {
        "itinerary_agent": AgentProfile(
            agent_id="itinerary_agent",
            observed_tools=["query_graph_database"],
        ),
        "concierge_agent": AgentProfile(agent_id="concierge_agent"),
    }

    audit, summary = build_delegation_context(context)

    assert summary["delegation_count"] == 1
    assert audit[0]["delegation_id"] == "delegation:2"
    assert audit[0]["recipient_agent"] == "itinerary_agent"
    assert audit[0]["delegated_task"] == "Find a route and exact fare."
    assert audit[0]["delegation_outcome"] == "completed"
    assert audit[0]["work_id"] == "work:0"
    assert [
        item["tool_name"] for item in audit[0]["observed_tools_before_next_delegation"]
    ] == ["query_graph_database"]
    assert "capability_gap_candidates" not in audit[0]
    profiles = {item["agent_id"]: item for item in summary["agent_capabilities"]}
    assert profiles["itinerary_agent"]["observed_tools"] == ["query_graph_database"]
    assert profiles["concierge_agent"]["observed_tools"] == []
    assert "agent_specific_contract_text" not in profiles["concierge_agent"]

    _, detailed = build_delegation_context(context, include_contract_text=True)
    texts = {
        item["agent_id"]: item["agent_specific_contract_text"]
        for item in detailed["agent_capabilities"]
    }
    assert texts["concierge_agent"] == "Use get_fares for transport fares."
    assert "query_graph_database for routes" in texts["itinerary_agent"]
    assert all("Shared protocol" not in text for text in texts.values())

    judge_context = DelegationAccuracyMetric().to_judge_payload(context)["context"]
    assert {
        item["agent_id"]: item["agent_specific_contract_text"]
        for item in judge_context["delegation_summary"]["agent_capabilities"]
    } == {agent_id: " ".join(text.split()) for agent_id, text in texts.items()}
    payload = build_context_payload(
        context,
        DelegationAccuracyMetric().input_config,
        metric_name="Delegation Accuracy",
    )
    assert payload["delegation_audit"] == audit
    assert payload["delegation_summary"]["capability_precedence"].startswith(
        "Tool-backed"
    )
    assert "every requirement" in (payload["delegation_summary"]["decision_protocol"])


def test_revised_rubrics_separate_routing_recovery_and_external_failure() -> None:
    delegation_rubric = " ".join(DelegationAccuracyMetric.rubric.split())
    instruction_rubric = " ".join(InstructionFollowingMetric.rubric.split())

    assert "claims to evaluate, not proof of capability" in delegation_rubric
    assert "system capability gap" in delegation_rubric
    assert "same action and object" in delegation_rubric
    assert "agent_capabilities" in delegation_rubric
    assert "capability_gap_candidate" not in delegation_rubric
    assert "does not erase an executed material wrong-owner delegation" in (
        delegation_rubric
    )
    assert "downstream queue, tool, or recipient failure" in instruction_rubric
    assert "not itself an instruction violation" in instruction_rubric
    assert 'Do not redefine "use an agent"' in instruction_rubric
    assert "checking timing" in instruction_rubric
    assert "partial or progress response" in instruction_rubric
    assert "displayed plan itself is corrected" in instruction_rubric


def test_metric_status_tracks_audit_normalized_score() -> None:
    context = TrajectoryContext(policy_text="Follow the supplied instruction.")
    result = HighLevelMetricResult(
        high_level_metric="Instruction Following",
        score=1,
        status="fail",
        reasoning="The unsupported failure was rejected by the audit.",
    )

    decorated = InstructionFollowingMetric().decorate_result(result, context)

    assert decorated.status == "pass"


def test_instruction_execution_audit_counts_failed_delegation_as_attempt() -> None:
    context = TrajectoryContext(
        policy_text="Make sure you use ALL agents. No retry is required."
    )
    context.evidence.extend(
        [
            EvidenceFact(
                span_index=0,
                fact_type="policy_rule",
                source_name="semantic_contract:itinerary_agent",
                content="Use query_graph_database for routes.",
            ),
            EvidenceFact(
                span_index=0,
                fact_type="policy_rule",
                source_name="semantic_contract:schedule_agent",
                content="Use lookup_schedule for schedules.",
            ),
            EvidenceFact(
                span_index=1,
                fact_type="tool_output",
                source_name="delegate_to_itinerary_agent",
                agent_id="moderator",
                actor_scope="root",
                content=(
                    "[Tool: delegate_to_itinerary_agent]\n"
                    '  Called with: {"task": "Find routes."}\n'
                    "  Returned: agent turn failed: queue full"
                ),
            ),
            EvidenceFact(
                span_index=2,
                fact_type="tool_output",
                source_name="delegate_to_schedule_agent",
                agent_id="moderator",
                actor_scope="root",
                content=(
                    "[Tool: delegate_to_schedule_agent]\n"
                    '  Called with: {"task": "Find schedules."}\n'
                    "  Returned: agent turn failed"
                ),
            ),
        ]
    )

    context.evidence.append(
        EvidenceFact(
            span_index=3,
            fact_type="tool_output",
            source_name="delegate_to_itinerary_agent",
            agent_id="moderator",
            actor_scope="root",
            content=(
                "[Tool: delegate_to_itinerary_agent]\n"
                '  Called with: {"task": "Find routes."}\n'
                '  Returned: {"routes": ["AB"]}'
            ),
            outcome="output",
        )
    )
    context.work_units.extend(
        [
            WorkUnit(
                work_id="work:0",
                allocator_agent_id="moderator",
                recipient_agent_ids=["itinerary_agent"],
                request_span_index=1,
                outcome="failed",
            ),
            WorkUnit(
                work_id="work:1",
                allocator_agent_id="moderator",
                recipient_agent_ids=["schedule_agent"],
                request_span_index=2,
                outcome="failed",
            ),
            WorkUnit(
                work_id="work:2",
                allocator_agent_id="moderator",
                recipient_agent_ids=["itinerary_agent"],
                request_span_index=3,
                outcome="completed",
                attempt_index=2,
                retry_of_work_id="work:0",
                retry_basis="same_request",
            ),
        ]
    )

    audit = build_instruction_execution_context(context)
    payload = build_context_payload(
        context,
        InstructionFollowingMetric().input_config,
        metric_name="Instruction Following",
    )

    assert audit["attempted_peer_agents"] == [
        "itinerary_agent",
        "schedule_agent",
    ]
    assert audit["delegation_attempt_count_by_agent"] == {
        "itinerary_agent": 2,
        "schedule_agent": 1,
    }
    assert [
        (
            item["work_id"],
            item["outcome"],
            item["attempt_index"],
            item["retry_of_work_id"],
        )
        for item in audit["delegation_attempts"]
    ] == [
        ("work:0", "failed", 1, ""),
        ("work:1", "failed", 1, ""),
        ("work:2", "completed", 2, "work:0"),
    ]
    assert "binding_decisions" not in audit
    assert payload["instruction_execution_audit"] == audit

    focused = build_instruction_following_context(context)
    assert focused["instruction_execution_audit"] == audit
    assert "claims" not in focused
    assert "constraint_evidence_index" not in focused
    assert len(focused["authoritative_tool_outputs"]) == 3


def test_shared_metric_context_keeps_complete_fact_content() -> None:
    full_content = "prefix " + ("detail " * 500) + "Azure Lake Promenade"
    context = TrajectoryContext(policy_text="")
    context.evidence.append(
        EvidenceFact(
            span_index=3,
            fact_type="tool_output",
            source_name="get_attractions_description",
            content=full_content,
        )
    )

    payload = build_context_payload(
        context,
        InstructionFollowingMetric().input_config,
        metric_name="Instruction Following",
    )

    assert payload["fact_store"][0]["content"] == full_content


def test_groundedness_separates_direct_tools_from_delegation_outputs() -> None:
    context = TrajectoryContext(policy_text="")
    context.evidence.extend(
        [
            EvidenceFact(
                span_index=1,
                fact_type="tool_output",
                source_name="delegate_to_concierge_agent",
                content=(
                    "[Tool: delegate_to_concierge_agent]\n"
                    '  Returned: {"value": "Estimated total: $1000"}'
                ),
            ),
            EvidenceFact(
                span_index=2,
                fact_type="tool_output",
                source_name="get_fares",
                content="[Tool: get_fares]\n  Called with: {}",
            ),
        ]
    )
    context.work_units.append(
        WorkUnit(
            work_id="work:0",
            allocator_agent_id="moderator",
            recipient_agent_ids=["concierge_agent"],
            request_span_index=1,
        )
    )
    context.latest_root_answer = "The verified total is $1000."
    context.latest_root_answer_span_index = 3

    payload = GroundednessMetric().to_judge_payload(context)["context"]

    assert [item["source_name"] for item in payload["direct_tool_evidence"]] == [
        "get_fares"
    ]
    assert [item["source_name"] for item in payload["delegation_outputs"]] == [
        "delegate_to_concierge_agent"
    ]
    assert "monetary_claim_index" not in payload
    assert "superlative_claim_index" not in payload
    assert GroundednessMetric().deterministic_precheck(context) is None


def test_instruction_following_rejects_unattributed_incompleteness_failure() -> None:
    metric = InstructionFollowingMetric()
    result = metric.result_from_raw(
        {
            "score": 0,
            "reasoning": "The final answer is incomplete.",
            "fatal_failures": [
                {
                    "span_index": 9,
                    "entity_name": "final_answer",
                    "reasoning": "Pricing remains pending.",
                    "evidence": [
                        {
                            "span_index": 9,
                            "source_name": "final_answer",
                            "kind": "final_answer",
                            "content": "Pricing remains pending.",
                            "artifact_id": "final_answer",
                        }
                    ],
                }
            ],
            "minor_failures": [],
        },
        judge=PassingBatchJudge(),
    )

    assert result.score == 1
    assert result.fatal_failures == []
    assert result.metadata["unsubstantiated_fatal_count"] == 1
    assert result.metadata["score_was_normalized"] is True


def test_instruction_following_keeps_attributed_behavior_failure() -> None:
    metric = InstructionFollowingMetric()
    result = metric.result_from_raw(
        {
            "score": 0,
            "reasoning": "A known window was dropped.",
            "fatal_failures": [
                {
                    "span_index": 9,
                    "entity_name": "telemetry",
                    "reasoning": "The 15m window was omitted.",
                    "evidence": [
                        {
                            "span_index": 5,
                            "source_name": "peer_agent",
                            "kind": "fact",
                            "content": "Call get_metrics with window=15m.",
                            "artifact_id": "fact:5",
                        },
                        {
                            "span_index": 9,
                            "source_name": "telemetry",
                            "kind": "claim",
                            "content": "get_metrics(service=payment-service)",
                            "artifact_id": "claim:4",
                        },
                    ],
                }
            ],
            "minor_failures": [],
        },
        judge=PassingBatchJudge(),
    )

    assert result.score == 0
    assert len(result.fatal_failures) == 1


def test_saved_context_can_be_restored_for_metric_only_comparison(tmp_path) -> None:
    artifact = tmp_path / "trajectory_context.json"
    artifact.write_text(
        json.dumps(
            {
                "session_id": "session-1",
                "policy_text": "Verify material claims.",
                "evidence": [
                    {
                        "span_index": 0,
                        "fact_type": "user_statement",
                        "content": "Plan a trip.",
                        "source_name": "user",
                    }
                ],
                "intents": [
                    {
                        "name": "trip",
                        "source": "user",
                        "first_seen": 0,
                        "last_seen": 2,
                        "status": "fulfilled",
                        "description": "Plan a trip.",
                        "events": [{"span_index": 2, "status": "fulfilled"}],
                    }
                ],
                "claims": [
                    {
                        "span_index": 2,
                        "claim_type": "completion_claim",
                        "content": "Trip complete.",
                        "entity_name": "moderator",
                        "agent_id": "moderator",
                        "actor_scope": "root",
                        "span_id": "span-2",
                        "parent_span_id": "turn-1",
                        "trace_id": "trace-1",
                    }
                ],
                "final_answer_context": {
                    "final_answer": "Here is the trip.",
                    "final_answer_span_index": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    context, payload = load_trajectory_context_artifact(artifact)

    assert payload["session_id"] == "session-1"
    assert context.policy_text == "Verify material claims."
    assert context.intents[0].events[0]["status"] == "fulfilled"
    assert context.latest_root_answer == "Here is the trip."
    assert context.latest_root_answer_span_index == 2
    assert context.claims[0].agent_id == "moderator"
    assert context.claims[0].actor_scope == "root"
    assert context.claims[0].span_id == "span-2"
    assert context.claims[0].parent_span_id == "turn-1"
    assert context.claims[0].trace_id == "trace-1"


def test_temporal_options_keep_legacy_default_and_validate_paper_suite() -> None:
    assert TemporalMetricOptions().high_level_metric_suite == "legacy_v1"
    assert (
        TemporalMetricOptions(
            high_level_metric_suite="paper_v1"
        ).high_level_metric_suite
        == "paper_v1"
    )
    assert (
        TemporalMetricOptions(
            high_level_metric_suite="paper_v2"
        ).high_level_metric_suite
        == "paper_v2"
    )
    with pytest.raises(ValueError):
        TemporalMetricOptions(high_level_metric_suite="unknown")
