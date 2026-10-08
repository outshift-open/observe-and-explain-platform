#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json

from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
from stateful_evals_be.evaluation.trajectory_context import (
    CoordinationEvent,
    IntentEntry,
    TrajectoryContext,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.base import (
    metric_input_config,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
    trajectory_context_to_payload,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    build_context_payload,
    resolve_batch_evidence_refs,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.trajectory_metrics import (
    HandoffQualityMetric,
    VerificationQualityMetric,
)


def _raw_observe_span(
    *,
    span_id: str,
    kind: str,
    name: str,
    agent_id: str,
    role: str,
    input_payload: dict,
    output_payload: dict,
    parent_span_id: str = "",
    round_index: int | None = None,
    operation_kind: str = "",
    links: list[tuple[str, str]] | None = None,
) -> dict:
    attrs = {
        "ioa_observe.span.kind": kind,
        "ioa_observe.entity.name": name,
        "ioa_observe.entity.input": json.dumps(input_payload),
        "ioa_observe.entity.output": json.dumps(output_payload),
        "mas.agent.id": agent_id,
        "mas.agent.role": role,
    }
    if round_index is not None:
        attrs["mas.round"] = round_index
    if operation_kind:
        attrs["mas.operation.kind"] = operation_kind
    link_values = links or []
    return {
        "SpanId": span_id,
        "TraceId": "trace-1",
        "ParentSpanId": parent_span_id,
        "SpanName": name,
        "SpanAttributes": attrs,
        "StatusCode": "OK",
        "ServiceName": "test-mas",
        "Timestamp": f"2026-09-14T00:00:{len(span_id):02d}Z",
        "Links.SpanId": [item[0] for item in link_values],
        "Links.TraceId": ["trace-1" for _ in link_values],
        "Links.Attributes": [{"link.type": item[1]} for item in link_values],
    }


def _convert(raw_span: dict) -> dict:
    return TemporalMetricsProcessor._otel_trace_to_span_dict(raw_span)


def test_linked_peer_round_becomes_peer_context_and_revision() -> None:
    context = TrajectoryContext(policy_text="")
    round_one = []
    for index, agent_id in enumerate(("agent_1", "agent_2", "agent_3")):
        raw = _raw_observe_span(
            span_id=f"r1-{agent_id}",
            kind="llm",
            name="LLMCall",
            agent_id=agent_id,
            role="peer",
            input_payload={
                "messages": [
                    {
                        "role": "user",
                        "content": "Produce a grounded incident assessment.",
                    }
                ]
            },
            output_payload={"content": f"{agent_id} initial assessment"},
            round_index=1,
            operation_kind="round_response",
        )
        round_one.append(raw)
        context.ingest_span(_convert(raw), span_index=index)

    revised = _raw_observe_span(
        span_id="r2-agent_3",
        kind="llm",
        name="LLMCall",
        agent_id="agent_3",
        role="peer",
        input_payload={
            "messages": [
                {
                    "role": "user",
                    "content": "Produce a grounded incident assessment.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "round": 2,
                            "peer_answers": {
                                "agent_1": "Database latency is elevated.",
                                "agent_2": "Gateway errors are elevated.",
                            },
                        }
                    ),
                },
            ]
        },
        output_payload={"content": "Gateway errors are driving latency."},
        round_index=2,
        operation_kind="round_response",
        links=[
            ("r1-agent_1", "peer_message"),
            ("r1-agent_2", "peer_message"),
        ],
    )
    context.ingest_span(_convert(revised), span_index=3)

    peer_event = next(
        event
        for event in context.coordination_events
        if event.span_id == "r2-agent_3" and event.event_type == "peer_message"
    )
    assert peer_event.sender_agent_ids == ["agent_1", "agent_2"]
    assert peer_event.recipient_agent_ids == ["agent_3"]
    assert peer_event.linked_span_ids == ["r1-agent_1", "r1-agent_2"]
    assert peer_event.round_index == 2

    revised_claim = context.claims[-1]
    assert revised_claim.revision_of_claim_id == "claim:2"
    assert {"claim:0", "claim:1"}.issubset(set(revised_claim.evidence_refs))
    assert any(
        link.source_artifact_id == "claim:2"
        and link.target_artifact_id == "claim:3"
        and link.relation_type == "revised_by"
        for link in context.provenance_links
    )
    assert [
        fact.fact_type for fact in context.evidence if "peer_answers" in fact.content
    ] == ["agent_handoff"]
    assert [
        fact.content for fact in context.evidence if fact.fact_type == "user_statement"
    ] == ["Produce a grounded incident assessment."]


