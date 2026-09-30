#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Lossless export loading across harnesses, without model calls."""

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from stateful_evals_be.integrations.files import load_trajectory_file


def row(span_id="s1", trace="t1", session="session", timestamp="2026-01-01T00:00:00Z"):
    return {
        "SpanId": span_id,
        "TraceId": trace,
        "ParentSpanId": "parent",
        "SpanName": "model.chat",
        "Timestamp": timestamp,
        "SpanAttributes": {
            "session.id": session,
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": "Find the morning trains.",
            "gen_ai.completion.0.content": "The first train leaves at 09:00.",
        },
    }


def sdk_span():
    return {
        "name": "model.chat",
        "context": {"span_id": "0x02", "trace_id": "0x01", "trace_state": "[]"},
        "parent_id": "0x03",
        "start_time": "2026-01-01T00:00:00.000000001Z",
        "end_time": "2026-01-01T00:00:00.000000003Z",
        "status": {"status_code": "OK"},
        "resource": {"attributes": {"service.name": "example-app"}},
        "attributes": {
            "session.id": "session",
            "ioa_observe.span.kind": "llm",
            "ioa_observe.entity.input": {
                "messages": [{"role": "user", "content": "full message " * 2000}],
                "tools": [{"type": "function", "function": {"name": "lookup"}}],
            },
            "ioa_observe.entity.output": {"content": "The complete answer."},
        },
        "links": [
            {
                "context": {"span_id": "0x04", "trace_id": "0x01", "trace_state": "[]"},
                "attributes": {"link.type": "peer_message", "message.id": "message-1"},
            }
        ],
    }


def write_export(tmp_path, payload, *, jsonl=False):
    path = tmp_path / "arbitrary-name.data"
    text = (
        "\n\n".join(json.dumps(item) for item in payload)
        if jsonl
        else json.dumps(payload, indent=2)
    )
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("container", ["array", "envelope", "jsonl", "single"])
def test_common_containers_preserve_span_content(tmp_path, container):
    source = row()
    payload = (
        {"spans": [source]}
        if container == "envelope"
        else source
        if container == "single"
        else [source]
    )
    path = write_export(tmp_path, payload, jsonl=container == "jsonl")
    before = path.read_bytes()
    session, spans = load_trajectory_file(path)
    assert session == "session"
    assert spans[0]["SpanAttributes"] == source["SpanAttributes"]
    assert spans[0]["ParentSpanId"] == "parent"
    assert spans[0]["SpanId"] == "s1"
    assert path.read_bytes() == before


def test_sdk_jsonl_preserves_messages_tools_ids_links_and_duration(tmp_path):
    source = sdk_span()
    session, spans = load_trajectory_file(write_export(tmp_path, [source], jsonl=True))
    span = spans[0]
    assert session == "session"
    assert span["SpanAttributes"] == source["attributes"]
    assert span["SpanId"] == "0x02"
    assert span["ParentSpanId"] == "0x03"
    assert span["TraceId"] == "0x01"
    assert span["Timestamp"] == source["start_time"]
    assert span["Duration"] == 2
    assert span["ServiceName"] == "example-app"
    assert span["links"] == source["links"]
    assert span["Links.SpanId"] == ["0x04"]
    assert span["Links.Attributes"] == [source["links"][0]["attributes"]]
    assert not any(key.startswith("mas.") for key in span["SpanAttributes"])


def test_noa_raw_spans_win_and_labels_are_not_evaluation_input(tmp_path):
    original = row()
    original.update(
        LinksSpanId=["peer"],
        LinksTraceId=["t2"],
        LinksTraceState=[""],
        LinksAttributes=[{"link.type": "delegation"}],
    )
    entity = {
        "span_id": "s1",
        "trace_id": "t1",
        "entity_type": "llm",
        "entity_name": "model",
        "session_id": "session",
        "raw_span_data": original,
        "input_payload": {"gen_ai.prompt.0.content": "shorter derived prompt"},
        "output_payload": {"gen_ai.completion.0.content": "shorter answer"},
    }
    session, spans = load_trajectory_file(
        write_export(
            tmp_path,
            {
                "id": "export-id",
                "reward": 0,
                "expected_output": "DO NOT LEAK",
                "metadata": {"ground_truth": "DO NOT LEAK"},
                "spans": [entity],
            },
        )
    )
    assert session == "session"
    for key, value in original["SpanAttributes"].items():
        assert spans[0]["SpanAttributes"][key] == value
    assert spans[0]["Links.Attributes"] == original["LinksAttributes"]
    assert "DO NOT LEAK" not in json.dumps(spans)
    assert "reward" not in spans[0]


