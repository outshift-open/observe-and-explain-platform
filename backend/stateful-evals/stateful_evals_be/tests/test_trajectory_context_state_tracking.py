#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Agent, work-unit, flag and boundary state tracked by TrajectoryContext."""

import json
from pathlib import Path

from stateful_evals_be.evaluation.coordination import CoordinationContext
from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
from stateful_evals_be.evaluation.span_normalization import SpanNormalizer
from stateful_evals_be.evaluation.trajectory_context import (
    TrajectoryContext,
    _classify_work_response,
    _timestamp_ns,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    build_context_payload,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.base import (
    MetricInputConfig,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
    trajectory_context_to_payload,
)


def _llm(span_id, agent_id, *, user="", output="", tool_calls=None, system=""):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if user:
        messages.append({"role": "user", "content": user})
    output_payload = {"content": output}
    if tool_calls:
        output_payload["tool_calls"] = [
            {"id": f"call-{name}", "function": {"name": name, "arguments": "{}"}}
            for name in tool_calls
        ]
    return {
        "entity_type": "llm",
        "span_id": span_id,
        "entity_name": "model",
        "agent_id": agent_id,
        "input_payload": {"messages": messages},
        "output_payload": output_payload,
    }


def _router(span_id, value):
    return {
        "entity_type": "other",
        "span_id": span_id,
        "entity_name": "RunnableCallable",
        "input_payload": {},
        "output_payload": {"outputs": value},
    }


def _roster_context(*agents):
    context = TrajectoryContext("")
    context.declare_roster([(agent, index) for index, agent in enumerate(agents)])
    return context


def test_agent_identity_reads_generic_attribute_and_inherits_from_ancestor():
    agent_span = {
        "SpanId": "a1",
        "SpanName": "schedule_agent.agent",
        "SpanAttributes": {"agent_id": "schedule_agent"},
    }
    tool_span = {
        "SpanId": "t1",
        "ParentSpanId": "a1",
        "SpanName": "read_document.tool",
        "SpanAttributes": {},
    }
    method_span = {
        "SpanId": "m1",
        "SpanName": "RunnableSequence.task",
        "SpanAttributes": {"agent_id": "moderator-agent.invoke"},
    }
    explicit = {
        "SpanId": "x1",
        "SpanAttributes": {"mas.agent.id": "planner", "agent_id": "other"},
    }
    by_id = {span["SpanId"]: span for span in (agent_span, tool_span, method_span)}

    assert SpanNormalizer.resolve_agent_id(agent_span) == "schedule_agent"
    assert SpanNormalizer.resolve_agent_id(tool_span, by_id) == "schedule_agent"
    assert SpanNormalizer.resolve_agent_id(method_span) == ""
    assert SpanNormalizer.resolve_agent_id(explicit) == "planner"


def test_otel_genai_semconv_messages_are_read_and_not_deduplicated():
    def semconv_span(span_id, answer):
        return {
            "SpanId": span_id,
            "SpanName": "ChatOpenAI.chat",
            "Timestamp": "2026-09-04 16:00:41.521212000",
            "SpanAttributes": {
                "agent_id": "moderator",
                "gen_ai.input.messages": json.dumps(
                    [{"role": "user", "parts": [{"type": "text", "content": "Q?"}]}]
                ),
                "gen_ai.output.messages": json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": answer}],
                        }
                    ]
                ),
            },
        }

    spans = [semconv_span("s1", "First"), semconv_span("s2", "Second")]
    unique = SpanNormalizer.deduplicate_spans(spans)
    normalized = SpanNormalizer.normalize_span(unique[0])

    assert [span["SpanId"] for span in unique] == ["s1", "s2"]
    assert normalized["agent_id"] == "moderator"
    assert normalized["input_payload"]["messages"][0]["content"] == "Q?"


def test_dedup_keeps_distinct_empty_spans_and_distinct_calls():
    empty_a = {"SpanId": "e1", "SpanName": "agent_start_event", "SpanAttributes": {}}
    empty_b = {"SpanId": "e2", "SpanName": "agent_start_event", "SpanAttributes": {}}
    retry_a = {
        "SpanId": "r1",
        "SpanName": "delegate_to_x.tool",
        "SpanAttributes": {"mas.call.id": "c1", "traceloop.entity.output": "failed"},
    }
    retry_b = {
        "SpanId": "r2",
        "SpanName": "delegate_to_x.tool",
        "SpanAttributes": {"mas.call.id": "c2", "traceloop.entity.output": "failed"},
    }

    unique = SpanNormalizer.deduplicate_spans(
        [empty_a, empty_b, dict(empty_a), retry_a, retry_b, dict(retry_a)]
    )

    assert [span["SpanId"] for span in unique] == ["e1", "e2", "r1", "r2"]