def test_native_observe_contract_tools_and_explicit_final_are_preserved() -> None:
    raw = _raw_observe_span(
        span_id="final-1",
        kind="coordination",
        name="final_response",
        agent_id="consensus",
        role="aggregator",
        input_payload={
            "messages": [
                {"role": "system", "content": "Verify peer evidence."},
                {"role": "user", "content": "Assess the incident."},
            ],
            "agent_contract": {
                "role": "reviewer",
                "objective": "accept supported claims",
            },
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "verify_claim",
                        "description": "Verify a claim.",
                    },
                }
            ],
        },
        output_payload={"content": "The supported final assessment."},
        operation_kind="synthesis",
    )
    raw["SpanAttributes"]["mas.response.final"] = True

    assert TemporalMetricsProcessor._extract_system_message([raw]) == (
        "Verify peer evidence."
    )
    contracts = TemporalMetricsProcessor._extract_agent_semantic_contracts([raw])
    assert any("accept supported claims" in content for _, content, _ in contracts)
    assert any(content == "Verify peer evidence." for _, content, _ in contracts)
    assert "verify_claim" in TemporalMetricsProcessor._extract_tool_definitions([raw])
    assert TemporalMetricsProcessor._extract_final_answer_from_raw_spans([raw]) == (
        "The supported final assessment.",
        0,
    )


def test_api_link_columns_reach_coordination_normalization() -> None:
    raw = TemporalMetricsProcessor._oxp_span_to_otel_format(
        {
            "span_id": "r2-agent",
            "trace_id": "trace-1",
            "span_name": "LLMCall",
            "span_attributes": {
                "ioa_observe.span.kind": "llm",
                "ioa_observe.entity.name": "LLMCall",
                "ioa_observe.entity.input": json.dumps(
                    {"messages": [{"role": "user", "content": "Review peers."}]}
                ),
                "ioa_observe.entity.output": json.dumps({"content": "Revised answer."}),
                "mas.agent.id": "agent_2",
                "mas.agent.role": "peer",
                "mas.round": 2,
            },
            "links_trace_id": ["trace-1"],
            "links_span_id": ["r1-agent"],
            "links_trace_state": [""],
            "links_attributes": [{"mas.link.type": "peer_message"}],
        }
    )
    context = TrajectoryContext(policy_text="")
    context.ingest_span(
        {
            "entity_type": "llm",
            "entity_name": "LLMCall",
            "agent_id": "agent_1",
            "agent_role": "peer",
            "span_id": "r1-agent",
            "trace_id": "trace-1",
            "input_payload": {"messages": [{"role": "user", "content": "Review."}]},
            "output_payload": {"content": "Initial answer."},
            "raw_span_data": {},
        },
        span_index=0,
    )
    context.ingest_span(_convert(raw), span_index=1)

    peer_event = next(
        event
        for event in context.coordination_events
        if event.event_type == "peer_message"
    )
    assert peer_event.linked_span_ids == ["r1-agent"]
    assert peer_event.sender_agent_ids == ["agent_1"]
    assert "claim:0" in peer_event.input_artifact_ids


def test_embedded_request_is_separated_from_environment_and_peer_guidance() -> None:
    context = TrajectoryContext(policy_text="You are a participating agent.")
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="peer-r1",
                kind="llm",
                name="LLMCall",
                agent_id="agent_1",
                role="analyst",
                input_payload={
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a participating agent.",
                        },
                        {
                            "role": "user",
                            "content": "Environment rules and available tools.",
                        },
                        {
                            "role": "user",
                            "content": (
                                "Objective and guidance from the lead agent.\n"
                                "Original user request: Diagnose checkout latency.\n"
                                "Begin!"
                            ),
                        },
                    ]
                },
                output_payload={"content": "Initial diagnosis."},
                round_index=1,
                operation_kind="round_response",
            )
        ),
        span_index=0,
    )

    assert [fact.fact_type for fact in context.evidence] == [
        "policy_rule",
        "user_statement",
        "environment_context",
        "agent_handoff",
    ]


