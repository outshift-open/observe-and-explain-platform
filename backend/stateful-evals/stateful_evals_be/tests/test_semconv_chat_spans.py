#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OTel GenAI semantic-convention chat spans are kept, typed, and readable."""

import json

from stateful_evals_be.evaluation.span_normalization import SpanNormalizer


def _messages(role: str, text: str) -> str:
    return json.dumps([{"role": role, "parts": [{"type": "text", "content": text}]}])


def _chat_span(span_id: str, question: str, answer: str) -> dict:
    return {
        "SpanId": span_id,
        "SpanName": "ChatOpenAI.chat",
        "Timestamp": "2026-01-01 00:00:00.000000000",
        "SpanAttributes": {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.input.messages": _messages("user", question),
            "gen_ai.output.messages": _messages("assistant", answer),
        },
    }


def test_distinct_semconv_chat_spans_are_not_deduplicated():
    spans = [
        _chat_span("c1", "Route from A to B?", "Take the train."),
        _chat_span("c2", "Route from B to C?", "Take the bus."),
        _chat_span("c3", "Route from A to B?", "Take the train."),  # exact repeat
    ]

    unique = SpanNormalizer.deduplicate_spans(spans)

    assert [span["SpanId"] for span in unique] == ["c1", "c2"]


def test_semconv_chat_span_is_an_llm_span_with_readable_payloads():
    span = _chat_span("c1", "Route from A to B?", "Take the train.")

    normalized = SpanNormalizer.normalize_span(span, spans_by_id={"c1": span})

    assert normalized["entity_type"] == "llm"
    [question] = normalized["input_payload"]["messages"]
    [answer] = normalized["output_payload"]["messages"]
    assert SpanNormalizer._extract_message_entry(question) == {
        "role": "user",
        "content": "Route from A to B?",
    }
    assert SpanNormalizer._extract_message_entry(answer) == {
        "role": "assistant",
        "content": "Take the train.",
    }


def test_legacy_prompt_attributes_still_take_precedence():
    span = _chat_span("c1", "semconv question", "semconv answer")
    span["SpanAttributes"]["gen_ai.prompt.0.role"] = "user"
    span["SpanAttributes"]["gen_ai.prompt.0.content"] = "legacy question"

    normalized = SpanNormalizer.normalize_span(span, spans_by_id={"c1": span})

    assert normalized["input_payload"]["gen_ai.prompt.0.content"] == "legacy question"


def _execute_span(operation: str, provider: str) -> dict:
    return {
        "SpanId": f"{operation}-{provider}",
        "SpanName": f"{operation} some_node",
        "Timestamp": "2026-01-01 00:00:01.000000000",
        "SpanAttributes": {
            "gen_ai.operation.name": operation,
            "gen_ai.provider.name": provider,
            "traceloop.span.kind": "tool",
            "gen_ai.tool.name": "read_document",
        },
    }


def test_langgraph_execute_spans_are_framework_spans():
    for operation in ("execute_task", "execute_tool"):
        attrs = _execute_span(operation, "langgraph")["SpanAttributes"]
        assert SpanNormalizer.is_framework_span(attrs)
    # Same operation from another provider is an ordinary tool span.
    other = _execute_span("execute_tool", "openai")["SpanAttributes"]
    assert not SpanNormalizer.is_framework_span(other)
    assert not SpanNormalizer.is_framework_span(
        _chat_span("c", "q", "a")["SpanAttributes"]
    )


def test_framework_spans_are_not_judged_but_other_spans_are():
    from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
    from stateful_evals_be.models.requests import TemporalMetricOptions

    processor = object.__new__(TemporalMetricsProcessor)
    processor.options = TemporalMetricOptions()

    def metrics_for(raw: dict) -> list:
        span = SpanNormalizer.normalize_span(raw, spans_by_id={raw["SpanId"]: raw})
        return processor._metrics_for_span(span)

    assert metrics_for(_execute_span("execute_tool", "langgraph")) == []
    assert metrics_for(_execute_span("execute_task", "langgraph")) == []
    assert metrics_for(_execute_span("execute_tool", "openai"))  # still judged
    assert metrics_for(_chat_span("c1", "q", "a"))  # chat spans still judged


def _tool_chat_spans() -> list[dict]:
    """Two chat spans: the model calls a tool, then answers using its reply."""
    call = {
        "type": "tool_call",
        "id": "call_1",
        "name": "read_document",
        "arguments": "{}",
    }
    reply = {
        "type": "tool_call_response",
        "id": "call_1",
        "response": "Train 7 leaves at 09:10.",
    }
    text = lambda t: {"type": "text", "content": t}  # noqa: E731

    def span(span_id, ts, inputs, outputs):
        return {
            "SpanId": span_id,
            "SpanName": "ChatOpenAI.chat",
            "Timestamp": ts,
            "SpanAttributes": {
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.input.messages": json.dumps(inputs),
                "gen_ai.output.messages": json.dumps(outputs),
            },
        }

    question = {"role": "user", "parts": [text("When does the train leave?")]}
    return [
        span(
            "c1",
            "2026-01-01 00:00:01",
            [question],
            [{"role": "assistant", "parts": [call]}],
        ),
        span(
            "c2",
            "2026-01-01 00:00:03",
            [
                question,
                {"role": "assistant", "parts": [call]},
                {"role": "tool", "parts": [reply]},
            ],
            [{"role": "assistant", "parts": [text("The train leaves at 09:10.")]}],
        ),
    ]


def _context_from(spans: list[dict]):
    from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext

    by_id = {span["SpanId"]: span for span in spans}
    context = TrajectoryContext(policy_text="")
    for index, span in enumerate(spans):
        context.ingest_span(
            SpanNormalizer.normalize_span(span, spans_by_id=by_id), span_index=index
        )
    return context


def test_chat_messages_alone_carry_request_tool_call_and_result():
    context = _context_from(_tool_chat_spans())

    users = [f.content for f in context.evidence if f.fact_type == "user_statement"]
    tools = [f for f in context.evidence if f.fact_type == "tool_output"]

    assert users == ["When does the train leave?"]
    assert [f.source_name for f in tools] == ["read_document"]  # once, not per span
    assert "Train 7 leaves at 09:10." in tools[0].content
    assert (
        context.get_final_answer_context()["final_answer"]
        == "The train leaves at 09:10."
    )


def test_tool_result_from_chat_is_not_added_twice_when_a_tool_span_exists():
    tool_span = {
        "SpanId": "t1",
        "SpanName": "read_document.tool",
        "Timestamp": "2026-01-01 00:00:02",
        "SpanAttributes": {
            "traceloop.span.kind": "tool",
            "traceloop.entity.name": "read_document",
            "traceloop.entity.input": "{}",
            "traceloop.entity.output": json.dumps(
                {"output": "Train 7 leaves at 09:10."}
            ),
        },
    }
    first, second = _tool_chat_spans()

    context = _context_from([first, tool_span, second])

    tools = [f for f in context.evidence if f.fact_type == "tool_output"]
    assert len(tools) == 1
