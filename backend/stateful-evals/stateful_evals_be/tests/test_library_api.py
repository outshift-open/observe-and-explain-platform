#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Library boundaries and integration parity without billed model calls."""

import json
import subprocess
import sys
from copy import deepcopy
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from stateful_evals_be import (
    LLMJudgeConfig,
    TemporalMetricOptions,
    TemporalMetricsProcessor,
    evaluate_file,
    evaluate_session,
    evaluate_spans,
    session_result_payload,
)
from stateful_evals_be.evaluation.processor import CORE_METRICS
from stateful_evals_be.integrations.oxp import (
    oxp_span_to_otel,
    fetch_session_spans,
    local_api_client,
)
from stateful_evals_be.models.requests import FailureDetail


@pytest.fixture
def config():
    return LLMJudgeConfig(LLM_MODEL_NAME="test-model", LLM_API_KEY="test-only")


@pytest.fixture
def offline_processor(monkeypatch, config):
    monkeypatch.setattr(
        TemporalMetricsProcessor, "_warm_inprocess_metric_catalog", lambda self: None
    )
    monkeypatch.setattr("stateful_evals_be.evaluation.processor.LLMClient", Mock())
    processor = TemporalMetricsProcessor(llm_config=config)
    processor.compute_span_state_delta = Mock(
        return_value={
            "results": [
                {
                    "metric_name": name,
                    "value": 1.0,
                    "reasoning": "pass",
                    "success": True,
                }
                for name in CORE_METRICS
            ],
            "failed_metrics": [],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
    )
    processor._run_unified_final_audit = Mock(
        side_effect=lambda **_: ([], [], [], [], {})
    )
    processor.fetch_spans_for_session = Mock(
        side_effect=AssertionError("must not fetch")
    )
    return processor


def span(span_id="s1", timestamp="2026-01-01T00:00:00Z"):
    return {
        "SpanId": span_id,
        "TraceId": "t1",
        "Timestamp": timestamp,
        "ServiceName": "example",
        "SpanName": "model.chat",
        "SpanAttributes": {
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": "Say hello.",
            "gen_ai.completion.0.role": "assistant",
            "gen_ai.completion.0.content": "Hello.",
        },
    }


@pytest.mark.parametrize("expected_score", [0, 1])
def test_direct_spans_match_legacy_session_payload(offline_processor, expected_score):
    fatal = FailureDetail(
        metric="Groundedness",
        metric_score=0,
        fatality_score=1,
        reasoning="Unsupported answer.",
        explanation="The final answer contradicts the supplied evidence.",
        span_id="s1",
    )
    offline_processor._run_unified_final_audit.side_effect = lambda **_: (
        [fatal] if expected_score == 0 else [],
        [],
        [],
        [],
        {},
    )
    raw = [span()]
    direct = offline_processor.evaluate_spans(raw, session_id="session")
    assert direct.error is None
    assert direct.total_spans == 1
    assert direct.trajectory_score == expected_score
    assert direct.token_usage.total_tokens == 30
    offline_processor.fetch_spans_for_session.assert_not_called()
    offline_processor.fetch_spans_for_session = Mock(return_value=raw)
    legacy = offline_processor.evaluate_session("session")
    assert session_result_payload(direct) == session_result_payload(legacy)


def test_public_function_uses_fresh_processor_and_preserves_options(
    monkeypatch, offline_processor, config
):
    constructor = Mock(return_value=offline_processor)
    monkeypatch.setattr(
        "stateful_evals_be.evaluation.engine.TemporalMetricsProcessor", constructor
    )
    options = TemporalMetricOptions(trajectory_metrics=["groundedness"])
    result = evaluate_spans(
        [span()],
        session_id="session",
        llm_config=config,
        options=options,
        policy_override="A supplied policy.",
    )
    assert result.error is None
    constructor.assert_called_once_with(llm_config=config, options=options)
    context = offline_processor._run_unified_final_audit.call_args.kwargs["traj_ctx"]
    assert context.policy_text == "A supplied policy."


def test_span_input_is_copied_and_chronologically_processed(offline_processor):
    raw = [span("later", "2026-01-02"), span("earlier", "2026-01-01")]
    raw[0]["SpanAttributes"]["gen_ai.completion.0.content"] = "Hello again."
    before = deepcopy(raw)
    result = offline_processor.evaluate_spans(iter(raw), session_id="session")
    assert result.error is None
    assert raw == before
    assert [m.span_id for m in result.span_metric_results][::3] == ["earlier", "later"]


@pytest.mark.parametrize("source_format", ["memory", "json", "sdk_jsonl"])
def test_public_api_preserves_native_peer_context_and_final_answer(
    monkeypatch, offline_processor, config, tmp_path, source_format
):
    monkeypatch.setattr(
        "stateful_evals_be.evaluation.engine.TemporalMetricsProcessor",
        Mock(return_value=offline_processor),
    )
    question = "Assess the service latency."
    policy = "Use observed evidence to assess the incident."
    first = span("peer-first", "2026-01-01T00:00:00Z")
    first["SpanName"] = "LLMCall"
    first["SpanAttributes"] = {
        "ioa_observe.span.kind": "llm",
        "ioa_observe.entity.name": "LLMCall",
        "mas.agent.id": "peer-a",
        "mas.agent.role": "peer",
        "mas.round": 1,
        "mas.operation.kind": "round_response",
        "ioa_observe.entity.input": json.dumps(
            {
                "messages": [
                    {"role": "system", "content": policy},
                    {"role": "user", "content": question},
                ]
            }
        ),
        "ioa_observe.entity.output": json.dumps({"content": "Latency is 40 ms."}),
    }
    final_answer = "The observed service latency is 40 ms."
    final = deepcopy(first)
    final.update(
        {
            "SpanId": "peer-final",
            "Timestamp": "2026-01-01T00:00:01Z",
            "Links.TraceId": ["t1"],
            "Links.SpanId": ["peer-first"],
            "Links.TraceState": [""],
            "Links.Attributes": [{"link.type": "peer_message"}],
        }
    )
    final["SpanAttributes"].update(
        {
            "mas.agent.id": "peer-b",
            "mas.round": 2,
            "mas.response.final": True,
            "ioa_observe.entity.input": json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": question},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "round": 2,
                                    "peer_answers": {"peer-a": "Latency is 40 ms."},
                                }
                            ),
                        },
                    ]
                }
            ),
            "ioa_observe.entity.output": json.dumps({"content": final_answer}),
        }
    )
    raw = [final, first]
    before = deepcopy(raw)
    if source_format == "memory":
        result = evaluate_spans(raw, session_id="peer-session", llm_config=config)
    else:
        path = tmp_path / "trace.data"
        if source_format == "json":
            path.write_text(json.dumps({"spans": raw}))
        else:
            sdk_records = []
            for item in raw:
                sdk_records.append(
                    {
                        "name": item["SpanName"],
                        "context": {
                            "span_id": item["SpanId"],
                            "trace_id": item["TraceId"],
                        },
                        "start_time": item["Timestamp"],
                        "attributes": item["SpanAttributes"],
                        "links": [
                            {
                                "context": {"span_id": linked, "trace_id": "t1"},
                                "attributes": attributes,
                            }
                            for linked, attributes in zip(
                                item.get("Links.SpanId", []),
                                item.get("Links.Attributes", []),
                            )
                        ],
                    }
                )
            path.write_text("\n".join(json.dumps(item) for item in sdk_records))
        result = evaluate_file(path, session_id="peer-session", llm_config=config)
    assert result.error is None
    assert raw == before
    offline_processor.fetch_spans_for_session.assert_not_called()
    context = offline_processor._run_unified_final_audit.call_args.kwargs["traj_ctx"]
    assert context.policy_text == policy
    assert any(
        f.fact_type == "user_statement" and f.content == question
        for f in context.evidence
    )
    assert any(c.content == "Latency is 40 ms." for c in context.claims)
    assert context.get_final_answer_context()["final_answer"] == final_answer
    peer_event = next(
        e for e in context.coordination_events if e.event_type == "peer_message"
    )
    assert peer_event.span_id == "peer-final"
    assert peer_event.linked_span_ids == ["peer-first"]
    assert peer_event.sender_agent_ids == ["peer-a"]
    assert peer_event.recipient_agent_ids == ["peer-b"]
    assert context.provenance_links


