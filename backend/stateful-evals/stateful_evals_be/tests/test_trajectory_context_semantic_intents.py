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


def test_external_request_creates_semantic_requirement_intents() -> None:
    context = TrajectoryContext(policy_text="")
    context.ingest_span(
        _llm_span(
            "You are a moderator coordinating a team of specialized agents.",
            (
                "Hello, I'm Alex. Plan me a 1-day trip in Celestia for July 4, "
                "2026, leaving from Luminos. Keep it affordable, include one "
                "indoor attraction and at least one outdoor attraction, and keep "
                "the total budget under 500 EUR. Don't care about dining options."
            ),
        ),
        span_index=0,
    )

    assert [intent.name for intent in context.intents] == [
        "Trip itinerary",
        "Budget ceiling",
        "Indoor attraction",
        "Outdoor attraction",
        "Dining preference",
    ]
    assert context.intents[0].description.startswith("Plan me a 1-day trip")
    assert context.intents[1].description == "Keep total cost under 500 EUR."
    assert all(
        intent.events[0]["type"] == "requirement_observed" for intent in context.intents
    )


def test_delegations_and_tools_link_to_requirements_without_becoming_intents() -> None:
    context = TrajectoryContext(policy_text="")
    context.ingest_span(
        _llm_span(
            "You are a moderator coordinating a team of specialized agents.",
            (
                "Plan a trip from Luminos to Celestia. Include one indoor "
                "attraction and at least one outdoor attraction under 500 EUR."
            ),
        ),
        span_index=0,
    )
    initial_count = len(context.intents)

    context.ingest_span(
        _llm_span(
            "You have tools to look up schedules and attractions inside cities.",
            (
                "Find an indoor attraction and an outdoor attraction in Celestia "
                "for the proposed trip."
            ),
            "I found a museum and a park for the delegated task.",
        ),
        span_index=1,
    )
    context.ingest_span(
        {
            "entity_type": "tool",
            "entity_name": "get_attractions",
            "input_payload": {"city": "Celestia"},
            "output_payload": {
                "status": "ok",
                "attractions": ["Museum of Celestial Arts", "Nova Park"],
            },
        },
        span_index=2,
    )

    assert len(context.intents) == initial_count
    assert "get_attractions" not in {intent.name for intent in context.intents}
    assert any(claim.claim_type == "peer_agent_assertion" for claim in context.claims)
    assert [fact.fact_type for fact in context.evidence] == [
        "user_statement",
        "agent_handoff",
        "tool_output",
    ]
    indoor = next(
        intent for intent in context.intents if intent.name == "Indoor attraction"
    )
    outdoor = next(
        intent for intent in context.intents if intent.name == "Outdoor attraction"
    )
    assert [event["type"] for event in indoor.events] == [
        "requirement_observed",
        "delegated_task",
        "tool_attempt",
    ]
    assert outdoor.status == "in_progress"
    assert outdoor.events[-1]["tool"] == "get_attractions"


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


def test_intent_retrieval_includes_semantic_description() -> None:
    context = TrajectoryContext(policy_text="")
    context.ingest_span(
        _llm_span(
            "You are a moderator coordinating a team.",
            "Plan a trip from Luminos to Celestia under 500 EUR.",
        ),
        span_index=0,
    )

    intent_context = context.retrieve_for_intent_recognition({})

    assert (
        "Trip itinerary: Plan a trip from Luminos to Celestia under 500 EUR."
        in intent_context
    )
    assert "Budget ceiling: Keep total cost under 500 EUR." in intent_context


def test_final_root_answer_resolves_semantic_requirements() -> None:
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
    assert all(intent.status == "pending" for intent in context.intents)

    context.ingest_span(
        _llm_span(
            "You are a moderator coordinating a team.",
            request,
            (
                "Here is your complete Celestia trip from Luminos. The route "
                "and schedule cost 120 EUR, with an indoor museum and an "
                "outdoor park included. This complete itinerary remains under "
                "your 500 EUR budget and includes the requested activities."
            ),
        ),
        span_index=9,
    )

    assert all(intent.status == "fulfilled" for intent in context.intents)
    assert all(
        intent.events[-1]["type"] == "final_answer_alignment"
        for intent in context.intents
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
