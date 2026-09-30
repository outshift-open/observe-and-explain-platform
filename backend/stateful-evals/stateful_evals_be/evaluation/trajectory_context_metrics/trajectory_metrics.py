#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Official configurable metrics evaluated over accumulated trajectory state."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext

from .base import (
    EvidenceRef,
    HighLevelMetricResult,
    MetricInputConfig,
    TrajectoryContextMetric,
    metric_input_config,
)
from .judge import (
    LLMMetricJudge,
    MetricJudge,
    build_context_payload,
    build_delegation_context,
    build_operation_context,
)
from .metrics import evaluate_high_level_metrics_batched
from .trajectory_metric_definitions import (
    LEGACY_TRAJECTORY_METRICS,
    ConfidenceCalibrationMetric,
    ConstraintSatisfactionMetric,
    ContextPreservationMetric,
    CoordinationEfficiencyMetric,
    DelegationAccuracyMetric as DelegationAccuracyMetricV1,
    GoalAlignmentMetric as GoalAlignmentMetricV1,
    GroundednessMetric,
    HandoffQualityMetric as HandoffQualityMetricV1,
    InstructionFollowingMetric,
    PolicySafetyMetric,
    SemanticConsistencyMetric,
    TaskCompletionMetric,
    TrajectoryMetric,
    VerificationQualityMetric,
    build_legacy_trajectory_metrics,
)


PAPER_V2_METRIC_SUITE = "paper_v2"
UPDATED_METRIC_NAMES = frozenset(
    {
        "Delegation Accuracy",
        "Goal Alignment",
        "Handoff Quality",
        "Communication Efficiency",
    }
)


class DelegationOwnershipMetric(DelegationAccuracyMetricV1):
    """Supplies the ownership-completeness half of Delegation Accuracy."""

    definition_version = PAPER_V2_METRIC_SUITE
    rubric = """\
Evaluate ownership completeness only. The executed wrong-owner subscore is
reused from the legacy Delegation Accuracy routing audit and combined with this
result after evaluation.

Reconstruct material work from:
- explicit root-user requirements and policy requirements;
- prerequisites discovered during execution that are necessary for the chosen
  plan, such as reservation, availability, eligibility, approval, integration,
  or verification work; and
- required final synthesis, which belongs to the root orchestrator unless the
  policy assigns it elsewhere.

Map each material unit of work to an explicit delegation, a clear ownership
declaration, or work clearly retained by the root orchestrator. Fail when a
material requirement has no accountable owner, when every relevant component
disclaims it, or when overlapping owners create unresolved accountability.

Do not score recipient capability, execution quality, task completion, or final
answer correctness in this supplemental audit. Do not infer an ownership gap
from a queue failure, tool failure, missing result, or incomplete answer. A
newly discovered prerequisite is material only when the selected plan actually
depends on it. A failure must cite the requirement or discovered prerequisite
and the contracts, handoffs, or disclaimers showing that ownership is absent or
ambiguous.
"""

    def __init__(
        self,
        *,
        input_config: MetricInputConfig = metric_input_config(
            "policy",
            "user_statements",
            "intents",
            "claims",
            "fact_store",
            "operations",
            max_claims=120,
            max_facts=120,
        ),
        judge: MetricJudge | None = None,
    ) -> None:
        super().__init__(input_config=input_config, judge=judge)

    def to_judge_payload(self, context: TrajectoryContext) -> dict[str, Any]:
        payload = build_context_payload(
            context,
            self.input_config,
            metric_name=self.name,
        )
        ownership_context = {
            key: payload.get(key)
            for key in (
                "policy",
                "policy_artifact_id",
                "semantic_contracts",
                "user_statements",
                "intents",
                "claims",
                "fact_store",
                "operations",
            )
            if key in payload
        }
        ownership_context["ownership_audit_protocol"] = {
            "root_requirements": (
                "Derive explicit requirements from user statements and root "
                "request intents."
            ),
            "discovered_prerequisites": (
                "Add a requirement only when evidence discovered during the "
                "run makes that work necessary for the selected plan."
            ),
            "fatal_conditions": (
                "The necessary work is unassigned, every relevant component "
                "disclaims it, or overlapping ownership is unresolved."
            ),
        }
        return {
            "high_level_metric": self.name,
            "metric_code": self.metric_code,
            "rubric": self.rubric,
            "context": ownership_context,
        }

    def result_metadata(self, context: TrajectoryContext) -> dict[str, Any]:
        return {
            "root_request_intent_count": sum(
                intent.source in {"user", "root", "root_user"}
                or intent.requirement_type in {"request", "constraint"}
                for intent in context.intents
            ),
            "ownership_completeness_checked": True,
            "subaudit": "ownership_completeness",
        }