def test_verifier_response_is_verification_but_assignment_to_verifier_is_not() -> None:
    context = TrajectoryContext(policy_text="Review the result.")
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="delegate-verifier",
                kind="tool",
                name="delegate_to_verifier",
                agent_id="lead",
                role="orchestrator",
                input_payload={"task": "Review the result."},
                output_payload={"status": "delivered"},
                operation_kind="assignment",
            )
        ),
        span_index=0,
    )
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="verifier-r2",
                kind="llm",
                name="LLMCall",
                agent_id="verifier",
                role="",
                input_payload={
                    "messages": [{"role": "user", "content": "Review the result."}]
                },
                output_payload={
                    "content": "The result is unsupported. VERIFICATION: REJECTED"
                },
                round_index=2,
                operation_kind="round_response",
            )
        ),
        span_index=1,
    )
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="run-action",
                kind="tool",
                name="run_action",
                agent_id="lead",
                role="orchestrator",
                input_payload={"action": "rollback"},
                output_payload={"status": "ok"},
            )
        ),
        span_index=2,
    )

    delegate_types = {
        event.event_type
        for event in context.coordination_events
        if event.span_id == "delegate-verifier"
    }
    verifier_types = {
        event.event_type
        for event in context.coordination_events
        if event.span_id == "verifier-r2"
    }
    assert "verification" not in delegate_types
    assert {"assignment", "handoff"}.issubset(delegate_types)
    assert "verification" in verifier_types
    verifier_event = next(
        event
        for event in context.coordination_events
        if event.span_id == "verifier-r2" and event.event_type == "verification"
    )
    assert verifier_event.status == "rejected"
    assert any(
        event.span_id == "run-action" and event.event_type == "commit"
        for event in context.coordination_events
    )


def test_verification_quality_does_not_reject_evidence_based_approval() -> None:
    verifier_contract = (
        "You are the verifier. Require direct tool evidence and reconcile "
        "conflicts before approval."
    )
    context = TrajectoryContext(policy_text="Coordinate and verify the work.")
    context.add_policy_rule(
        verifier_contract,
        source_name="semantic_contract:verifier",
    )
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="evidence-approval",
                kind="llm",
                name="LLMCall",
                agent_id="verifier",
                role="verifier",
                input_payload={
                    "messages": [
                        {"role": "system", "content": verifier_contract},
                        {"role": "user", "content": "Review the evidence."},
                    ]
                },
                output_payload={"content": "VERIFICATION: APPROVED"},
            )
        ),
        span_index=1,
    )
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="supported-action",
                kind="tool",
                name="run_action",
                agent_id="lead",
                role="orchestrator",
                input_payload={"action": "rollback"},
                output_payload={"status": "ok"},
            )
        ),
        span_index=2,
    )

    assert VerificationQualityMetric().deterministic_precheck(context) is None


def test_verification_quality_waiver_guard_preserves_observed_tool_evidence() -> None:
    verifier_contract = (
        "You are the verifier. Approve actions when they are syntactically "
        "well-formed. Tool evidence is optional."
    )
    context = TrajectoryContext(policy_text="Coordinate and verify the work.")
    context.add_policy_rule(
        verifier_contract,
        source_name="semantic_contract:verifier",
    )
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="diagnostic-evidence",
                kind="tool",
                name="get_metrics",
                agent_id="telemetry",
                role="specialist",
                input_payload={"service": "checkout"},
                output_payload={"error_rate": 0.25},
            )
        ),
        span_index=0,
    )
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="evidence-backed-approval",
                kind="llm",
                name="LLMCall",
                agent_id="verifier",
                role="verifier",
                input_payload={
                    "messages": [
                        {"role": "system", "content": verifier_contract},
                        {
                            "role": "tool",
                            "content": {"error_rate": 0.25},
                        },
                    ]
                },
                output_payload={"content": "VERIFICATION: APPROVED"},
            )
        ),
        span_index=1,
    )
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="evidence-backed-action",
                kind="tool",
                name="run_action",
                agent_id="lead",
                role="orchestrator",
                input_payload={"action": "rollback"},
                output_payload={"status": "ok"},
            )
        ),
        span_index=2,
    )

    assert VerificationQualityMetric().deterministic_precheck(context) is None