def test_incremental_adapter_ingestion_has_no_look_ahead_and_keeps_native_index():
    coordination = CoordinationContext.from_payload(
        {
            "edges": [
                {
                    "edge_id": "delegation-1:c1",
                    "call_id": "c1",
                    "sender": "moderator",
                    "receiver": "schedule_agent",
                    "dispatcher": "moderator",
                    "request": "Find schedules",
                    "response": "[delegation] agent 'schedule_agent' failed: busy",
                    "start_event_index": 240,
                    "end_event_index": 264,
                    "source_span_ids": ["s2"],
                }
            ],
            "final_response": "Here is the plan.",
            "final_response_event_index": 592,
        }
    )
    context = TrajectoryContext(
        "",
        coordination_context=coordination,
        adapter_ingestion="incremental",
    )

    assert context.coordination_events == []
    assert context.latest_root_answer == ""

    context.ingest_span(_llm("s1", "moderator", user="Plan it", output="Delegating"), 0)
    context.ingest_span(
        {
            "entity_type": "tool",
            "span_id": "s2",
            "entity_name": "delegate_to_schedule_agent",
            "agent_id": "moderator",
            "input_payload": {"task": "Find schedules"},
            "output_payload": {
                "value": "[delegation] agent 'schedule_agent' failed: busy"
            },
        },
        1,
    )
    context.finalize_state()

    assignment = next(
        event
        for event in context.coordination_events
        if event.event_type == "assignment"
    )
    assert assignment.span_index == 1
    assert assignment.source_event_index == 240
    assert assignment.outcome == "failed"
    unit = context.work_units[0]
    assert (unit.allocator_agent_id, unit.recipient_agent_ids) == (
        "moderator",
        ["schedule_agent"],
    )
    assert unit.outcome == "failed"
    assert context.evidence[-1].relayed_from_agent_id == "schedule_agent"
    assert context.evidence[-1].outcome == "error"


def test_router_output_opens_unit_records_receipt_and_handback_resolves_it():
    context = _roster_context("moderator", "schedule_agent")
    context.ingest_span(
        _llm("m1", "moderator", user="Trains?", output="Ask schedule"), 0
    )
    context.ingest_span(_router("r1", "schedule_agent"), 1)
    context.ingest_span(
        _llm("a1", "schedule_agent", user="Find trains", output="CV103 at 08:30"), 2
    )
    context.ingest_span(_router("r2", "moderator"), 3)
    context.ingest_span(_router("r3", "end"), 4)

    assert len(context.work_units) == 1
    unit = context.work_units[0]
    assert unit.source == "route"
    assert unit.request == "Ask schedule"
    assert unit.receipt_span_indices == [2]
    assert unit.outcome == "completed"
    assert context.claims[-1].work_id == unit.work_id
    assert context.termination_span_index == 4
    assert [event.event_type for event in context.coordination_events] == ["assignment"]


def test_state_routing_field_on_a_recipient_node_is_not_a_handback():
    context = _roster_context("moderator", "schedule_agent")
    context.ingest_span(
        _llm("m1", "moderator", user="Trains?", output="Ask schedule"), 0
    )
    context.ingest_span(_router("r1", "schedule_agent"), 1)
    context.ingest_span(
        {
            "entity_type": "agent",
            "span_id": "n1",
            "entity_name": "schedule_agent",
            "agent_id": "schedule_agent",
            "output_payload": {"next_agent": "moderator", "messages": []},
        },
        2,
    )

    assert context.work_units[0].outcome == "pending"
    assert len(context.work_units) == 1


def test_message_addressed_to_an_agent_is_an_assignment_not_a_final_answer():
    context = _roster_context("moderator", "web_surfer")
    message = {
        "type": "RequestToSpeak",
        "target": "web_surfer",
        "message": "What time is it in Paris?",
    }
    context.ingest_span(
        _llm("m1", "moderator", user="time in paris?", output=json.dumps(message)), 0
    )

    unit = context.work_units[0]
    assert (unit.source, unit.recipient_agent_ids) == ("message", ["web_surfer"])
    assert unit.request == "What time is it in Paris?"
    assert context.latest_root_answer == ""


def test_tool_without_agent_is_attributed_to_requester_and_errors_are_outcomes():
    context = _roster_context("concierge_agent")
    context.ingest_span(
        _llm("l1", "concierge_agent", user="Price it", tool_calls=["get_fares"]), 0
    )
    context.ingest_span(
        {
            "entity_type": "tool",
            "span_id": "t1",
            "entity_name": "get_fares",
            "input_payload": {"route": "LC"},
            "output_payload": {"error": "Route 'LC' not found"},
        },
        1,
    )

    fact = context.evidence[-1]
    assert fact.agent_id == "concierge_agent"
    assert fact.outcome == "error"
    assert context.agents["concierge_agent"].observed_tools == ["get_fares"]


def test_reply_classification_and_flags():
    assert _classify_work_response("Could you please provide the route IDs?")[0] == (
        "needs_input"
    )
    assert (
        _classify_work_response("I will wait for the schedule agent.")[0] == "waiting"
    )
    assert _classify_work_response("I cannot find any direct flights.")[0] == (
        "completed"
    )
    assert _classify_work_response("")[0] == "no_response"

    context = _roster_context("moderator", "concierge_agent")
    context.ingest_span(
        _llm("m1", "moderator", user="Budget?", output="Ask concierge"), 0
    )
    context.ingest_span(_router("r1", "concierge_agent"), 1)
    context.ingest_span(
        _llm(
            "c1",
            "concierge_agent",
            user="Price routes",
            output="I don't have access to route IDs. Please provide them.",
        ),
        2,
    )
    context.ingest_span(_llm("m2", "moderator", output="Final plan without fares."), 3)

    assert context.work_units[0].outcome == "needs_input"
    assert {flag.kind for flag in context.flags} >= {"needs_input", "cannot_do"}
    assert all(flag.work_id == "work:0" for flag in context.flags)


