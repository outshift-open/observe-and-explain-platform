#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Metric inputs come from recorded state, and judges decide what text means."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from stateful_evals_be.evaluation.trajectory_context import (
    EvidenceFact,
    IntentEntry,
    TrajectoryContext,
    WorkUnit,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
    trajectory_context_to_payload,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    JudgeUsage,
    build_operation_context,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.trajectory_metrics import (
    GoalAlignmentMetric,
    TaskCompletionMetric,
    VerificationQualityMetric,
    evaluate_trajectory_metrics_batched,
)


class _NoJudge:
    last_usage = JudgeUsage()


class _NotApplicableBatchJudge:
    """Returns ``applicable: false`` for every metric in the batch."""

    last_usage = JudgeUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    def judge_batch(
        self,
        *,
        metrics_payload: Sequence[Mapping[str, Any]],
        shared_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return {
            "metrics": [
                {
                    "high_level_metric": item["high_level_metric"],
                    "applicable": False,
                    "score": 1,
                    "reasoning": "No checking duty, review step, or synthesis.",
                    "evidence_refs": [],
                    "fatal_failures": [],
                    "minor_failures": [],
                }
                for item in metrics_payload
            ]
        }

    def judge(self, **_: Any) -> Mapping[str, Any]:
        raise AssertionError("the batch path should be used")


def _tool_fact(
    span_index: int,
    *,
    tool: str,
    agent_id: str,
    span_id: str,
    parent_span_id: str,
    outcome: str,
    started_at_ns: int | None = None,
    duration_ns: int | None = None,
) -> EvidenceFact:
    return EvidenceFact(
        span_index=span_index,
        fact_type="tool_output",
        source_name=tool,
        agent_id=agent_id,
        actor_scope="peer",
        span_id=span_id,
        parent_span_id=parent_span_id,
        outcome=outcome,
        started_at_ns=started_at_ns,
        duration_ns=duration_ns,
        content=(
            f"[Tool: {tool}]\n"
            '  Called with: {"service": "payments"}\n'
            '  Returned: {"rows": []}'
        ),
    )


def test_tool_facts_record_span_start_and_duration(tmp_path: Path) -> None:
    context = TrajectoryContext("")
    context.ingest_span(
        {
            "entity_type": "tool",
            "span_id": "t1",
            "entity_name": "get_metrics",
            "agent_id": "telemetry",
            "input_payload": {"service": "payments"},
            "output_payload": {"p99_ms": 1200},
            "timestamp": "2026-07-22T20:18:47.086175Z",
            "raw_span_data": {"Duration": 52_448_034},
        },
        0,
    )
    fact = next(item for item in context.evidence if item.fact_type == "tool_output")

    assert fact.started_at_ns == 1_784_751_527_086_175_000
    assert fact.duration_ns == 52_448_034

    path = tmp_path / "trajectory_context.json"
    path.write_text(
        json.dumps(
            trajectory_context_to_payload(context, schema_version="t", session_id="s")
        )
    )
    restored, _ = load_trajectory_context_artifact(path)
    restored_fact = next(
        item for item in restored.evidence if item.fact_type == "tool_output"
    )
    assert (restored_fact.started_at_ns, restored_fact.duration_ns) == (
        fact.started_at_ns,
        fact.duration_ns,
    )


def test_repeated_calls_carry_previous_outcome_timing_and_parent() -> None:
    second = 1_000_000_000
    context = TrajectoryContext("")
    context.evidence.extend(
        [
            _tool_fact(
                1,
                tool="query_db",
                agent_id="db",
                span_id="c1",
                parent_span_id="db-exec",
                outcome="error",
                started_at_ns=10 * second,
                duration_ns=2 * second,
            ),
            _tool_fact(
                2,
                tool="query_db",
                agent_id="db",
                span_id="c2",
                parent_span_id="db-exec",
                outcome="output",
                started_at_ns=13 * second,
                duration_ns=second,
            ),
            _tool_fact(
                3,
                tool="query_db",
                agent_id="db",
                span_id="c3",
                parent_span_id="c2",
                outcome="output",
            ),
        ]
    )

    _, summary = build_operation_context(context)
    [group] = summary["exact_repeated_call_groups"]

    assert (group["agent_id"], group["entity_name"], group["count"]) == (
        "db",
        "query_db",
        3,
    )
    first, retry, nested = group["calls"]
    assert first["outcome"] == "error"
    assert "previous_call_outcome" not in first
    assert first["started_at"] == "1970-01-01T00:00:10.000000Z"
    assert first["ended_at"] == "1970-01-01T00:00:12.000000Z"
    assert retry["previous_call_outcome"] == "error"
    assert retry["relation_to_previous_call"] == "same_parent_span"
    assert nested["relation_to_previous_call"] == "child_of_previous_call"
    assert nested["started_at"] == ""


def test_a_delegation_is_recognised_from_state_not_tool_name() -> None:
    context = TrajectoryContext("")
    context.evidence.extend(
        [
            EvidenceFact(
                span_index=1,
                fact_type="tool_output",
                source_name="handoff_notes",
                agent_id="lead",
                actor_scope="root",
                content='[Tool: handoff_notes]\n  Called with: {"note": "x"}',
            ),
            EvidenceFact(
                span_index=2,
                fact_type="tool_output",
                source_name="ask_specialist",
                agent_id="lead",
                actor_scope="root",
                content='[Tool: ask_specialist]\n  Called with: {"task": "y"}',
            ),
        ]
    )
    context.work_units.append(
        WorkUnit(
            work_id="work:0",
            allocator_agent_id="lead",
            recipient_agent_ids=["specialist"],
            request_span_index=2,
            outcome="completed",
        )
    )

    operations, _ = build_operation_context(context)
    by_span = {item["span_index"]: item for item in operations}

    assert by_span[1]["is_delegation"] is False
    assert by_span[2]["is_delegation"] is True
    assert by_span[2]["recipient_agent_id"] == "specialist"
    assert by_span[2]["work_outcome"] == "completed"


def test_verification_quality_applicability_is_decided_by_the_judge() -> None:
    context = TrajectoryContext("Plan the trip and use the schedule to check it.")
    context.work_units.append(
        WorkUnit(
            work_id="work:0",
            allocator_agent_id="lead",
            recipient_agent_ids=["schedule_agent"],
            request_span_index=1,
        )
    )
    metric = VerificationQualityMetric()

    assert metric.applicability(context)["status"] == "applicable"

    not_applicable = metric.result_from_raw(
        {"applicable": False, "score": 1, "reasoning": "No checking duty."},
        judge=_NoJudge(),
    )
    assert not_applicable.status == "not_applicable"
    assert not_applicable.score is None
    assert not_applicable.metadata["applicability"]["decided_by"] == "judge"
    decorated = metric.decorate_result(not_applicable, context)
    assert decorated.status == "not_applicable"

    applicable = metric.result_from_raw(
        {
            "applicable": True,
            "score": 0,
            "reasoning": "The plan was not checked.",
            "fatal_failures": [
                {"span_index": 3, "reasoning": "Unchecked infeasible plan."}
            ],
        },
        judge=_NoJudge(),
    )
    assert applicable.status == "fail"

    other = TaskCompletionMetric().result_from_raw(
        {"applicable": False, "score": 1, "reasoning": "Done."},
        judge=_NoJudge(),
    )
    assert other.status == "pass"


def test_batched_judge_can_mark_verification_quality_not_applicable() -> None:
    context = TrajectoryContext("Answer the question.")
    context.latest_root_answer = "Here is the answer."
    context.latest_root_answer_span_index = 0

    results = evaluate_trajectory_metrics_batched(
        context,
        ["verification_quality", "task_completion"],
        judge=_NotApplicableBatchJudge(),
    )
    by_code = {result.metadata["metric_code"]: result for result in results}

    assert by_code["verification_quality"].status == "not_applicable"
    assert by_code["task_completion"].status == "pass"


def test_goal_alignment_payload_omits_outcomes() -> None:
    context = TrajectoryContext("Plan a trip within budget.")
    context.evidence.append(
        EvidenceFact(
            span_index=2,
            fact_type="tool_output",
            source_name="delegate_to_schedule_agent",
            agent_id="lead",
            actor_scope="root",
            content=(
                "[Tool: delegate_to_schedule_agent]\n"
                '  Called with: {"task": "Find trains."}\n'
                '  Returned: {"result": "queue full"}'
            ),
            outcome="error",
        )
    )
    context.work_units.append(
        WorkUnit(
            work_id="work:0",
            allocator_agent_id="lead",
            recipient_agent_ids=["schedule_agent"],
            request_span_index=2,
            outcome="failed",
        )
    )
    context.intents.append(
        IntentEntry(
            name="find_trains",
            source="user",
            first_seen=0,
            last_seen=2,
            status="dropped",
            description="Find trains for the trip.",
            events=[{"type": "work_outcome", "outcome": "failed", "span_index": 2}],
        )
    )

    payload = GoalAlignmentMetric().to_judge_payload(context)["context"]

    assert payload["delegation_requests"] == [
        {
            "delegation_id": "delegation:2",
            "operation_artifact_id": "operation:2",
            "span_index": 2,
            "delegator_agent_id": "lead",
            "recipient_agent": "schedule_agent",
            "delegated_task": "Find trains.",
        }
    ]
    [intent] = payload["intents"]
    assert "status" not in intent and "events" not in intent
    assert intent["description"] == "Find trains for the trip."
    serialized = json.dumps(payload)
    assert "queue full" not in serialized
    assert "delegation_audit" not in payload