@pytest.mark.parametrize("nested", [True, False])
def test_entity_payload_without_raw_preserves_both_message_formats(tmp_path, nested):
    input_payload = (
        {"messages": [{"role": "user", "content": "Find a route."}]}
        if nested
        else {"gen_ai.prompt.0.content": "Find a route."}
    )
    output_payload = (
        {"content": "Route A", "tool_calls": []}
        if nested
        else {"gen_ai.completion.0.content": "Route A"}
    )
    record = {
        "span_id": "s1",
        "entity_type": "llm",
        "entity_name": "model",
        "timestamp": "2026-01-01T00:00:00Z",
        "input_payload": input_payload,
        "output_payload": output_payload,
        "tool_definition": [{"name": "search", "parameters": {}}],
    }
    session, spans = load_trajectory_file(
        write_export(tmp_path, {"id": "trajectory", "spans": [record]})
    )
    attrs = spans[0]["SpanAttributes"]
    assert session == "trajectory"
    if nested:
        assert attrs["traceloop.entity.input"] == input_payload
        assert attrs["traceloop.entity.output"] == output_payload
    else:
        assert attrs["gen_ai.prompt.0.content"] == "Find a route."
        assert attrs["gen_ai.completion.0.content"] == "Route A"
    assert attrs["tool_definition"] == record["tool_definition"]


def test_api_export_preserves_links(tmp_path):
    source = {
        "span_id": "s1",
        "span_name": "search.tool",
        "timestamp": "2026-01-01 00:00:00.000000001",
        "session_id": "session",
        "span_attributes": {"traceloop.entity.output": {"result": 0}},
        "links_span_id": ["s0"],
        "links_trace_id": ["t1"],
        "links_trace_state": [""],
        "links_attributes": [{"link.type": "pipeline_handoff"}],
    }
    session, spans = load_trajectory_file(write_export(tmp_path, {"spans": [source]}))
    assert session == "session"
    assert spans[0]["Links.Attributes"] == source["links_attributes"]
    assert spans[0]["SpanAttributes"] == source["span_attributes"]


def test_sorting_normalizes_timezones_and_preserves_nanoseconds(tmp_path):
    later = row("later", timestamp="2026-01-01T01:00:00.000000002+01:00")
    earlier = row("earlier", timestamp="2025-12-31T19:00:00.000000001-05:00")
    _, spans = load_trajectory_file(write_export(tmp_path, [later, earlier]))
    assert [s["SpanId"] for s in spans] == ["earlier", "later"]
    assert spans[0]["Timestamp"] == "2026-01-01T00:00:00.000000001Z"
    assert spans[1]["Timestamp"] == "2026-01-01T00:00:00.000000002Z"


def test_single_session_can_contain_many_traces(tmp_path):
    session, spans = load_trajectory_file(
        write_export(tmp_path, [row("s1", "t1"), row("s2", "t2")])
    )
    assert session == "session"
    assert len(spans) == 2


@pytest.mark.parametrize("override", [None, "do-not-merge"])
def test_multiple_sessions_rejected_even_with_override(tmp_path, override):
    path = write_export(tmp_path, [row(), row("s2", session="other")])
    with pytest.raises(ValueError, match="multiple session IDs"):
        load_trajectory_file(path, session_id=override)


def test_unidentified_traces_are_not_combined(tmp_path):
    records = [row("s1", "t1"), row("s2", "t2")]
    for item in records:
        del item["SpanAttributes"]["session.id"]
    with pytest.raises(ValueError, match="Multiple traces"):
        load_trajectory_file(write_export(tmp_path, records), session_id="not-a-merge")


