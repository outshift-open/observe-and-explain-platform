#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Storage-free execution and isolation tests; no live judge calls."""

from copy import deepcopy
from threading import Barrier, Lock
from types import MappingProxyType
from unittest.mock import Mock

import pytest

from stateful_evals_be import EvaluationEngine, LLMJudgeConfig, SpanRecord
from stateful_evals_be.evaluation.processor import (
    CORE_METRICS,
    TemporalMetricsProcessor,
)
from stateful_evals_be.evaluation.span_judge import SpanJudge
from stateful_evals_be.evaluation.span_normalization import SpanNormalizer
from stateful_evals_be.models.requests import TemporalMetricOptions


def recorded_span(session_id: str) -> SpanRecord:
    return {
        "SpanId": session_id,
        "SpanName": "model.chat",
        "Timestamp": "2026-01-01T00:00:00Z",
        "SpanAttributes": {
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": f"Report the {session_id} result.",
            "gen_ai.completion.0.content": f"The {session_id} result is ready.",
        },
    }


@pytest.fixture
def offline_engine(monkeypatch):
    monkeypatch.setattr(
        TemporalMetricsProcessor, "_warm_inprocess_metric_catalog", lambda _: None
    )
    client_factory = Mock(side_effect=lambda _: Mock())
    monkeypatch.setattr(
        "stateful_evals_be.evaluation.processor.LLMClient", client_factory
    )
    config = LLMJudgeConfig(
        LLM_MODEL_NAME="test-model",
        LLM_BASE_MODEL_URL="https://example.invalid/v1",
        LLM_API_KEY="test-only",
    )
    options = TemporalMetricOptions(use_fatal_mode=False, batch_size=2)
    return (
        EvaluationEngine(llm_config=config, options=options),
        config,
        options,
        client_factory,
    )


def install_judge(monkeypatch, *, barrier=None):
    processors = []
    contexts = {}
    synchronize = TemporalMetricsProcessor._synchronize_final_answer

    def judge(processor, span, **_kwargs):
        processors.append(processor)
        tokens = 10 if span["span_id"] == "alpha" else 20
        processor._last_cross_span_usage = {
            "prompt_tokens": tokens * 10,
            "total_tokens": tokens * 10,
        }
        if barrier is not None:
            barrier.wait(timeout=5)
        return {
            "results": [
                {"metric_name": metric, "value": 1, "reasoning": "Supported."}
                for metric in CORE_METRICS
            ],
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
        }

    def capture(processor, context, spans):
        synchronize(processor, context, spans)
        contexts[spans[0]["SpanId"]] = context

    monkeypatch.setattr(TemporalMetricsProcessor, "compute_span_state_delta", judge)
    monkeypatch.setattr(TemporalMetricsProcessor, "_synchronize_final_answer", capture)
    return processors, contexts


def test_concurrent_sessions_isolate_usage_clients_and_context(
    monkeypatch, offline_engine
):
    engine, _, _, clients = offline_engine
    processors, contexts = install_judge(monkeypatch, barrier=Barrier(2))
    raw = {key: [recorded_span(key)] for key in ("alpha", "beta")}
    before = deepcopy(raw)
    summary = engine.evaluate_sessions(
        raw,
        span_loader=raw.__getitem__,
        policy_overrides={"alpha": "Check alpha.", "beta": "Check beta."},
    )

    assert summary.errors == []
    assert [result.session_id for result in summary.results] == ["alpha", "beta"]
    assert [result.token_usage.total_tokens for result in summary.results] == [110, 220]
    assert summary.total_token_usage.total_tokens == 330
    assert summary.total_token_usage.cross_span_total_tokens == 300
    assert summary.total_spans_processed == 2
    assert summary.total_sessions == 2
    assert len({id(processor) for processor in processors}) == 2
    assert len({id(processor.llm_client) for processor in processors}) == 2
    assert contexts["alpha"] is not contexts["beta"]
    assert contexts["alpha"].policy_text == "Check alpha."
    assert contexts["beta"].policy_text == "Check beta."
    assert "beta" not in contexts["alpha"].get_full_summary()
    assert "alpha" not in contexts["beta"].get_full_summary()
    assert raw == before
    assert clients.call_count == 2