@pytest.mark.parametrize("expected_score", [0, 1])
def test_file_evaluation_matches_direct_result_and_context(
    monkeypatch, offline_processor, config, tmp_path, expected_score
):
    from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
        trajectory_context_to_payload,
    )

    monkeypatch.setattr(
        "stateful_evals_be.evaluation.engine.TemporalMetricsProcessor",
        Mock(return_value=offline_processor),
    )
    fatal = FailureDetail(
        metric="Groundedness",
        metric_score=0,
        fatality_score=1,
        reasoning="Unsupported answer.",
        explanation="The final answer contradicts the supplied evidence.",
        span_id="s1",
    )
    offline_processor._run_unified_final_audit.side_effect = lambda **_: (
        [fatal] if not expected_score else [],
        [],
        [],
        [],
        {},
    )
    raw = [span(timestamp="2026-01-01T00:00:00.000000000Z")]
    direct = evaluate_spans(raw, session_id="session", llm_config=config)
    direct_context = trajectory_context_to_payload(
        offline_processor._run_unified_final_audit.call_args.kwargs["traj_ctx"],
        schema_version="test",
        session_id="session",
    )
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps({"reward": 1 - expected_score, "spans": raw}))
    loaded = evaluate_file(path, session_id="session", llm_config=config)
    file_context = trajectory_context_to_payload(
        offline_processor._run_unified_final_audit.call_args.kwargs["traj_ctx"],
        schema_version="test",
        session_id="session",
    )
    assert direct.error is None and loaded.error is None
    assert loaded.trajectory_score == expected_score
    assert session_result_payload(loaded) == session_result_payload(direct)
    assert file_context == direct_context
    offline_processor.fetch_spans_for_session.assert_not_called()


