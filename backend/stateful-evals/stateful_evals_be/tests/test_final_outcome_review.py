#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
from types import SimpleNamespace

from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
from stateful_evals_be.evaluation.trajectory_context import (
    ClaimEntry,
    EvidenceFact,
    TrajectoryContext,
)


class FakeLLMClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def query(self, messages, temperature=0.0):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(self.payload))
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
        )


def _processor_with_final_outcome(payload: dict) -> TemporalMetricsProcessor:
    processor = object.__new__(TemporalMetricsProcessor)
    processor.llm_client = FakeLLMClient(payload)
    return processor


def _context_with_final_answer(final_answer: str) -> TrajectoryContext:
    ctx = TrajectoryContext(
        policy_text="Refunds are denied after 30 days unless the item is defective."
    )
    ctx.evidence.append(
        EvidenceFact(
            span_index=0,
            fact_type="user_statement",
            content="I want a refund for an order from 45 days ago.",
            source_name="user",
        )
    )
    ctx.evidence.append(
        EvidenceFact(
            span_index=1,
            fact_type="tool_output",
            content='{"order_age_days": 45, "defective": false}',
            source_name="lookup_order",
        )
    )
    ctx.claims.append(
        ClaimEntry(
            span_index=2,
            claim_type="assertion",
            content=final_answer,
            entity_name="refund_agent",
        )
    )
    return ctx


def test_final_outcome_review_accepts_policy_compliant_denial() -> None:
    processor = _processor_with_final_outcome(
        {
            "passes": True,
            "verdict": "PASS",
            "failure_metric": "FinalOutcomeRelevancy",
            "severity": 0.0,
            "user_request_addressed": True,
            "policy_compliant_resolution": True,
            "evidence_supported": True,
            "observed_impact": "none",
            "hard_rule_violation": False,
            "reasoning": "The denial follows the refund policy.",
            "explanation": "The user request was resolved under policy.",
        }
    )
    ctx = _context_with_final_answer(
        "I cannot issue the refund because the order is outside the 30 day window."
    )

    fatal, minor = processor._review_final_outcome(
        traj_ctx=ctx,
        system_message=ctx.policy_text,
        session_id="session-pass",
        intent_states=[],
    )

    assert fatal == []
    assert minor == []
    assert processor._last_final_outcome_usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }


def test_final_outcome_review_fails_unsupported_resolution() -> None:
    processor = _processor_with_final_outcome(
        {
            "passes": False,
            "verdict": "FAIL",
            "failure_metric": "FinalOutcomeRelevancy",
            "severity": 0.9,
            "user_request_addressed": True,
            "policy_compliant_resolution": False,
            "evidence_supported": False,
            "observed_impact": "unsupported_resolution",
            "hard_rule_violation": False,
            "reasoning": "The final refund approval contradicts the policy.",
            "explanation": "The order is outside the allowed refund window.",
        }
    )
    ctx = _context_with_final_answer("I issued the refund for your order.")

    fatal, minor = processor._review_final_outcome(
        traj_ctx=ctx,
        system_message=ctx.policy_text,
        session_id="session-fail",
        intent_states=[],
    )

    assert minor == []
    assert len(fatal) == 1
    assert fatal[0].metric == "FinalOutcomeRelevancy"
    assert fatal[0].observed_impact == "unsupported_resolution"


def test_final_answer_context_uses_recent_user_request_history() -> None:
    ctx = TrajectoryContext(policy_text="")
    ctx.evidence.extend(
        [
            EvidenceFact(
                span_index=0,
                fact_type="user_statement",
                content="Can I partially cancel the office items from my order?",
                source_name="user",
            ),
            EvidenceFact(
                span_index=4,
                fact_type="user_statement",
                content=(
                    "Please change my default profile address to match the Seattle "
                    "shipping address on order #W1845024."
                ),
                source_name="user",
            ),
            EvidenceFact(
                span_index=6,
                fact_type="user_statement",
                content="Yes, please go ahead and update my default address.",
                source_name="user",
            ),
        ]
    )

    user_question = ctx.get_final_answer_context()["user_question"]

    assert "partially cancel" in user_question
    assert "default profile address" in user_question
    assert "go ahead and update" in user_question
    assert user_question.index("go ahead and update") < user_question.index(
        "partially cancel"
    )


def test_raw_user_request_extraction_prefers_structured_telemetry() -> None:
    raw_spans = [
        {
            "SpanName": "LangGraph.workflow",
            "SpanAttributes": {
                "traceloop.entity.input": json.dumps(
                    {
                        "inputs": {
                            "messages": [
                                {
                                    "lc": 1,
                                    "type": "constructor",
                                    "id": [
                                        "langchain",
                                        "schema",
                                        "messages",
                                        "HumanMessage",
                                    ],
                                    "kwargs": {
                                        "content": (
                                            "Give me airplane schedules with fares "
                                            "for Verdantia to Luminos"
                                        ),
                                        "type": "human",
                                    },
                                }
                            ],
                            "question": (
                                "Give me airplane schedules with fares for "
                                "Verdantia to Luminos"
                            ),
                        }
                    }
                )
            },
        },
        {
            "SpanName": "ChatOpenAI.chat",
            "SpanAttributes": {
                "traceloop.span.kind": "LLM",
                "gen_ai.prompt.0.role": "user",
                "gen_ai.prompt.0.content": (
                    "Sub-agent instruction that should not become the user request."
                ),
            },
        },
    ]

    user_request = (
        TemporalMetricsProcessor._extract_user_request_history_from_raw_spans(raw_spans)
    )

    assert "Give me airplane schedules with fares" in user_request
    assert "Sub-agent instruction" not in user_request