def test_retry_after_failure_is_chained():
    context = _roster_context("moderator", "schedule_agent")
    for attempt, call in enumerate(("c1", "c2")):
        context.ingest_span(
            {
                "entity_type": "tool",
                "span_id": f"d{attempt}",
                "entity_name": "delegate_to_schedule_agent",
                "agent_id": "moderator",
                "attributes": {"mas.call.id": call},
                "input_payload": {"task": "Find schedules"},
                "output_payload": {"value": "[delegation] agent 'x' failed: busy"},
            },
            2 * attempt,
        )
        context.ingest_span(
            _llm(f"m{attempt}", "moderator", output="Retrying."), 2 * attempt + 1
        )

    first, second = context.work_units
    assert first.outcome == second.outcome == "failed"
    assert (first.response_span_index, first.outcome_span_index) == (0, 1)
    assert second.retry_of_work_id == first.work_id
    assert second.attempt_index == 2


def test_delegation_reply_resolves_after_the_recipient_runs():
    context = _roster_context("moderator", "schedule_agent")
    reply = "Please provide the preferred departure station."
    context.ingest_span(
        _llm(
            "m0", "moderator", user="Trains?", tool_calls=["delegate_to_schedule_agent"]
        ),
        0,
    )
    context.ingest_span(
        {
            "entity_type": "tool",
            "span_id": "d0",
            "entity_name": "delegate_to_schedule_agent",
            "agent_id": "moderator",
            "input_payload": {"task": "Find Friday trains to Lyon."},
            "output_payload": {"content": reply},
        },
        1,
    )
    unit = context.work_units[0]
    assert unit.outcome == "pending"

    context.ingest_span(
        _llm("s0", "schedule_agent", user="Find Friday trains to Lyon.", output=reply),
        2,
    )
    assert unit.receipt_span_indices == [2]
    assert context.claims[-1].work_id == unit.work_id
    assert unit.outcome == "pending"

    context.ingest_span(_llm("m1", "moderator", output="Which station?"), 3)
    assert unit.outcome == "needs_input"
    assert (unit.response_span_index, unit.outcome_span_index) == (1, 3)
    assert [(flag.kind, flag.agent_id, flag.work_id) for flag in context.flags] == [
        ("needs_input", "schedule_agent", unit.work_id)
    ]


def test_repeated_non_system_header_is_a_contract_not_a_user_request():
    header = (
        "You are the moderator coordinating a team of specialized agents. "
        "Available agents: - schedule_agent: finds train schedules and attractions "
        "- concierge_agent: looks up fares and computes total costs."
    )
    question = "What trains go from Celestia to Verdantia?"

    def raw(span_id):
        return {
            "SpanId": span_id,
            "SpanName": "ChatOpenAI.chat",
            "SpanAttributes": {
                "agent_id": "moderator",
                "gen_ai.prompt.0.role": "user",
                "gen_ai.prompt.0.content": f"{header}\nUser: {question}",
            },
        }

    contracts = SpanNormalizer.extract_agent_semantic_contracts(
        [raw("s1"), raw("s2")], root_request=question
    )
    assert contracts == [("moderator", " ".join(header.split()), 0)]

    context = _roster_context("moderator", "schedule_agent", "concierge_agent")
    context.add_policy_rule(contracts[0][1], source_name="semantic_contract:moderator")
    context.ingest_span(
        _llm("m1", "moderator", user=f"{header}\nUser: {question}", output="Routing."),
        0,
    )

    statements = [
        fact for fact in context.evidence if fact.fact_type == "user_statement"
    ]
    assert [fact.content for fact in statements] == [f"User: {question}"]
    assert context.agents["moderator"].contract_ids == ["semantic_contract:moderator"]
    assert context.agents["schedule_agent"].declared_capability.startswith(
        "finds train schedules"
    )


def test_tool_call_only_root_output_is_not_a_final_answer():
    context = TrajectoryContext("")
    context.ingest_span(
        _llm(
            "m1",
            "moderator",
            user="Plan a weekend trip to Lisbon with a budget of $500.",
            tool_calls=["delegate_to_itinerary_agent"],
        ),
        0,
    )

    assert context.latest_root_answer == ""
    assert all(intent.status != "fulfilled" for intent in context.intents)


def test_new_state_round_trips_through_the_artifact(tmp_path: Path):
    context = _roster_context("moderator", "schedule_agent")
    context.ingest_span(
        _llm("m1", "moderator", user="Trains?", output="Ask schedule"), 0
    )
    context.ingest_span(_router("r1", "schedule_agent"), 1)
    context.ingest_span(_llm("a1", "schedule_agent", user="Find", output="CV103"), 2)
    context.finalize_state()
    path = tmp_path / "trajectory_context.json"
    path.write_text(
        json.dumps(
            trajectory_context_to_payload(context, schema_version="t", session_id="s")
        )
    )

    restored, _ = load_trajectory_context_artifact(path)

    assert [unit.work_id for unit in restored.work_units] == ["work:0"]
    assert restored.work_units[0].receipt_span_indices == [2]
    assert set(restored.agents) == {"moderator", "schedule_agent"}
    assert restored.claims[-1].work_id == "work:0"