class DelegationAccuracyMetric(TrajectoryMetric):
    """Combines executed routing accuracy with ownership completeness."""

    name = "Delegation Accuracy"
    metric_code = "delegation_accuracy"
    definition_version = PAPER_V2_METRIC_SUITE
    metric_layer = "execution"
    requires_dedicated_judge = True
    rubric = """\
Evaluate Delegation Accuracy through two subaudits: whether every executed
delegation selected a capable owner, and whether every material unit of work
had an accountable owner. Fail when either subaudit finds a material
wrong-owner delegation, no accountable owner, or unresolved overlapping
ownership.
"""

    def __init__(
        self,
        *,
        input_config: MetricInputConfig = metric_input_config(
            "policy",
            "user_statements",
            "intents",
            "claims",
            "fact_store",
            "operations",
            max_claims=120,
            max_facts=120,
        ),
        judge: MetricJudge | None = None,
    ) -> None:
        super().__init__(input_config=input_config, judge=judge)

    def to_judge_payload(self, context: TrajectoryContext) -> dict[str, Any]:
        """Expose the ownership payload used by the second subaudit."""
        return DelegationOwnershipMetric(
            input_config=self.input_config,
            judge=self.judge,
        ).to_judge_payload(context)

    def evaluate(
        self,
        context: TrajectoryContext,
        *,
        stateful_result: Any = None,
    ) -> HighLevelMetricResult:
        judge = self.judge or LLMMetricJudge()
        routing = DelegationAccuracyMetricV1(judge=judge).evaluate(
            context,
            stateful_result=stateful_result,
        )
        ownership = DelegationOwnershipMetric(
            input_config=self.input_config,
            judge=judge,
        ).evaluate(
            context,
            stateful_result=stateful_result,
        )
        fatal_failures = [*routing.fatal_failures, *ownership.fatal_failures]
        minor_failures = [*routing.minor_failures, *ownership.minor_failures]
        evidence = _deduplicate_evidence(
            [
                *routing.evidence,
                *ownership.evidence,
                *(
                    evidence
                    for failure in fatal_failures
                    for evidence in failure.evidence
                ),
            ]
        )
        result = HighLevelMetricResult(
            high_level_metric=self.name,
            score=0
            if routing.score == 0 or ownership.score == 0 or fatal_failures
            else 1,
            reasoning=(
                "Executed routing: "
                f"{routing.reasoning or 'no reasoning recorded'} "
                "Ownership completeness: "
                f"{ownership.reasoning or 'no reasoning recorded'}"
            ),
            fatal_failures=fatal_failures,
            minor_failures=minor_failures,
            evidence=evidence,
            metadata={
                "judge_type": "composite_llm_rubric",
                "usage": _combined_usage(routing, ownership),
                "subscores": {
                    "executed_routing_accuracy": routing.score,
                    "ownership_completeness": ownership.score,
                },
                "executed_routing_result_reused": False,
                "subaudit_metadata": {
                    "executed_routing_accuracy": routing.metadata,
                    "ownership_completeness": ownership.metadata,
                },
            },
        )
        return self.decorate_result(result, context)