def test_empty_input_keeps_existing_error(offline_processor):
    result = offline_processor.evaluate_spans([], session_id="empty")
    assert result.error == "No spans found for session"
    assert result.trajectory_score is None
    offline_processor.compute_span_state_delta.assert_not_called()


def test_rate_limit_does_not_refetch_or_restart_session(offline_processor):
    offline_processor._extract_system_message = Mock(
        side_effect=RuntimeError("429 rate_limit")
    )
    result = offline_processor.evaluate_spans([span()], session_id="limited")
    assert result.error == "429 rate_limit"
    offline_processor._extract_system_message.assert_called_once()
    offline_processor.fetch_spans_for_session.assert_not_called()


def test_legacy_fetch_failure_is_a_session_error(offline_processor):
    offline_processor.fetch_spans_for_session = Mock(
        side_effect=RuntimeError("retrieval failed")
    )
    result = offline_processor.evaluate_session("missing")
    assert result.error == "retrieval failed"


def test_library_and_span_normalization_need_no_api_namespace():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
sys.modules['oxp'] = None
from stateful_evals_be import EvaluationEngine, evaluate_file, evaluate_spans
from stateful_evals_be.integrations.oxp import oxp_span_to_otel
from stateful_evals_be.integrations.files import load_trajectory_file
span = oxp_span_to_otel({
    'span_id': 'span-1',
    'span_attributes': {'ioa_observe.entity.output': {'content': 'Hello.'}},
    'links_span_id': ['span-0'],
    'links_attributes': [{'relationship': 'peer_message'}],
})
assert span['SpanId'] == 'span-1'
assert span['SpanAttributes']['ioa_observe.entity.output']['content'] == 'Hello.'
assert span['Links.SpanId'] == ['span-0']
assert span['Links.Attributes'] == [{'relationship': 'peer_message'}]
""",
        ],
        check=True,
    )


def test_import_does_not_configure_logging_or_load_server():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import logging
import sys
handlers = list(logging.getLogger().handlers)
import stateful_evals_be
assert list(logging.getLogger().handlers) == handlers
assert not any(name in sys.modules for name in ('fastapi', 'uvicorn', 'dotenv'))
assert 'stateful_evals_be.evaluation.processor' not in sys.modules
""",
        ],
        check=True,
    )