def test_engine_snapshots_config_and_creates_fresh_runs(monkeypatch, offline_engine):
    engine, config, options, _ = offline_engine
    processors, _ = install_judge(monkeypatch)
    config.LLM_MODEL_NAME = "changed-by-caller"
    options.max_messages = 19
    first = engine.evaluate_spans([recorded_span("alpha")], session_id="alpha")
    processors[0].options.max_messages = 31
    processors[0].llm_config.LLM_MODEL_NAME = "changed-by-run"
    second = engine.evaluate_spans([recorded_span("alpha")], session_id="alpha")
    assert first.model_dump() == second.model_dump()
    assert processors[1].options.max_messages == 2
    assert processors[1].llm_config.LLM_MODEL_NAME == "test-model"
    assert processors[0] is not processors[1]


def test_batch_materializes_loader_before_evaluation_and_isolates_errors(
    monkeypatch, offline_engine
):
    engine, _, _, _ = offline_engine
    processors, _ = install_judge(monkeypatch)
    read_lock = Lock()

    def load(session_id):
        assert read_lock.acquire(blocking=False)
        try:
            yield recorded_span(session_id)
            if session_id == "incomplete":
                raise RuntimeError("second page failed")
        finally:
            read_lock.release()

    result = engine.evaluate_sessions(["alpha", "incomplete", "beta"], span_loader=load)
    assert [item.session_id for item in result.results] == ["alpha", "beta"]
    assert result.errors == [
        {"session_id": "incomplete", "error": "second page failed"}
    ]
    assert len(processors) == 2


def test_empty_batch_does_not_instantiate_judges(offline_engine):
    engine, _, _, clients = offline_engine
    loader = Mock(side_effect=AssertionError("no sessions to load"))
    summary = engine.evaluate_sessions([], span_loader=loader)
    assert summary.total_sessions == 0
    assert summary.total_token_usage.total_tokens == 0
    loader.assert_not_called()
    clients.assert_not_called()


def test_legacy_batch_uses_isolated_engine(monkeypatch, offline_engine):
    _, config, options, _ = offline_engine
    processors, _ = install_judge(monkeypatch, barrier=Barrier(2))
    legacy = TemporalMetricsProcessor(llm_config=config, options=options)
    legacy.fetch_spans_for_session = lambda sid: [recorded_span(sid)]
    result = legacy.run_evaluation(["alpha", "beta"])
    assert result.errors == []
    assert result.total_token_usage.total_tokens == 330
    assert all(processor is not legacy for processor in processors)


@pytest.mark.parametrize("batch", [False, True])
def test_read_only_mapping_inputs_remain_supported(monkeypatch, offline_engine, batch):
    engine, _, _, _ = offline_engine
    install_judge(monkeypatch)
    spans = [MappingProxyType(recorded_span("alpha"))]
    if batch:
        summary = engine.evaluate_sessions(["alpha"], span_loader=lambda _: spans)
        assert summary.errors == []
        result = summary.results[0]
    else:
        result = engine.evaluate_spans(spans, session_id="alpha")
    assert result.error is None
    assert result.total_spans == 1


def test_normalizer_retains_source_and_private_compatibility_alias():
    span = recorded_span("alpha")
    before = deepcopy(span)
    normalized = SpanNormalizer.normalize_span(span)
    assert normalized == TemporalMetricsProcessor._otel_trace_to_span_dict(span)
    assert normalized["span_id"] == "alpha"
    assert (
        normalized["input_payload"]["gen_ai.prompt.0.content"]
        == "Report the alpha result."
    )
    assert span == before
    assert SpanJudge.parse_response('```json\n{"metrics": []}\n```') == {"metrics": []}


def test_legacy_serial_reuse_clears_usage_left_by_failed_run(
    monkeypatch, offline_engine
):
    _, config, options, _ = offline_engine
    processor = TemporalMetricsProcessor(llm_config=config, options=options)
    processor._last_cross_span_usage = {"total_tokens": 123}
    processor._last_final_outcome_usage = {"total_tokens": 456}
    assert processor.evaluate_spans([], session_id="empty").error
    assert processor._last_cross_span_usage is None
    assert processor._last_final_outcome_usage is None
    processor.compute_span_state_delta = Mock(
        return_value={
            "results": [
                {"metric_name": metric, "value": 1, "reasoning": "Supported."}
                for metric in CORE_METRICS
            ]
        }
    )
    result = processor.evaluate_spans([recorded_span("alpha")], session_id="alpha")
    assert result.error is None
    assert result.token_usage.total_tokens == 0