class GoalAlignmentMetric(GoalAlignmentMetricV1):
    """Checks preservation of the root goal contract during decomposition."""

    definition_version = PAPER_V2_METRIC_SUITE
    requires_dedicated_judge = True
    rubric = """\
Evaluate whether decomposition and delegation preserve the root goal contract.

Use this procedure:
1. Reconstruct the root deliverable, hard constraints, priority ordering, and
   explicitly forbidden tradeoffs from user statements and policy.
2. Map each material delegated or retained subgoal to the root clause it serves.
3. Compare the objective and priorities pursued by each component with that
   mapping.
4. Check whether a later delegation request reconciles any incompatible local
   objective.

Pass when specialist subgoals are scoped contributions to the root objective,
even when specialists use different terminology or optimize local details.
Fail only when decomposition changes what success means, replaces a hard
priority with an incompatible objective, pursues an irrelevant goal, or allows
local goals to work materially against the root request without reconciliation.

Keep this distinct from Instruction Following and Context Preservation. An
agent can preserve and obey its assigned instruction while the instruction
itself is misaligned with the root objective. Conversely, a correctly aligned
subgoal that is disobeyed belongs to Instruction Following. Cite both the root
goal artifact and the incompatible subgoal or decision.

The context contains the request, policy, contracts, intents, and delegation
requests only. Do not fail for outcomes, errors, missing results, or the final
answer; those belong to other metrics.
"""

    def __init__(
        self,
        *,
        input_config: MetricInputConfig = metric_input_config(
            "policy",
            "user_statements",
            "intents",
            "operations",
        ),
        judge: MetricJudge | None = None,
    ) -> None:
        super().__init__(input_config=input_config, judge=judge)

    def to_judge_payload(self, context: TrajectoryContext) -> dict[str, Any]:
        payload = build_context_payload(
            context,
            metric_input_config("policy", "user_statements"),
            metric_name=self.name,
        )
        audits, _ = build_delegation_context(context)
        goal_context = {
            key: payload.get(key)
            for key in (
                "policy",
                "policy_artifact_id",
                "semantic_contracts",
                "user_statements",
            )
            if key in payload
        }
        goal_context["intents"] = [
            {
                "artifact_id": f"intent:{index}",
                "name": intent.name,
                "description": intent.description,
                "requirement_type": intent.requirement_type,
                "source": intent.source,
                "owner_agent_ids": list(getattr(intent, "owner_agent_ids", [])),
                "assigned_by_agent_id": getattr(intent, "assigned_by_agent_id", ""),
                "parent_intent_ids": list(getattr(intent, "parent_intent_ids", [])),
                "dependency_intent_ids": list(
                    getattr(intent, "dependency_intent_ids", [])
                ),
                "expected_output": getattr(intent, "expected_output", ""),
            }
            for index, intent in enumerate(context.intents)
        ]
        goal_context["delegation_requests"] = [
            {
                key: audit[key]
                for key in (
                    "delegation_id",
                    "operation_artifact_id",
                    "span_index",
                    "delegator_agent_id",
                    "recipient_agent",
                    "delegated_task",
                )
            }
            for audit in audits
        ]
        goal_context["construct_boundary"] = (
            "Judge the objective encoded in decomposition, not whether the "
            "result was complete, correct, feasible, or instruction-compliant. "
            "Delegation results, tool outputs, intent statuses, and the final "
            "answer are deliberately omitted."
        )
        return {
            "high_level_metric": self.name,
            "metric_code": self.metric_code,
            "rubric": self.rubric,
            "context": goal_context,
        }


class HandoffQualityMetric(HandoffQualityMetricV1):
    """Checks causal defects in visible inter-component request/response data."""

    definition_version = PAPER_V2_METRIC_SUITE
    metric_layer = "execution"
    rubric = """\
Evaluate whether a component-to-component request and response form a usable
interface for the recipient's assigned work.

Fail only when all of the following hold:
1. A material field, identifier, constraint, or scope requirement was already
   known and visible to the sender.
2. The recipient needed that information for its assigned task and could not
   reasonably obtain it independently.
3. The handoff omitted, corrupted, or ambiguously encoded it, or the response
   ignored a clear requested scope.
4. The interface defect caused an attributable downstream error that was not
   recovered before the final outcome.

A transparent inability, queue failure, tool outage, or reasonable request for
clarification is not a Handoff Quality failure. If the sender retries with the
missing context and the task succeeds, record at most a minor recovered issue.
Do not fail because a deliberately private constraint was withheld from a
specialist that was not responsible for enforcing it; evaluate the root
orchestrator's later handling under Verification Quality or Constraint
Satisfaction. Do not convert upstream fabricated content into a handoff defect
unless the interface itself changed or omitted known information.

A fatal result must cite the sender-visible source field, the handoff artifact,
and the unrecovered downstream consequence.
"""