def test_direct_client_normalizes_and_keeps_external_client_open():
    client = Mock(spec=["get_session_spans", "close"])
    source_span = {"span_id": "s1", "span_attributes": {"input": "complete payload"}}
    client.get_session_spans.return_value.spans = [Mock(model_dump=lambda: source_span)]
    spans = fetch_session_spans(client, "a/b")
    client.get_session_spans.assert_called_once_with(
        session_ids=["a/b"], limit=500, offset=0, order="asc"
    )
    assert spans == [oxp_span_to_otel(source_span)]
    client.close.assert_not_called()


@pytest.mark.parametrize("count", [0, 500, 501, 1000])
def test_direct_client_reads_every_page(count):
    records = [Mock(model_dump=lambda i=i: {"span_id": str(i)}) for i in range(count)]
    client = Mock(spec=["get_session_spans", "close"])
    client.get_session_spans.side_effect = lambda **kw: SimpleNamespace(
        spans=records[kw["offset"] : kw["offset"] + kw["limit"]]
    )
    result = fetch_session_spans(client, "session")
    assert [span["SpanId"] for span in result] == [str(i) for i in range(count)]
    assert client.get_session_spans.call_args_list == [
        call(session_ids=["session"], limit=500, offset=offset, order="asc")
        for offset in range(0, count + 1, 500)
    ]


def test_database_failure_does_not_evaluate_partial_session(offline_processor):
    del offline_processor.fetch_spans_for_session
    client = Mock(spec=["get_session_spans", "close"])
    client.get_session_spans.side_effect = [
        SimpleNamespace(spans=[Mock(model_dump=lambda: {"span_id": "s1"})] * 500),
        RuntimeError("database unavailable"),
    ]
    offline_processor.api_client = client
    result = offline_processor.evaluate_session("session")
    assert result.error == "database unavailable"
    offline_processor.compute_span_state_delta.assert_not_called()
    client.close.assert_not_called()


def test_public_session_api_preserves_results_and_client_ownership(
    monkeypatch, offline_processor, config
):
    del offline_processor.fetch_spans_for_session
    recorded = span()
    source = {
        "span_id": recorded["SpanId"],
        "trace_id": recorded["TraceId"],
        "timestamp": recorded["Timestamp"],
        "service_name": recorded["ServiceName"],
        "span_name": recorded["SpanName"],
        "span_attributes": recorded["SpanAttributes"],
    }
    client = Mock(spec=["get_session_spans", "close"])
    client.get_session_spans.return_value.spans = [Mock(model_dump=lambda: source)]
    offline_processor.api_client = client
    options = TemporalMetricOptions()
    constructor = Mock(return_value=offline_processor)
    monkeypatch.setattr(
        "stateful_evals_be.evaluation.engine.TemporalMetricsProcessor", constructor
    )
    actual = evaluate_session(
        "session",
        llm_config=config,
        api_client=client,
        options=options,
        policy_override="A supplied policy.",
    )
    expected = offline_processor.evaluate_spans(
        [oxp_span_to_otel(source)],
        session_id="session",
        policy_override="A supplied policy.",
    )
    assert actual.error is None
    assert session_result_payload(actual) == session_result_payload(expected)
    constructor.assert_called_once_with(llm_config=config, options=options)
    client.close.assert_not_called()


def test_default_session_retrieval_uses_local_client(offline_processor, monkeypatch):
    del offline_processor.fetch_spans_for_session
    client = Mock(spec=["get_session_spans", "close"])
    client.get_session_spans.return_value.spans = []
    closed = Mock()

    @contextmanager
    def connection():
        try:
            yield client
        finally:
            closed()

    monkeypatch.setattr(
        "stateful_evals_be.integrations.oxp.local_api_client", connection
    )
    assert offline_processor.fetch_spans_for_session("session") == []
    closed.assert_called_once()


@pytest.mark.parametrize("session_id,page_size", [("", 500), (" ", 500), ("s", 0)])
def test_invalid_session_query_does_not_touch_database(session_id, page_size):
    client = Mock(spec=["get_session_spans", "close"])
    with pytest.raises(ValueError):
        fetch_session_spans(client, session_id, page_size=page_size)
    client.get_session_spans.assert_not_called()