def test_artifact_saved_before_work_state_loads_without_stale_units(tmp_path: Path):
    sidecar = {
        "edges": [
            {
                "edge_id": "delegation-1:c1",
                "call_id": "c1",
                "sender": "moderator",
                "receiver": "schedule_agent",
                "dispatcher": "moderator",
                "request": "Find schedules",
                "response": "CV103 at 09:10",
                "source_span_ids": ["s2"],
            }
        ]
    }
    old_payload = {
        "coordination_events": [
            {"event_id": "coordination:0", "event_type": "assignment", "span_index": 1}
        ],
        "coordination_context": sidecar,
    }
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old_payload))
    restored, _ = load_trajectory_context_artifact(path)
    assert restored.work_units == []
    assert all(
        not profile.allocated_work_ids and not profile.received_work_ids
        for profile in restored.agents.values()
    )

    sidecar_only = tmp_path / "sidecar.json"
    sidecar_only.write_text(json.dumps({"coordination_context": sidecar}))
    restored, _ = load_trajectory_context_artifact(sidecar_only)
    assert [unit.outcome for unit in restored.work_units] == ["completed"]
    assert restored.work_units[0].assignment_event_ids == [
        event.event_id for event in restored.coordination_events[:2]
    ]
    assert restored._intent_by_artifact_id(restored.work_units[0].intent_id)


def test_final_answer_index_is_never_an_adapter_event_index():
    spans = [
        {
            "SpanId": "s0",
            "SpanName": "moderator.chat",
            "SpanAttributes": {
                "traceloop.span.kind": "LLM",
                "gen_ai.prompt.0.role": "system",
                "gen_ai.prompt.0.content": "You are a moderator coordinating a team.",
                "gen_ai.completion.0.role": "assistant",
                "gen_ai.completion.0.content": "Final plan: take CV103.",
            },
        }
    ]
    context = TrajectoryContext(
        "",
        coordination_context={
            "final_response": "<|channel>thought\n<channel|>Final plan: take CV103.",
            "final_response_event_index": 592,
        },
        adapter_ingestion="incremental",
    )
    context.ingest_span(TemporalMetricsProcessor._otel_trace_to_span_dict(spans[0]), 0)
    TemporalMetricsProcessor._synchronize_final_answer(
        object.__new__(TemporalMetricsProcessor), context, spans
    )

    assert context.get_final_answer_context()["final_answer_span_index"] == 0


def test_timestamps_with_mixed_fraction_digits_sort_chronologically():
    spans = [
        {"SpanId": "late", "Timestamp": "2026-08-05 15:40:01.10000000"},
        {"SpanId": "early", "Timestamp": "2026-08-05 15:40:01.099999999"},
    ]

    ordered = TemporalMetricsProcessor._sort_spans_chronologically(spans)

    assert [span["SpanId"] for span in ordered] == ["early", "late"]
    assert _timestamp_ns("2026-08-05T15:40:01Z") == _timestamp_ns(1_785_944_401)
    assert _timestamp_ns("2026-08-05T17:40:01+02:00") == _timestamp_ns(1_785_944_401)


def _node(span_id, agent_id, output, links=None):
    span = {
        "entity_type": "agent",
        "span_id": span_id,
        "entity_name": agent_id,
        "agent_id": agent_id,
        "input_payload": {},
        "output_payload": output,
    }
    if links:
        span["links"] = links
    return span


def test_json_tool_call_output_is_routing_not_a_flag_or_an_answer():
    context = _roster_context("moderator", "concierge_agent")
    call = {
        "function": {
            "name": "delegate_to_concierge_agent",
            "arguments": json.dumps({"task": "Please provide the fares."}),
        }
    }
    context.ingest_span(
        _llm(
            "m0",
            "moderator",
            user="Plan a weekend trip to Lisbon with a budget of $500.",
            output=json.dumps({"tool_calls": [call]}),
        ),
        0,
    )

    assert context.flags == []
    assert context.latest_root_answer == ""
    assert all(intent.status != "fulfilled" for intent in context.intents)


def test_waiting_needs_a_first_person_subject():
    described = "Threads hang while waiting for the gateway, holding connections."

    assert _classify_work_response(described)[0] == "completed"
    assert _classify_work_response("I will wait for the schedule agent.")[0] == (
        "waiting"
    )
    assert _classify_work_response(
        "Once the concierge returns the fares, I will total the budget."
    ) == ("waiting", "waiting_reply")


def test_rephrased_retry_to_the_same_recipient_is_linked():
    context = _roster_context("sre", "telemetry")
    tasks = ("Provide a local hypothesis.", "Analyze the payment-service incident.")
    replies = ("Please provide the incident description.", "Gateway timeouts.")
    for attempt, (task, reply) in enumerate(zip(tasks, replies)):
        context.ingest_span(
            {
                "entity_type": "tool",
                "span_id": f"d{attempt}",
                "entity_name": "delegate_to_telemetry",
                "agent_id": "sre",
                "input_payload": {"task": task},
                "output_payload": {"content": reply},
            },
            2 * attempt,
        )
        context.ingest_span(_llm(f"s{attempt}", "sre", output="Next."), 2 * attempt + 1)

    first, second = context.work_units
    assert (first.outcome, second.outcome) == ("needs_input", "completed")
    assert (second.retry_of_work_id, second.attempt_index) == (first.work_id, 2)
    assert second.retry_basis == "same_recipients"