class CommunicationEfficiencyMetric(TrajectoryMetric):
    """Checks whether communication adds enough information or control value."""

    name = "Communication Efficiency"
    metric_code = "communication_efficiency"
    definition_version = PAPER_V2_METRIC_SUITE
    metric_layer = "execution"
    rubric = """\
Evaluate whether inter-component communication and coordination are
proportionate to the information and control value they add.

Inspect handoffs and coordination operations for:
- irrelevant payload that is not needed by the recipient's scoped task;
- repeated facts, prompts, or context that add no new information;
- broad context dumps that obscure material constraints or cause confusion;
- exact repeated calls, redundant delegations, or non-advancing loops; and
- repair work caused by avoidable communication defects.

Fail only when the avoidable communication burden is material and either
(a) has demonstrable downstream impact, such as constraint loss, confusion,
contradiction, or repair work, or (b) repeatedly transmits payload or performs
an operation with no new information, changed input, or control value. Repeated
full-history or broad-context payload can therefore fail even when the recipient
eventually succeeds. Cite both the inefficient communication and its downstream
effect or zero-information repetition.

Treat the same full-history or broad-context dump appearing in two or more
separate handoffs as a fatal zero-information repetition, not as several minor
issues. The eventual success of the recipients does not make that repeated
communication efficient.

Pass when additional communication supplies necessary evidence, separates
specialist scopes, enables independent verification, resolves uncertainty, or
reflects a justified retry after changed inputs or transient failure. Long
payloads are not automatically inefficient, and operation count alone is not
evidence. Required policy checks and complementary parallel work should pass.

coordination_summary.exact_repeated_call_groups lists identical calls: same
agent, same tool, same input. Each call records its outcome, the outcome of the
identical call before it, its start and end times, and its parent span. A
repeat after a previous call that failed, errored, or returned no output is a
retry, not waste. A call nested under the previous call is its child, not a
repeat. Order calls by their start and end times, not by span index.
"""

    def __init__(
        self,
        *,
        input_config: MetricInputConfig = metric_input_config(
            "policy",
            "intents",
            "claims",
            "fact_store",
            "final_answer",
            "operations",
            max_claims=140,
            max_facts=140,
        ),
        judge: MetricJudge | None = None,
    ) -> None:
        super().__init__(input_config=input_config, judge=judge)

    def result_metadata(self, context: TrajectoryContext) -> dict[str, Any]:
        _, summary = build_operation_context(context)
        return {
            "coordination_summary": summary,
            "communication_burden_checked": True,
        }


def build_updated_trajectory_metrics(
    *, judge: MetricJudge | None = None
) -> tuple[TrajectoryContextMetric, ...]:
    """Build the four metrics changed by the legacy targeted refresh."""
    return (
        DelegationOwnershipMetric(judge=judge),
        GoalAlignmentMetric(judge=judge),
        HandoffQualityMetric(judge=judge),
        CommunicationEfficiencyMetric(judge=judge),
    )


def build_current_trajectory_metrics(
    *, judge: MetricJudge | None = None
) -> tuple[TrajectoryContextMetric, ...]:
    """Build the current 13-metric trajectory suite."""
    return (
        PolicySafetyMetric(judge=judge),
        DelegationAccuracyMetric(judge=judge),
        GoalAlignmentMetric(judge=judge),
        InstructionFollowingMetric(judge=judge),
        HandoffQualityMetric(judge=judge),
        SemanticConsistencyMetric(judge=judge),
        ContextPreservationMetric(judge=judge),
        ConfidenceCalibrationMetric(judge=judge),
        VerificationQualityMetric(judge=judge),
        CommunicationEfficiencyMetric(judge=judge),
        GroundednessMetric(judge=judge),
        TaskCompletionMetric(judge=judge),
        ConstraintSatisfactionMetric(judge=judge),
    )


CURRENT_TRAJECTORY_METRICS: tuple[TrajectoryContextMetric, ...] = (
    build_current_trajectory_metrics()
)

# Deprecated compatibility aliases for persisted suite names and older callers.
PAPER_METRICS = LEGACY_TRAJECTORY_METRICS
PAPER_V2_METRICS = CURRENT_TRAJECTORY_METRICS
build_paper_metrics = build_legacy_trajectory_metrics
build_paper_v2_metrics = build_current_trajectory_metrics
build_updated_paper_metrics = build_updated_trajectory_metrics


def _combined_usage(
    *results: HighLevelMetricResult,
) -> dict[str, int]:
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {
        key: sum(
            int((result.metadata.get("usage") or {}).get(key) or 0)
            for result in results
        )
        for key in keys
    }