def test_oxp_adapter_preserves_typed_otel_links():
    source = {
        "span_id": "recipient",
        "trace_id": "trace-1",
        "links_trace_id": ["trace-1"],
        "links_span_id": ["sender"],
        "links_trace_state": [""],
        "links_attributes": [{"link.type": "peer_message"}],
    }
    normalized = oxp_span_to_otel(source)
    assert normalized == TemporalMetricsProcessor._oxp_span_to_otel_format(source)
    assert normalized["Links.TraceId"] == ["trace-1"]
    assert normalized["Links.SpanId"] == ["sender"]
    assert normalized["Links.TraceState"] == [""]
    assert normalized["Links.Attributes"] == [{"link.type": "peer_message"}]
    assert oxp_span_to_otel({})["Links.SpanId"] == []


@pytest.mark.parametrize("persist_metrics", [False, True])
def test_local_client_delegates_connection_ownership_to_api(
    monkeypatch, persist_metrics
):
    from unittest.mock import MagicMock

    factory = Mock()
    client = MagicMock()
    client.__enter__.return_value = client
    factory.from_settings.return_value = client
    monkeypatch.setitem(
        sys.modules, "oxp.client.local", SimpleNamespace(LocalClient=factory)
    )
    with pytest.raises(RuntimeError, match="query failed"):
        with local_api_client(persist_metrics=persist_metrics) as actual:
            assert actual is client
            raise RuntimeError("query failed")
    factory.from_settings.assert_called_once_with(persist_metrics=persist_metrics)
    assert client.__exit__.call_args.args[0] is RuntimeError


def test_local_client_missing_optional_dependency_has_actionable_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "oxp.client.local", None)
    with pytest.raises(ImportError, match="requires the oxp-api package"):
        with local_api_client():
            pytest.fail("must not reach a database")


@pytest.mark.parametrize("score", [0, 1])
def test_mce_library_computation_preserves_payload_and_usage(
    monkeypatch, offline_processor, score
):
    llm = Mock()
    llm.query.return_value = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10, total_tokens=30)
    )
    query = llm.query
    jury = SimpleNamespace(llms=[llm])
    jury_factory = Mock(return_value=jury)
    monkeypatch.setattr("metrics_computation_engine.llm_judge.jury.Jury", jury_factory)
    expected = {
        "metric_name": "mdt.Groundedness",
        "value": score,
        "reasoning": "Observed evidence.",
    }

    async def compute(_span, **_kwargs):
        jury.llms[0].query([{"role": "user", "content": "Judge the span."}])
        return expected

    metric = Mock(compute=AsyncMock(side_effect=compute))
    metric_class = Mock(return_value=metric)
    resolve = Mock(return_value=(metric_class, "mdt.Groundedness"))
    monkeypatch.setattr("metrics_computation_engine.util.get_metric_class", resolve)
    source = {
        "entity_type": "llm",
        "entity_name": "agent",
        "span_id": "s1",
        "app_name": "example",
        "input_payload": {"messages": [{"role": "user", "content": "A request."}]},
    }
    before = deepcopy(source)
    for _ in range(2):
        result = offline_processor.compute_span_metrics_inprocess(
            source,
            context="Prior state.",
            policy="A policy.",
            metrics=["mdt.Groundedness"],
        )
        assert result["results"] == [expected]
        assert result["failed_metrics"] == []
        assert result["usage"] == {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
        }
    jury_factory.assert_called_once()
    resolve.assert_called_with("mdt.Groundedness")
    metric_class.assert_called_with("mdt.Groundedness")
    assert metric.jury is jury
    args, kwargs = metric.compute.call_args
    assert args[0].span_id == "s1"
    assert args[0].input_payload == source["input_payload"]
    assert kwargs == {"context": "Prior state.", "policy": "A policy."}
    assert source == before
    assert (
        query.call_args.kwargs["max_tokens"]
        == offline_processor.options.span_judge_max_tokens
    )