def test_identity_fallbacks_and_explicit_override(tmp_path):
    source = row()
    del source["SpanAttributes"]["session.id"]
    path = write_export(tmp_path, [source])
    assert load_trajectory_file(path)[0] == "t1"
    source["TraceId"] = ""
    path = write_export(tmp_path, [source])
    with pytest.raises(ValueError, match="supply session_id"):
        load_trajectory_file(path)
    assert load_trajectory_file(path, session_id="explicit")[0] == "explicit"


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "no spans"),
        ({"spans": {}}, "must be an array"),
        ([{"event": "execution_start"}], "Unsupported span schema"),
        ([None], "must be an object"),
        ([dict(row(), SpanId="")], "span ID"),
        ([dict(row(), Timestamp="")], "timestamp"),
        ([dict(row(), SpanAttributes=[])], "must be an object"),
        (
            [dict(row(), **{"Links.SpanId": ["s0"], "Links.Attributes": []})],
            "matching lengths",
        ),
        ([row("s1", "t1"), row("s1", "t2")], "same span ID"),
    ],
)
def test_invalid_exports_fail_before_evaluation(tmp_path, payload, message):
    with pytest.raises(ValueError, match=message):
        load_trajectory_file(write_export(tmp_path, payload))


def test_malformed_jsonl_reports_line(tmp_path):
    path = write_export(tmp_path, [row(), row("s2")], jsonl=True)
    path.write_text(path.read_text() + '\n{"broken":')
    with pytest.raises(ValueError, match="line 4"):
        load_trajectory_file(path)


def test_raw_span_id_mismatch_is_rejected(tmp_path):
    entity = {"span_id": "wrong", "entity_type": "llm", "raw_span_data": row()}
    with pytest.raises(ValueError, match="disagrees"):
        load_trajectory_file(write_export(tmp_path, {"spans": [entity]}))


def test_native_raw_messages_take_precedence_over_derived_flat_messages(tmp_path):
    raw = sdk_span()
    entity = {
        "span_id": raw["context"]["span_id"],
        "entity_type": "llm",
        "raw_span_data": raw,
        "input_payload": {"gen_ai.prompt.0.content": "shorter derived prompt"},
        "output_payload": {"gen_ai.completion.0.content": "shorter derived answer"},
    }
    _, spans = load_trajectory_file(write_export(tmp_path, {"spans": [entity]}))
    attrs = spans[0]["SpanAttributes"]
    assert "gen_ai.prompt.0.content" not in attrs
    assert "gen_ai.completion.0.content" not in attrs
    assert (
        attrs["ioa_observe.entity.input"]
        == raw["attributes"]["ioa_observe.entity.input"]
    )
    assert (
        attrs["ioa_observe.entity.output"]
        == raw["attributes"]["ioa_observe.entity.output"]
    )


def test_conflicting_envelope_session_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="envelope session ID disagrees"):
        load_trajectory_file(
            write_export(tmp_path, {"session_id": "other", "spans": [row()]})
        )


def test_evaluate_file_forwards_options_and_returns_existing_result(
    tmp_path, monkeypatch
):
    from stateful_evals_be import LLMJudgeConfig, TemporalMetricOptions, evaluate_file
    from stateful_evals_be.models.requests import SessionResult

    result = SessionResult(session_id="override", trajectory_score=1)
    evaluate = Mock(return_value=result)
    monkeypatch.setattr("stateful_evals_be.api.evaluate_spans", evaluate)
    config = LLMJudgeConfig(LLM_MODEL_NAME="test-model", LLM_API_KEY="test-only")
    options = TemporalMetricOptions(trajectory_metrics=["groundedness"])
    path = write_export(tmp_path, [sdk_span()], jsonl=True)
    actual = evaluate_file(
        path,
        llm_config=config,
        session_id="override",
        options=options,
        policy_override="Policy.",
    )
    assert actual is result
    assert evaluate.call_args.kwargs == dict(
        session_id="override",
        llm_config=config,
        options=options,
        policy_override="Policy.",
    )
    assert evaluate.call_args.args[0][0]["SpanAttributes"] == sdk_span()["attributes"]
    evaluate.reset_mock()
    with pytest.raises(ValueError):
        evaluate_file(write_export(tmp_path, []), llm_config=config)
    evaluate.assert_not_called()


def test_missing_file_is_not_hidden(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_trajectory_file(tmp_path / "absent.json")


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n\n")
    with pytest.raises(ValueError, match="empty"):
        load_trajectory_file(path)


def test_loader_does_not_mutate_embedded_records(tmp_path):
    source = sdk_span()
    original = deepcopy(source)
    load_trajectory_file(write_export(tmp_path, [source], jsonl=True))
    assert source == original