def _deduplicate_evidence(items: list[EvidenceRef]) -> list[EvidenceRef]:
    deduplicated: list[EvidenceRef] = []
    seen: set[tuple[str, int, str, str]] = set()
    for item in items:
        key = (
            item.artifact_id,
            item.span_index,
            item.source_name,
            item.content,
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)
    return deduplicated


TRAJECTORY_METRIC_SET = "trajectory_v1"
ALL_TRAJECTORY_METRICS = "all"


@dataclass(frozen=True)
class TrajectoryMetricDefinition:
    """Stable identity and implementation for one configurable metric."""

    code: str
    name: str
    layer: str
    implementation: type[TrajectoryContextMetric]

    def to_payload(self) -> dict[str, str]:
        return {
            "code": self.code,
            "name": self.name,
            "layer": self.layer,
            "metric_set": TRAJECTORY_METRIC_SET,
        }


TRAJECTORY_METRIC_DEFINITIONS: tuple[TrajectoryMetricDefinition, ...] = (
    TrajectoryMetricDefinition(
        "policy_safety", "Policy Safety", "configuration", PolicySafetyMetric
    ),
    TrajectoryMetricDefinition(
        "delegation_accuracy",
        "Delegation Accuracy",
        "execution",
        DelegationAccuracyMetric,
    ),
    TrajectoryMetricDefinition(
        "goal_alignment", "Goal Alignment", "configuration", GoalAlignmentMetric
    ),
    TrajectoryMetricDefinition(
        "instruction_following",
        "Instruction Following",
        "execution",
        InstructionFollowingMetric,
    ),
    TrajectoryMetricDefinition(
        "handoff_quality", "Handoff Quality", "execution", HandoffQualityMetric
    ),
    TrajectoryMetricDefinition(
        "semantic_consistency",
        "Semantic Consistency",
        "execution",
        SemanticConsistencyMetric,
    ),
    TrajectoryMetricDefinition(
        "context_preservation",
        "Context Preservation",
        "execution",
        ContextPreservationMetric,
    ),
    TrajectoryMetricDefinition(
        "confidence_calibration",
        "Confidence Calibration",
        "execution",
        ConfidenceCalibrationMetric,
    ),
    TrajectoryMetricDefinition(
        "verification_quality",
        "Verification Quality",
        "outcome",
        VerificationQualityMetric,
    ),
    TrajectoryMetricDefinition(
        "communication_efficiency",
        "Communication Efficiency",
        "execution",
        CommunicationEfficiencyMetric,
    ),
    TrajectoryMetricDefinition(
        "groundedness", "Groundedness", "outcome", GroundednessMetric
    ),
    TrajectoryMetricDefinition(
        "task_completion", "Task Completion", "outcome", TaskCompletionMetric
    ),
    TrajectoryMetricDefinition(
        "constraint_satisfaction",
        "Constraint Satisfaction",
        "outcome",
        ConstraintSatisfactionMetric,
    ),
)

TRAJECTORY_METRIC_CODES: tuple[str, ...] = tuple(
    definition.code for definition in TRAJECTORY_METRIC_DEFINITIONS
)


def _selector_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _definition_aliases(
    definition: TrajectoryMetricDefinition,
) -> tuple[str, ...]:
    return (
        definition.code,
        _selector_key(definition.name),
        definition.name.casefold(),
    )


_DEFINITIONS_BY_SELECTOR = {
    alias: definition
    for definition in TRAJECTORY_METRIC_DEFINITIONS
    for alias in _definition_aliases(definition)
}
_DEFINITIONS_BY_CODE = {
    definition.code: definition for definition in TRAJECTORY_METRIC_DEFINITIONS
}


def available_trajectory_metrics() -> list[dict[str, str]]:
    """Return API-safe metadata for all registered trajectory metrics."""
    return [definition.to_payload() for definition in TRAJECTORY_METRIC_DEFINITIONS]