def test_node_state_route_waits_for_the_decision_and_keeps_handback_direction():
    context = _roster_context("moderator", "itinerary_agent", "schedule_agent")
    spans = [
        _node("m0", "moderator", {"next_agent": "itinerary_agent"}),
        _llm("m1", "moderator", output="Need routes. DECISION: itinerary_agent"),
        _router("r1", "itinerary_agent"),
        _llm("i1", "itinerary_agent", user="Find routes", output="V-L takes 2h."),
        _router("r2", "moderator"),
        _node(
            "m2",
            "moderator",
            {"next_agent": "schedule_agent"},
            links=[
                {
                    "span_id": "i1",
                    "attributes": {
                        "link.type": "agent_handoff",
                        "link.from_agent": "itinerary_agent",
                    },
                }
            ],
        ),
        _llm("m3", "moderator", output="Need times. DECISION: schedule_agent"),
        _router("r3", "schedule_agent"),
    ]
    for index, span in enumerate(spans):
        context.ingest_span(span, index)

    first, second = context.work_units
    assert first.request.endswith("DECISION: itinerary_agent")
    assert second.request.endswith("DECISION: schedule_agent")
    assert first.outcome == "completed"
    assignments = [
        (event.span_index, event.sender_agent_ids, event.recipient_agent_ids)
        for event in context.coordination_events
        if event.event_type == "assignment"
    ]
    assert assignments == [
        (2, ["moderator"], ["itinerary_agent"]),
        (7, ["moderator"], ["schedule_agent"]),
    ]
    handoffs = [
        (event.span_index, event.sender_agent_ids, event.recipient_agent_ids)
        for event in context.coordination_events
        if event.event_type == "handoff"
    ]
    assert handoffs == [(5, ["itinerary_agent"], ["moderator"])]


def test_node_state_route_without_a_router_opens_on_the_target_span():
    context = _roster_context("moderator", "schedule_agent")
    context.ingest_span(_node("m0", "moderator", {"next_agent": "schedule_agent"}), 0)
    context.ingest_span(_llm("m1", "moderator", output="DECISION: schedule_agent"), 1)
    assert context.work_units == []

    context.ingest_span(_llm("s1", "schedule_agent", user="Times?", output="CV103"), 2)
    context.finalize_state()

    unit = context.work_units[0]
    assert (unit.request, unit.request_span_index) == ("DECISION: schedule_agent", 0)
    assert unit.receipt_span_indices == [2]
    assert unit.outcome == "completed"


def test_roster_needs_llm_or_tool_activity_and_skips_the_app_name():
    raw_spans = [
        {
            "SpanId": "a",
            "SpanName": "moderator.agent",
            "ServiceName": "trip-app",
            "SpanAttributes": {"agent_id": "moderator"},
        },
        {
            "SpanId": "b",
            "ParentSpanId": "a",
            "SpanName": "ChatOpenAI.chat",
            "ServiceName": "trip-app",
            "SpanAttributes": {},
        },
        {
            "SpanId": "c",
            "SpanName": "finalize_on_error.agent",
            "ServiceName": "trip-app",
            "SpanAttributes": {"agent_id": "finalize_on_error"},
        },
    ]
    by_id = {span["SpanId"]: span for span in raw_spans}

    roster = TemporalMetricsProcessor._declared_roster(raw_spans, by_id)
    assert roster == [("moderator", 0)]

    context = TrajectoryContext("")
    context.declare_roster(roster)
    context.ingest_span(
        {
            "entity_type": "agent",
            "span_id": "c",
            "entity_name": "finalize_on_error",
            "agent_id": "finalize_on_error",
            "app_name": "trip-app",
            "attributes": {"mas.agent.role": "finalizer"},
            "output_payload": {},
        },
        2,
    )
    assert set(context.agents) == {"moderator"}
    assert set(context.coordination_metadata.get("agents", {})) <= {"moderator"}


def test_final_answer_reads_user_message_from_an_envelope_and_node_answers():
    def llm_span(span_id, service, content):
        return {
            "SpanId": span_id,
            "SpanName": f"{service}.chat",
            "ServiceName": service,
            "SpanAttributes": {
                "traceloop.span.kind": "LLM",
                "gen_ai.completion.0.role": "assistant",
                "gen_ai.completion.0.content": content,
            },
        }

    envelope = json.dumps(
        {
            "messages": [
                {"type": "ChatMessage", "message": "It is 5:40 PM in Paris."},
                {"type": "RequestToSpeak", "target": "noa-user-proxy"},
            ]
        }
    )
    spans = [
        llm_span("s0", "noa-moderator", "Asking the web surfer."),
        llm_span("s1", "noa-web-surfer", "Paris time is 17:40."),
        llm_span("s2", "noa-moderator", envelope),
    ]
    assert SpanNormalizer.extract_final_answer(spans) == ("It is 5:40 PM in Paris.", 2)

    node = {
        "SpanId": "n0",
        "SpanName": "moderator.agent",
        "SpanAttributes": {
            "traceloop.entity.output": json.dumps({"final_answer": "Take CV103."})
        },
    }
    answer = llm_span("n1", "app", "FINAL_ANSWER: Take CV103.")
    assert SpanNormalizer.extract_final_answer([node, answer]) == ("Take CV103.", 1)