def test_raw_user_request_extraction_excludes_peer_agent_handoffs() -> None:
    raw_spans = [
        {
            "SpanName": "LLMCall",
            "SpanAttributes": {
                "ioa_observe.entity.input": json.dumps(
                    {
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a moderator coordinating a team.",
                            },
                            {
                                "role": "user",
                                "content": "Plan a trip from Luminos to Celestia.",
                            },
                        ]
                    }
                )
            },
        },
        {
            "SpanName": "LLMCall",
            "SpanAttributes": {
                "ioa_observe.entity.input": json.dumps(
                    {
                        "messages": [
                            {
                                "role": "system",
                                "content": "You have tools to look up route schedules.",
                            },
                            {
                                "role": "user",
                                "content": "Check route LC for the delegated trip task.",
                            },
                        ]
                    }
                )
            },
        },
    ]

    user_request = (
        TemporalMetricsProcessor._extract_user_request_history_from_raw_spans(raw_spans)
    )

    assert user_request == "Plan a trip from Luminos to Celestia."


def test_raw_final_answer_uses_latest_tool_free_moderator_output() -> None:
    moderator_system = "You are a moderator coordinating a team of agents."
    raw_spans = [
        {
            "SpanName": "LLMCall",
            "SpanAttributes": {
                "ioa_observe.span.kind": "llm",
                "ioa_observe.entity.input": json.dumps(
                    {
                        "messages": [
                            {"role": "system", "content": moderator_system},
                            {"role": "user", "content": "Plan a trip."},
                        ]
                    }
                ),
                "ioa_observe.entity.output": json.dumps(
                    {
                        "content": "I will ask the itinerary agent.",
                        "tool_calls": [
                            {
                                "name": "delegate_to_itinerary_agent",
                                "arguments": {"task": "Find a route."},
                            }
                        ],
                    }
                ),
            },
        },
        {
            "SpanName": "LLMCall",
            "SpanAttributes": {
                "ioa_observe.span.kind": "llm",
                "ioa_observe.entity.input": json.dumps(
                    {
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an itinerary specialist.",
                            },
                            {"role": "user", "content": "Find a route."},
                        ]
                    }
                ),
                "ioa_observe.entity.output": json.dumps(
                    {"content": "A delegated-agent answer.", "tool_calls": None}
                ),
            },
        },
        {
            "SpanName": "LLMCall",
            "SpanAttributes": {
                "ioa_observe.span.kind": "llm",
                "ioa_observe.entity.input": json.dumps(
                    {
                        "messages": [
                            {"role": "system", "content": moderator_system},
                            {"role": "user", "content": "Plan a trip."},
                        ]
                    }
                ),
                "ioa_observe.entity.output": json.dumps(
                    {
                        "content": "Here is your complete itinerary and total price.",
                        "tool_calls": None,
                    }
                ),
            },
        },
    ]

    final_answer, span_index = (
        TemporalMetricsProcessor._extract_final_answer_from_raw_spans(raw_spans)
    )

    assert final_answer == "Here is your complete itinerary and total price."
    assert span_index == 2


def test_final_answer_context_uses_latest_root_assertion_only() -> None:
    ctx = TrajectoryContext(policy_text="")
    ctx.claims.extend(
        [
            ClaimEntry(
                span_index=2,
                claim_type="assertion",
                content="I will delegate the itinerary research.",
                entity_name="moderator",
            ),
            ClaimEntry(
                span_index=5,
                claim_type="peer_agent_assertion",
                content="A route specialist found three options.",
                entity_name="route_agent",
            ),
            ClaimEntry(
                span_index=8,
                claim_type="assertion",
                content="Here is the complete itinerary.",
                entity_name="moderator",
            ),
        ]
    )

    final_context = ctx.get_final_answer_context()

    assert final_context["final_answer"] == "Here is the complete itinerary."
    assert final_context["final_answer_span_index"] == 8


def test_final_answer_context_and_claim_retain_full_root_output() -> None:
    ctx = TrajectoryContext(policy_text="")
    full_answer = "Complete itinerary: " + ("detail " * 200)
    ctx.ingest_span(
        {
            "entity_type": "llm",
            "entity_name": "moderator",
            "input_payload": {
                "gen_ai.prompt.0.role": "system",
                "gen_ai.prompt.0.content": (
                    "You are a moderator coordinating a team of agents."
                ),
                "gen_ai.prompt.1.role": "user",
                "gen_ai.prompt.1.content": "Plan a complete trip.",
            },
            "output_payload": {
                "gen_ai.completion.0.role": "assistant",
                "gen_ai.completion.0.content": full_answer,
            },
        },
        span_index=4,
    )

    final_context = ctx.get_final_answer_context()

    assert ctx.claims[0].content == full_answer.strip()
    assert final_context["final_answer"] == full_answer.strip()
    assert final_context["final_answer_span_index"] == 4


def test_json_response_parser_accepts_reasoning_prefix() -> None:
    parsed = TemporalMetricsProcessor._parse_json_response(
        'I checked the complete trajectory.\n{"passes": true, "verdict": "PASS"}'
    )

    assert parsed == {"passes": True, "verdict": "PASS"}