def test_mce_library_metric_failure_remains_structured(monkeypatch, offline_processor):
    offline_processor._get_thread_jury = Mock(return_value=Mock())
    compute = AsyncMock(side_effect=[RuntimeError("metric failed"), None])
    monkeypatch.setattr(
        "metrics_computation_engine.util.get_metric_class",
        Mock(
            return_value=(Mock(return_value=Mock(compute=compute)), "mdt.Groundedness")
        ),
    )
    source = {
        "entity_type": "llm",
        "entity_name": "agent",
        "span_id": "s1",
        "app_name": "example",
    }
    for error in ("metric failed", "Metric returned None"):
        result = offline_processor.compute_span_metrics_inprocess(
            source, metrics=["mdt.Groundedness"]
        )
        assert result["results"] == []
        assert result["failed_metrics"] == [
            {"metric_name": "mdt.Groundedness", "error_message": error}
        ]


def test_processor_always_initializes_mce_library(monkeypatch, config):
    factory = Mock()
    warm = Mock()
    monkeypatch.setattr("stateful_evals_be.evaluation.processor.LLMClient", factory)
    monkeypatch.setattr(
        TemporalMetricsProcessor, "_warm_inprocess_metric_catalog", warm
    )
    processor = TemporalMetricsProcessor(llm_config=config)
    assert processor.llm_client is factory.return_value
    factory.assert_called_once_with(
        {
            "LLM_MODEL_NAME": config.LLM_MODEL_NAME,
            "LLM_BASE_MODEL_URL": config.LLM_BASE_MODEL_URL,
            "LLM_API_KEY": config.LLM_API_KEY,
        }
    )
    warm.assert_called_once()


def test_public_payload_is_json_serializable(offline_processor):
    result = offline_processor.evaluate_spans([span()], session_id="session")
    assert (
        json.loads(json.dumps(session_result_payload(result)))["session_id"]
        == "session"
    )


def test_real_local_client_database_round_trip(monkeypatch, offline_processor, config):
    """Optional API-package integration: real SQL queries, no server or model calls."""
    api_module = pytest.importorskip("oxp.client.local")
    from oxp.connectors.sqlalchemy import SQLAlchemyConnector
    from sqlalchemy import Column, Integer, MetaData, String, Table

    db = SQLAlchemyConnector("sqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "otel_traces",
        metadata,
        *(
            Column(name, String)
            for name in (
                "span_id",
                "session_id",
                "span_name",
                "timestamp",
                "status_code",
                "parent_span_id",
                "service_name",
                "span_attributes",
                "links_trace_id",
                "links_span_id",
                "links_trace_state",
                "links_attributes",
            )
        ),
        Column("duration", Integer),
    )
    try:
        metadata.create_all(db.engine)
        attributes = span()["SpanAttributes"]
        row = dict(
            span_id="s1",
            session_id="small-session",
            span_name="model.chat",
            timestamp="2026-01-01T00:00:00Z",
            status_code="OK",
            duration=1,
            parent_span_id="parent",
            service_name="example",
            span_attributes=json.dumps(attributes),
            links_trace_id='["trace"]',
            links_span_id='["peer"]',
            links_trace_state='[""]',
            links_attributes='[{"link.type":"peer_message"}]',
        )
        with db.engine.begin() as connection:
            connection.execute(
                table.insert(),
                [row]
                + [
                    {**row, "session_id": "large-session", "span_id": f"s{i:04d}"}
                    for i in reversed(range(1001))
                ],
            )
        client = api_module.LocalClient(db=db)
        loaded = fetch_session_spans(client, "large-session")
        assert [item["SpanId"] for item in loaded] == [f"s{i:04d}" for i in range(1001)]
        assert loaded[0]["SpanAttributes"] == attributes
        assert loaded[0]["ParentSpanId"] == "parent"
        assert loaded[0]["Links.SpanId"] == ["peer"]
        assert loaded[0]["Links.Attributes"] == [{"link.type": "peer_message"}]
        del offline_processor.fetch_spans_for_session
        offline_processor.api_client = client
        monkeypatch.setattr(
            "stateful_evals_be.evaluation.engine.TemporalMetricsProcessor",
            lambda **_: offline_processor,
        )
        result = evaluate_session("small-session", llm_config=config, api_client=client)
        assert result.error is None
        assert result.total_spans == 1
        assert result.trajectory_score == 1
        assert db.is_connected()
    finally:
        db.close()