def test_orchestration_prompt_that_wraps_the_request_is_not_user_text():
    request = "What trains go from Celestia to Verdantia?"
    context = TrajectoryContext("")
    context.declare_root_request(request)
    prompt = (
        f"User: {request} Original question: {request} Based on the conversation "
        "so far, decide: 1. If you need to call an agent, respond with DECISION. "
        "Assistant: Children under 12 travel at half fare; keep total cost under 12."
    )
    context.ingest_span(_llm("m0", "moderator", user=prompt, output="DECISION: x"), 0)

    user_facts = [
        f.content for f in context.evidence if f.fact_type == "user_statement"
    ]
    assert user_facts == [request]
    assert all(intent.requirement_type != "budget" for intent in context.intents)
    assert any(f.fact_type == "environment_context" for f in context.evidence)


def _delegation(span_id, allocator, tool, output, *, index_attrs=None, task="Do it"):
    return {
        "entity_type": "tool",
        "span_id": span_id,
        "entity_name": tool,
        "agent_id": allocator,
        "attributes": dict(index_attrs or {}),
        "input_payload": {"task": task},
        "output_payload": output,
    }


def test_delegation_to_an_agent_that_never_runs_is_a_no_response_unit():
    context = _roster_context("coordinator", "searcher")
    context.ingest_span(
        _delegation(
            "d0",
            "coordinator",
            "delegate_task",
            {},
            index_attrs={"mas.delegation.target": "booker"},
        ),
        0,
    )
    context.ingest_span(_llm("c1", "coordinator", output="Booker never replied."), 1)
    context.finalize_state()

    unit = context.work_units[0]
    assert unit.recipient_agent_ids == ["booker"]
    assert unit.outcome == "no_response"
    assert "delegation_target" in context.agents["booker"].declared_by


def test_handoff_only_operation_opens_a_unit():
    context = _roster_context("triage", "billing")
    context.ingest_span(
        _delegation("t0", "triage", "transfer_to_billing", {"content": "ok"}), 0
    )
    context.ingest_span(_llm("b1", "billing", user="Refund?", output="Refunded."), 1)
    context.finalize_state()

    unit = context.work_units[0]
    assert (unit.allocator_agent_id, unit.recipient_agent_ids) == (
        "triage",
        ["billing"],
    )
    assert unit.receipt_span_indices == [1]
    assert all(
        event.work_id == unit.work_id
        for event in context.coordination_events
        if event.event_type == "handoff"
    )


def test_a_repeated_route_back_to_the_allocator_is_not_new_work():
    context = _roster_context("moderator", "schedule_agent")
    spans = [
        _llm("m0", "moderator", user="Trains?", output="DECISION: schedule_agent"),
        _router("r0", "schedule_agent"),
        _llm("s0", "schedule_agent", user="Trains?", output="CV103 at 09:10"),
        _router("r1", "moderator"),
        _router("r2", "moderator"),
        _llm("m1", "moderator", output="Take CV103 at 09:10 from Celestia."),
    ]
    for index, span in enumerate(spans):
        context.ingest_span(span, index)

    assert len(context.work_units) == 1
    assert context.claims[-1].claim_type == "assertion"
    assert context.latest_root_answer_span_index == 5


def test_message_target_without_text_keeps_message_source_and_no_fallback():
    context = _roster_context("orchestrator", "web_surfer", "coder")
    for index, target in enumerate(("web_surfer", "coder")):
        context.ingest_span(
            _llm(
                f"o{index}",
                "orchestrator",
                system="You are the orchestrator. Coordinate the team.",
                output=json.dumps({"type": "RequestToSpeak", "target": target}),
            ),
            index,
        )

    assert [(unit.source, unit.request) for unit in context.work_units] == [
        ("message", ""),
        ("message", ""),
    ]
    assert context.work_units[1].previous_owner_agent_ids == []


def test_tool_spans_are_attributed_by_tool_call_id():
    context = _roster_context("a", "b")
    for index, agent in enumerate(("a", "b")):
        span = _llm(f"l{index}", agent, output="", tool_calls=["search"])
        span["output_payload"]["tool_calls"][0]["id"] = f"call-{agent}"
        context.ingest_span(span, index)
    for index, agent in enumerate(("a", "b"), start=2):
        context.ingest_span(
            {
                "entity_type": "tool",
                "span_id": f"t{index}",
                "entity_name": "search",
                "attributes": {"gen_ai.tool.call.id": f"call-{agent}"},
                "input_payload": {"query": agent},
                "output_payload": {"result": "hit"},
            },
            index,
        )

    tool_facts = [f for f in context.evidence if f.fact_type == "tool_output"]
    assert [fact.agent_id for fact in tool_facts] == ["a", "b"]


