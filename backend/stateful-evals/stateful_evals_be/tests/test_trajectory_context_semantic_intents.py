#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext


def _llm_span(
    system_text: str,
    user_text: str,
    assistant_text: str = "",
) -> dict:
    return {
        "entity_type": "llm",
        "entity_name": "LLMCall",
        "input_payload": {
            "gen_ai.prompt.0.role": "system",
            "gen_ai.prompt.0.content": system_text,
            "gen_ai.prompt.1.role": "user",
            "gen_ai.prompt.1.content": user_text,
        },
        "output_payload": (
            {"gen_ai.completion.0.content": assistant_text} if assistant_text else {}
        ),
    }


def test_ingestion_retains_recorded_agent_and_span_provenance() -> None:
    context = TrajectoryContext(policy_text="You are the root orchestrator.")
    root_span = _llm_span(
        "You are the root orchestrator.",
        "Investigate the payment incident.",
        "I will delegate telemetry analysis.",
    )
    root_span.update(
        {
            "app_name": "sre",
            "span_id": "root-span",
            "parent_span_id": "root-turn",
            "trace_id": "trace-1",
            "raw_span_data": {
                "ServiceName": "sre",
                "SpanAttributes": {"mas.agent.id": "sre"},
            },
        }
    )
    peer_span = _llm_span(
        "You are the telemetry specialist.",
        "Delegated task: inspect payment-service metrics and report findings.",
        "I will call get_metrics.",
    )
    peer_span.update(
        {
            "app_name": "telemetry",
            "span_id": "peer-span",
            "parent_span_id": "telemetry-turn",
            "trace_id": "trace-1",
            "raw_span_data": {
                "ServiceName": "telemetry",
                "SpanAttributes": {"mas.agent.id": "telemetry"},
            },
        }
    )

    context.ingest_span(root_span, span_index=0)
    context.ingest_span(peer_span, span_index=1)

    assert context.claims[0].agent_id == "sre"
    assert context.claims[0].actor_scope == "root"
    assert context.claims[0].span_id == "root-span"
    assert context.claims[1].agent_id == "telemetry"
    assert context.claims[1].actor_scope == "peer"
    assert context.claims[1].parent_span_id == "telemetry-turn"
    assert context.claims[1].trace_id == "trace-1"


def test_tool_outputs_are_persisted_without_truncation() -> None:
    context = TrajectoryContext(policy_text="")
    full_output = {
        "attractions": [
            {"name": f"Attraction {index}", "description": "detail " * 40}
            for index in range(20)
        ],
        "last_entry": {
            "name": "Azure Lake Promenade",
            "accessibility": "Wheelchair accessible.",
        },
    }

    context.ingest_span(
        {
            "entity_type": "tool",
            "entity_name": "get_attractions_description",
            "input_payload": {"city": "Celestia"},
            "output_payload": full_output,
        },
        span_index=0,
    )

    fact = context.evidence[0]
    claim = context.claims[0]
    assert "Azure Lake Promenade" in fact.content
    assert "Wheelchair accessible." in fact.content
    assert "Azure Lake Promenade" in claim.content
    assert not fact.content.endswith("...")


def test_final_root_answer_does_not_resolve_semantic_requirements() -> None:
    context = TrajectoryContext(policy_text="")
    request = (
        "Plan a trip from Luminos to Celestia under 500 EUR. Include one "
        "indoor attraction and one outdoor attraction. Don't care about "
        "dining options."
    )
    context.ingest_span(
        _llm_span(
            "You are a moderator coordinating a team.",
            request,
            "I will start by asking the itinerary agent for routes and schedules.",
        ),
        span_index=0,
    )
    assert all(intent.status == "unassessed" for intent in context.intents)

    final_answer = (
        "Here is your complete Celestia trip from Luminos. The route and "
        "schedule cost 820 EUR, which is above your 500 EUR budget, with an "
        "indoor museum and an outdoor park included."
    )
    context.ingest_span(
        _llm_span("You are a moderator coordinating a team.", request, final_answer),
        span_index=9,
    )
    context.set_final_answer(final_answer, 9)

    (user_request,) = [i for i in context.intents if i.source == "user"]
    assert user_request.description == request
    assert user_request.status == "unassessed"
    assert all(intent.status == "unassessed" for intent in context.intents)
    assert not any(
        event["type"] == "final_answer_alignment"
        for intent in context.intents
        for event in intent.events
    )


def test_root_policy_identifies_non_moderator_orchestrator() -> None:
    policy = """\
    You are an expert SRE leading incident triage.
    Delegate investigations to telemetry, backend, and database specialists.
    """
    context = TrajectoryContext(policy_text=policy)
    final_answer = (
        "Incident triage is complete. The payment-service rollback was initiated "
        "after reviewing telemetry, backend, and database findings. Continue "
        "monitoring latency and error rates during recovery."
    )

    context.ingest_span(
        _llm_span(
            "You are an expert SRE leading incident triage.\n"
            "Delegate investigations to telemetry, backend, and database specialists.",
            "Triage the critical payment-service latency incident.",
            final_answer,
        ),
        span_index=0,
    )

    assert any(fact.fact_type == "user_statement" for fact in context.evidence)
    assert context.claims[-1].claim_type == "assertion"
    assert context.get_final_answer_context()["final_answer"] == final_answer
    assert context.get_final_answer_context()["final_answer_span_index"] == 0


def test_non_root_policy_remains_a_delegated_agent() -> None:
    root_policy = "You are an expert SRE leading incident triage."
    context = TrajectoryContext(policy_text=root_policy)
    context.ingest_span(
        _llm_span(
            root_policy,
            "Triage the payment-service incident.",
            "I will ask telemetry to investigate the latency spike.",
        ),
        span_index=0,
    )
    context.ingest_span(
        _llm_span(
            "You are a telemetry analyst specializing in observability data.",
            "Analyze payment-service latency and error rates.",
            "Telemetry shows elevated latency and gateway timeouts.",
        ),
        span_index=1,
    )

    assert context.claims[-1].claim_type == "peer_agent_assertion"
    assert context.evidence[-1].fact_type == "agent_handoff"
    assert context.get_final_answer_context()["final_answer_span_index"] == 0
