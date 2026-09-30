#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json

from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor


def _observe_span(
    *,
    span_id: str,
    kind: str,
    name: str,
    input_payload: dict,
    output_payload: dict,
) -> dict:
    return {
        "SpanId": span_id,
        "SpanName": name,
        "SpanAttributes": {
            "session.id": "session-1",
            "ioa_observe.span.kind": kind,
            "ioa_observe.entity.name": name,
            "ioa_observe.entity.input": json.dumps(input_payload),
            "ioa_observe.entity.output": json.dumps(output_payload),
        },
        "StatusCode": "OK",
        "ServiceName": "trip-planner",
        "Timestamp": f"2026-08-10T12:00:0{span_id[-1]}+00:00",
        "ParentSpanId": "",
        "Duration": 1,
        "TraceId": "trace-1",
    }


def test_pure_observe_sdk_spans_classify_and_retain_io() -> None:
    spans = [
        _observe_span(
            span_id="span-1",
            kind="llm",
            name="LLMCall",
            input_payload={"messages": [{"role": "user", "content": "Find a ferry."}]},
            output_payload={"content": "I will inspect the schedules."},
        ),
        _observe_span(
            span_id="span-2",
            kind="tool",
            name="read_document",
            input_payload={"file_path": "schedule.txt"},
            output_payload={"content": "No inter-city ferry is listed."},
        ),
        _observe_span(
            span_id="span-3",
            kind="agent",
            name="schedule_agent",
            input_payload={"content": "Find a ferry."},
            output_payload={"content": "No ferry was found."},
        ),
    ]

    unique = TemporalMetricsProcessor._deduplicate_spans(spans)
    converted = [
        TemporalMetricsProcessor._otel_trace_to_span_dict(span) for span in unique
    ]

    assert len(unique) == 3
    assert [span["entity_type"] for span in converted] == ["llm", "tool", "agent"]
    assert converted[0]["input_payload"]["messages"][0]["content"] == ("Find a ferry.")
    assert converted[0]["output_payload"]["content"] == (
        "I will inspect the schedules."
    )
    assert converted[1]["entity_name"] == "read_document"
    assert converted[1]["input_payload"] == {"file_path": "schedule.txt"}
    assert converted[1]["output_payload"] == {
        "content": "No inter-city ferry is listed."
    }


def test_pure_observe_sdk_dedup_uses_entity_payloads() -> None:
    first = _observe_span(
        span_id="span-1",
        kind="llm",
        name="LLMCall",
        input_payload={"messages": [{"role": "user", "content": "Question"}]},
        output_payload={"content": "First answer"},
    )
    second = _observe_span(
        span_id="span-2",
        kind="llm",
        name="LLMCall",
        input_payload={"messages": [{"role": "user", "content": "Question"}]},
        output_payload={"content": "Second answer"},
    )

    unique = TemporalMetricsProcessor._deduplicate_spans([first, second, dict(first)])

    assert [span["SpanId"] for span in unique] == ["span-1", "span-2"]


def test_pure_observe_sdk_agent_answer_and_tool_output_are_discoverable() -> None:
    tool = _observe_span(
        span_id="span-1",
        kind="tool",
        name="read_document",
        input_payload={"file_path": "schedule.txt"},
        output_payload={"content": "No inter-city ferry is listed."},
    )
    agent = _observe_span(
        span_id="span-2",
        kind="agent",
        name="moderator",
        input_payload={"content": "Find a ferry."},
        output_payload={"final_answer": "No inter-city ferry is available."},
    )

    final_answer, span_index = (
        TemporalMetricsProcessor._extract_final_answer_from_raw_spans([tool, agent])
    )
    tool_outputs = TemporalMetricsProcessor._extract_full_tool_outputs([tool, agent])

    assert final_answer == "No inter-city ferry is available."
    assert span_index == 1
    assert "read_document" in tool_outputs
    assert "No inter-city ferry is listed." in tool_outputs
    assert TemporalMetricsProcessor._agent_span_has_routing_or_answer(agent)