def test_errored_delegation_fails_and_an_unkeyed_span_joins_its_edge_unit():
    context = _roster_context("moderator", "schedule_agent")
    context.ingest_span(
        _delegation(
            "d0",
            "moderator",
            "delegate_to_schedule_agent",
            {"status": "error", "message": "schedule_agent timed out"},
        ),
        0,
    )
    context.ingest_span(_llm("m1", "moderator", output="It timed out."), 1)
    assert context.work_units[0].outcome == "failed"

    coordination = CoordinationContext.from_payload(
        {
            "edges": [
                {
                    "edge_id": "e1",
                    "call_id": "c1",
                    "sender": "moderator",
                    "receiver": "schedule_agent",
                    "dispatcher": "moderator",
                    "request": "Find schedules",
                    "response": "CV103",
                    "source_span_ids": ["s2"],
                }
            ]
        }
    )
    for mode in ("eager", "incremental"):
        edge_context = TrajectoryContext(
            "", coordination_context=coordination, adapter_ingestion=mode
        )
        edge_context.ingest_span(
            _delegation(
                "s2", "moderator", "delegate_to_schedule_agent", {"value": "CV103"}
            ),
            0,
        )
        edge_context.finalize_state()
        assert len(edge_context.work_units) == 1, mode


def test_adapter_verification_survives_a_span_verification():
    coordination = CoordinationContext.from_payload(
        {
            "edges": [
                {
                    "edge_id": "e1",
                    "call_id": "c1",
                    "sender": "sre",
                    "receiver": "verifier",
                    "dispatcher": "sre",
                    "request": "Verify the rollback",
                    "response": "verification: approved",
                    "source_span_ids": ["d0"],
                }
            ],
            "verification": {
                "edge_id": "e1",
                "sender": "sre",
                "receiver": "verifier",
                "dispatcher": "sre",
                "verdict": "APPROVED",
                "verification_gate_observed": True,
            },
        }
    )
    context = TrajectoryContext(
        "", coordination_context=coordination, adapter_ingestion="incremental"
    )
    context.declare_roster([("sre", 0), ("verifier", 1)])
    context.ingest_span(
        _delegation("d0", "sre", "delegate_to_verifier", {"value": "approved"}), 0
    )
    context.ingest_span(
        {
            **_llm("v1", "verifier", user="Verify", output="Looks good to me."),
            "entity_name": "verifier",
            "attributes": {"mas.agent.role": "verifier"},
        },
        1,
    )
    context.ingest_span(_llm("s2", "sre", output="Rolling back."), 2)
    context.finalize_state()

    verifications = [
        (event.status, event.span_index)
        for event in context.coordination_events
        if event.event_type == "verification"
    ]
    assert ("approved", 2) in verifications


def test_flags_skip_courtesy_and_descriptions():
    for text in (
        "CV103 departs 08:30. Let me know if you need more information.",
        "Please confirm the dates look right.",
        "The route costs EUR 42. I can't guarantee prices will stay the same.",
        "I cannot recommend the museum highly enough.",
        "Expect 20 minutes waiting for the transfer.",
        "I cannot find any delays on that route.",
    ):
        assert _classify_work_response(text)[0] == "completed", text
    assert _classify_work_response("I'm unable to access the fares database.")[0] == (
        "declined"
    )


def test_small_helpers_are_robust():
    context = TrajectoryContext("")
    context.ingest_span(_llm("m0", "moderator", output="Take CV103 at 09:10."), 0)
    context.ingest_span(_llm("v1", "verifier", output="CV103"), 1)
    assert context.span_index_for_text("Take CV103 at 09:10.") == 0

    assert _timestamp_ns(float("nan")) is None
    assert _timestamp_ns("inf") is None
    assert (
        _timestamp_ns(1727500000123456800) - _timestamp_ns("1727500000123456700") == 100
    )

    roster = _roster_context("moderator", "schedule_agent")
    roster.ingest_span(_router("r0", "schedule_agent"), 0)
    roster.ingest_span(
        {**_node("n1", "schedule_agent", "schedule_agent"), "output_payload": "x"}, 1
    )
    assert roster.work_units[0].receipt_span_indices == [1]

    calls = _roster_context("moderator", "schedule_agent")
    for index, call in enumerate(("c12", "c1")):
        calls.ingest_span(
            _delegation(
                f"d{index}",
                "moderator",
                "delegate_to_schedule_agent",
                {"value": "ok"},
                index_attrs={"mas.call.id": call},
                task=f"Task {call}",
            ),
            index,
        )
    child = _llm("s0", "schedule_agent", output="Working")
    child["attributes"] = {"mas.parent.call.id": "schedule_agent-c12-exec"}
    calls.ingest_span(child, 2)
    assert calls.work_units[0].receipt_span_indices == [2]
    assert calls.work_units[1].receipt_span_indices == []


def test_flat_roster_line_ends_at_its_sentence():
    header = (
        "You are the moderator coordinating a team of specialized agents. "
        "Available agents: - schedule_agent: finds train schedules. "
        "- concierge_agent: looks up fares and computes total costs. "
        + "Always answer in English and cite the agent that found each fact. "
        * 8
    )
    context = _roster_context("moderator", "schedule_agent", "concierge_agent")
    context.add_policy_rule(header, source_name="semantic_contract:moderator")

    capability = context.agents["concierge_agent"].declared_capability
    assert capability == "looks up fares and computes total costs."