def resolve_trajectory_metric_codes(
    selectors: Sequence[str] | None,
) -> tuple[str, ...]:
    """Resolve configured codes or display names to stable metric codes."""
    if not selectors:
        return ()

    if isinstance(selectors, str):
        selectors = (selectors,)

    normalized = [
        str(selector).strip() for selector in selectors if str(selector).strip()
    ]
    if not normalized:
        return ()
    if any(
        _selector_key(selector) == ALL_TRAJECTORY_METRICS for selector in normalized
    ):
        if len(normalized) != 1:
            raise ValueError("'all' must be the only configured trajectory metric")
        return TRAJECTORY_METRIC_CODES

    resolved: list[str] = []
    unknown: list[str] = []
    for selector in normalized:
        key = _selector_key(selector)
        definition = _DEFINITIONS_BY_SELECTOR.get(key)
        if definition is None:
            unknown.append(selector)
            continue
        if definition.code not in resolved:
            resolved.append(definition.code)

    if unknown:
        available = ", ".join(TRAJECTORY_METRIC_CODES)
        raise ValueError(
            f"Unknown trajectory metric(s): {', '.join(unknown)}. "
            f"Available metrics: {available}, or all"
        )
    return tuple(resolved)


def build_trajectory_metrics(
    selectors: Sequence[str] | None,
    *,
    judge: MetricJudge | None = None,
) -> tuple[TrajectoryContextMetric, ...]:
    """Instantiate only the configured metrics, in configured order."""
    return tuple(
        _DEFINITIONS_BY_CODE[code].implementation(judge=judge)
        for code in resolve_trajectory_metric_codes(selectors)
    )


def evaluate_trajectory_metrics_batched(
    context: TrajectoryContext,
    selectors: Sequence[str] | None,
    *,
    stateful_result: Mapping[str, Any] | Any | None = None,
    judge: MetricJudge | None = None,
    supplemental_context: Mapping[str, Any] | None = None,
) -> list[HighLevelMetricResult]:
    """Evaluate configured metrics without changing correctness state."""
    codes = resolve_trajectory_metric_codes(selectors)
    if not codes:
        return []
    metrics = build_trajectory_metrics(codes, judge=judge)
    results = evaluate_high_level_metrics_batched(
        context,
        stateful_result=stateful_result,
        metrics=metrics,
        judge=judge,
        supplemental_context=supplemental_context,
    )
    if len(results) != len(codes):
        raise RuntimeError(
            "Configured trajectory metric count changed during evaluation"
        )

    for code, result in zip(codes, results, strict=True):
        definition = _DEFINITIONS_BY_CODE[code]
        result.metadata["metric_code"] = code
        result.metadata["metric_layer"] = definition.layer
        result.metadata["metric_set"] = TRAJECTORY_METRIC_SET
        result.metadata["definition_version"] = TRAJECTORY_METRIC_SET
        result.metadata["affects_trajectory_score"] = False
    return results


__all__ = (
    "ALL_TRAJECTORY_METRICS",
    "CURRENT_TRAJECTORY_METRICS",
    "LEGACY_TRAJECTORY_METRICS",
    "PAPER_METRICS",
    "PAPER_V2_METRICS",
    "PAPER_V2_METRIC_SUITE",
    "TRAJECTORY_METRIC_CODES",
    "TRAJECTORY_METRIC_DEFINITIONS",
    "TRAJECTORY_METRIC_SET",
    "UPDATED_METRIC_NAMES",
    "CommunicationEfficiencyMetric",
    "ConfidenceCalibrationMetric",
    "ConstraintSatisfactionMetric",
    "ContextPreservationMetric",
    "CoordinationEfficiencyMetric",
    "DelegationAccuracyMetric",
    "DelegationAccuracyMetricV1",
    "DelegationOwnershipMetric",
    "GoalAlignmentMetric",
    "GoalAlignmentMetricV1",
    "GroundednessMetric",
    "HandoffQualityMetric",
    "HandoffQualityMetricV1",
    "InstructionFollowingMetric",
    "PolicySafetyMetric",
    "SemanticConsistencyMetric",
    "TaskCompletionMetric",
    "TrajectoryMetric",
    "TrajectoryMetricDefinition",
    "VerificationQualityMetric",
    "available_trajectory_metrics",
    "build_current_trajectory_metrics",
    "build_legacy_trajectory_metrics",
    "build_paper_metrics",
    "build_paper_v2_metrics",
    "build_trajectory_metrics",
    "build_updated_trajectory_metrics",
    "build_updated_paper_metrics",
    "evaluate_trajectory_metrics_batched",
    "resolve_trajectory_metric_codes",
)