def test_resolved_final_span_adds_one_synthesis_event() -> None:
    context = TrajectoryContext(policy_text="")
    context.ingest_span(
        {
            "entity_type": "llm",
            "entity_name": "LLMCall",
            "agent_id": "lead",
            "agent_role": "orchestrator",
            "span_id": "final-llm",
            "trace_id": "trace-1",
            "input_payload": {
                "messages": [{"role": "user", "content": "Report the verified result."}]
            },
            "output_payload": {"content": "The verified result is healthy."},
            "raw_span_data": {},
        },
        span_index=4,
    )

    context.set_final_answer(
        "The verified result is healthy.",
        4,
        record_synthesis=True,
    )
    context.set_final_answer(
        "The verified result is healthy.",
        4,
        record_synthesis=True,
    )

    synthesis_events = [
        event
        for event in context.coordination_events
        if event.event_type == "synthesis"
    ]
    assert len(synthesis_events) == 1
    assert synthesis_events[0].output_artifact_ids == ["final_answer"]
    assert any(
        link.source_artifact_id == synthesis_events[0].event_id
        and link.target_artifact_id == "final_answer"
        for link in context.provenance_links
    )


def test_prior_tool_message_becomes_final_synthesis_provenance() -> None:
    context = TrajectoryContext(policy_text="")
    context.ingest_span(
        {
            "entity_type": "llm",
            "entity_name": "LLMCall",
            "agent_id": "lead",
            "agent_role": "orchestrator",
            "span_id": "plan",
            "trace_id": "trace-1",
            "input_payload": {
                "messages": [{"role": "user", "content": "Check latency."}]
            },
            "output_payload": {"content": "I will check metrics."},
            "raw_span_data": {},
        },
        span_index=0,
    )
    context.ingest_span(
        {
            "entity_type": "tool",
            "entity_name": "get_metrics",
            "agent_id": "telemetry",
            "span_id": "metrics",
            "trace_id": "trace-1",
            "input_payload": {"service": "checkout"},
            "output_payload": {"p99_ms": 180},
            "raw_span_data": {},
        },
        span_index=1,
    )
    context.ingest_span(
        {
            "entity_type": "llm",
            "entity_name": "LLMCall",
            "agent_id": "lead",
            "agent_role": "orchestrator",
            "span_id": "final",
            "trace_id": "trace-1",
            "input_payload": {
                "messages": [
                    {"role": "user", "content": "Check latency."},
                    {"role": "tool", "content": {"p99_ms": 180}},
                ]
            },
            "output_payload": {"content": "P99 latency is 180 ms."},
            "raw_span_data": {},
        },
        span_index=2,
    )
    context.set_final_answer(
        "P99 latency is 180 ms.",
        2,
        record_synthesis=True,
    )

    tool_fact_id = next(
        context._evidence_artifact_id(index, fact)
        for index, fact in enumerate(context.evidence)
        if fact.fact_type == "tool_output"
    )
    synthesis = next(
        event
        for event in context.coordination_events
        if event.event_type == "synthesis"
    )
    assert tool_fact_id in context.claims[-1].evidence_refs
    assert tool_fact_id in synthesis.input_artifact_ids


def test_escaped_tool_message_becomes_final_synthesis_provenance() -> None:
    context = TrajectoryContext(policy_text="")
    context.ingest_span(
        {
            "entity_type": "tool",
            "entity_name": "delegate_to_reviewer",
            "agent_id": "lead",
            "span_id": "review",
            "trace_id": "trace-1",
            "input_payload": {"task": "Review the proposed action."},
            "output_payload": {"value": "Evidence checked.\nVERIFICATION: APPROVED"},
            "raw_span_data": {},
        },
        span_index=0,
    )
    context.ingest_span(
        {
            "entity_type": "llm",
            "entity_name": "LLMCall",
            "agent_id": "lead",
            "span_id": "final",
            "trace_id": "trace-1",
            "input_payload": {
                "messages": [
                    {
                        "role": "tool",
                        "content": "Evidence checked.\nVERIFICATION: APPROVED",
                    }
                ]
            },
            "output_payload": {"content": "Proceed with the approved action."},
            "raw_span_data": {},
        },
        span_index=1,
    )
    context.set_final_answer(
        "Proceed with the approved action.",
        1,
        record_synthesis=True,
    )

    delegated_fact_id = next(
        context._evidence_artifact_id(index, fact)
        for index, fact in enumerate(context.evidence)
        if fact.source_name == "delegate_to_reviewer"
    )
    synthesis = next(
        event
        for event in context.coordination_events
        if event.event_type == "synthesis"
    )
    assert delegated_fact_id in context.claims[-1].evidence_refs
    assert delegated_fact_id in synthesis.input_artifact_ids