def test_work_links_are_not_sent_to_judges():
    context = _roster_context("moderator", "schedule_agent")
    context.ingest_span(_llm("m0", "moderator", output="DECISION: schedule_agent"), 0)
    context.ingest_span(_router("r0", "schedule_agent"), 1)
    assert any(link.relation_type == "assigns" for link in context.provenance_links)

    payload = build_context_payload(
        context, MetricInputConfig(), metric_name="task_completion"
    )
    assert all(
        link["relation_type"] not in {"assigns", "communicates"}
        for link in payload["provenance_links"]
    )


def _raw_llm(span_id, content, *, service="app", parent=None, attrs=None):
    span = {
        "SpanId": span_id,
        "SpanName": f"{service}.chat",
        "ServiceName": service,
        "SpanAttributes": {
            "traceloop.span.kind": "LLM",
            "gen_ai.completion.0.role": "assistant",
            "gen_ai.completion.0.content": content,
            **(attrs or {}),
        },
    }
    if parent:
        span["ParentSpanId"] = parent
    return span


def test_normalizer_keeps_semconv_payloads_and_named_agents():
    parent = {
        "SpanId": "p0",
        "SpanName": "execute_task moderator",
        "SpanAttributes": {
            "traceloop.entity.input": json.dumps({"question": "Parent input"}),
            "traceloop.entity.output": json.dumps({"answer": "Parent output"}),
        },
    }
    semconv = {
        "SpanId": "c0",
        "ParentSpanId": "p0",
        "SpanName": "chat gpt-4o",
        "SpanAttributes": {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.agent.name": "Triage Agent",
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": "Own input"}]}]
            ),
            "gen_ai.output.messages": json.dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": "Own output"}],
                    }
                ]
            ),
        },
    }
    by_id = {"p0": parent, "c0": semconv}
    normalized = SpanNormalizer.normalize_span(semconv, by_id)

    assert "Own input" in json.dumps(normalized["input_payload"])
    assert "Own output" in json.dumps(normalized["output_payload"])
    assert normalized["agent_id"] == "Triage Agent"


def test_roster_ignores_service_names_when_agents_are_named():
    raw_spans = [
        {
            "SpanId": "a",
            "SpanName": "planner.chat",
            "ServiceName": "mas-app",
            "SpanAttributes": {"mas.agent.id": "planner", "traceloop.span.kind": "LLM"},
        },
        {
            "SpanId": "b",
            "SpanName": "search.tool",
            "ServiceName": "mcp-search-server",
            "SpanAttributes": {},
        },
    ]
    by_id = {span["SpanId"]: span for span in raw_spans}

    roster = TemporalMetricsProcessor._declared_roster(raw_spans, by_id)
    assert roster == [("planner", 0)]


def test_final_answer_precedence_and_workflow_mapping():
    first = _raw_llm("r0", "Delegating.", attrs={"mas.agent.id": "moderator"})
    researcher = {
        "SpanId": "x1",
        "SpanName": "researcher.agent",
        "SpanAttributes": {
            "traceloop.entity.output": json.dumps({"final_answer": "raw notes"})
        },
    }
    last = _raw_llm(
        "r2", "Solar costs fell 12% this year.", attrs={"mas.agent.id": "moderator"}
    )
    assert SpanNormalizer.extract_final_answer([first, researcher, last]) == (
        "Solar costs fell 12% this year.",
        2,
    )

    answer = "Day 1: Museum\nDay 2: Café du Monde"
    workflow = {
        "SpanId": "w0",
        "SpanName": "trip.workflow",
        "SpanAttributes": {
            "traceloop.entity.output": json.dumps({"final_answer": answer})
        },
    }
    writer = {
        "SpanId": "w1",
        "SpanName": "writer.agent",
        "SpanAttributes": {"traceloop.entity.output": json.dumps({"response": answer})},
    }
    cleanup = {"SpanId": "w2", "SpanName": "cleanup.task", "SpanAttributes": {}}
    assert SpanNormalizer.extract_final_answer([workflow, writer, cleanup]) == (
        answer,
        1,
    )


def test_repeated_header_contract_cuts_at_the_request_slot_only():
    instructions = (
        "Within this conversation you are a weather assistant for a travel team. "
        "Answer with the forecast, the source, and any travel advisories that "
        "apply to the destination the user names."
    )

    def call(span_id, first, second=None):
        attrs = {
            "traceloop.span.kind": "LLM",
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": first,
        }
        if second:
            attrs.update(
                {"gen_ai.prompt.1.role": "user", "gen_ai.prompt.1.content": second}
            )
        return {
            "SpanId": span_id,
            "SpanName": "weather.chat",
            "SpanAttributes": {**attrs, "mas.agent.id": "weather"},
        }

    spans = [call("a", f"{instructions} Q: {n}", "Go") for n in ("hi", "hi again")]
    contracts = SpanNormalizer.extract_agent_semantic_contracts(spans, "hi")
    assert contracts and contracts[0][1].startswith("Within this conversation")

    question = (
        "I am planning a surprise anniversary dinner for my partner next Friday "
        "and need a quiet restaurant near the river that can seat two at 8pm."
    )
    react = [call(span_id, question) for span_id in ("q0", "q1", "q2")]
    assert SpanNormalizer.extract_agent_semantic_contracts(react) == []