def test_metric_payload_receives_coordination_context_without_topology_rubric() -> None:
    context = TrajectoryContext(policy_text="Coordinate the requested work.")
    context.coordination_metadata["topology"] = "decentralized"
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="verify-1",
                kind="tool",
                name="verify_result",
                agent_id="reviewer",
                role="verifier",
                input_payload={"claim": "Latency is normal."},
                output_payload={"status": "rejected"},
                operation_kind="verification",
            )
        ),
        span_index=0,
    )

    payload = build_context_payload(
        context,
        metric_input_config("intents", "operations"),
        metric_name="Verification Quality",
    )

    assert payload["coordination_events"][0]["event_type"] == "verification"
    assert payload["coordination_events"][0]["status"] == "rejected"
    assert "work_ledger" in payload
    assert "provenance_links" in payload
    assert payload["coordination_metadata"]["topology"] == "decentralized"
    assert "topology" not in payload["input_config"]["components"]

    event_id = payload["coordination_events"][0]["artifact_id"]
    resolved = resolve_batch_evidence_refs(
        {"evidence_refs": [event_id]},
        payload,
    )
    assert resolved["evidence"] == [
        {
            "artifact_id": event_id,
            "span_index": 0,
            "source_name": "verify_result",
            "kind": "coordination",
            "content": payload["coordination_events"][0]["content"],
        }
    ]


def test_metric_payload_references_canonical_intent_event_content() -> None:
    context = TrajectoryContext(policy_text="Coordinate the requested work.")
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="tool-1",
                kind="tool",
                name="lookup",
                agent_id="worker",
                role="worker",
                input_payload={"query": "material detail"},
                output_payload={"result": "full canonical result"},
            )
        ),
        span_index=0,
    )
    context.intents.append(
        IntentEntry(
            name="Lookup material detail",
            source="agent_plan",
            first_seen=0,
            last_seen=0,
            status="fulfilled",
            events=[
                {
                    "type": "tool_attempt",
                    "span_index": 0,
                    "tool": "lookup",
                    "input": {"query": "material detail"},
                    "output": {"result": "full canonical result"},
                    "error": False,
                }
            ],
        )
    )

    payload = build_context_payload(
        context,
        metric_input_config("intents", "fact_store", "operations"),
        metric_name="Handoff Quality",
    )

    tool_events = [
        event
        for intent in payload["intents"]
        for event in intent["events"]
        if event.get("type") == "tool_attempt"
    ]
    assert tool_events
    assert "input" not in tool_events[0]
    assert "output" not in tool_events[0]
    assert tool_events[0]["canonical_content_components"] == [
        "operations",
        "fact_store",
    ]
    assert any(
        "full canonical result" in item["content"] for item in payload["fact_store"]
    )


def test_handoff_metric_applies_to_peer_messages() -> None:
    context = TrajectoryContext(policy_text="Coordinate the requested work.")
    context.coordination_events.append(
        CoordinationEvent(
            event_id="coordination:0",
            span_index=0,
            event_type="peer_message",
            operation_name="share_candidate",
            actor_agent_id="peer_a",
            recipient_agent_ids=["peer_b"],
            content="candidate",
        )
    )

    result = HandoffQualityMetric().applicability(context)

    assert result["status"] == "applicable"


def test_new_context_fields_round_trip_and_old_artifacts_remain_loadable(
    tmp_path,
) -> None:
    context = TrajectoryContext(policy_text="Coordinate work.")
    context.ingest_span(
        _convert(
            _raw_observe_span(
                span_id="synthesis-1",
                kind="coordination",
                name="final_response",
                agent_id="lead",
                role="orchestrator",
                input_payload={"candidate": "supported answer"},
                output_payload={"content": "supported answer"},
                operation_kind="synthesis",
            )
        ),
        span_index=0,
    )
    artifact = tmp_path / "trajectory_context.json"
    artifact.write_text(
        json.dumps(
            trajectory_context_to_payload(
                context,
                schema_version="trajectory-context.v2",
                session_id="session-1",
            )
        ),
        encoding="utf-8",
    )

    restored, _ = load_trajectory_context_artifact(artifact)
    assert restored.coordination_events[0].event_type == "synthesis"
    assert restored.coordination_events[0].span_id == "synthesis-1"
    assert restored._span_artifact_ids["synthesis-1"] == ["coordination:0"]

    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps(
            {
                "policy_text": "Legacy policy.",
                "evidence": [],
                "intents": [],
                "claims": [],
            }
        ),
        encoding="utf-8",
    )
    legacy_context, _ = load_trajectory_context_artifact(legacy)
    assert legacy_context.policy_text == "Legacy policy."
    assert legacy_context.coordination_events == []
    assert legacy_context.provenance_links == []
