#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Span-level 1-5 rubric scoring, pass threshold and per-metric evaluation cost."""

import json
from types import SimpleNamespace

import pytest

from stateful_evals_be.evaluation.cost_estimator import estimate_usage_cost_usd
from stateful_evals_be.evaluation.processor import (
    CORE_METRICS,
    TemporalMetricsProcessor,
)
from stateful_evals_be.evaluation.span_judge import SpanJudge
from stateful_evals_be.models.requests import TemporalMetricOptions

_SPAN = {
    "span_id": "span-1",
    "entity_type": "llm",
    "entity_name": "assistant",
    "input_payload": {
        "gen_ai.prompt.0.role": "user",
        "gen_ai.prompt.0.content": "current request",
    },
    "output_payload": {"gen_ai.completion.0.content": "current answer"},
    "contains_error": False,
}
_CONTEXT = {"intents": [], "facts": [], "recent_claims": []}


def _response(content: str, prompt: int = 10, completion: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


def _judge(scores: dict) -> SpanJudge:
    content = json.dumps(
        {
            "metrics": [
                {"metric_name": name, "score": score, "reasoning": "r"}
                for name, score in scores.items()
            ]
        }
    )
    return SpanJudge(
        query=lambda messages, **kwargs: _response(content),
        options=TemporalMetricOptions(span_judge_max_attempts=1),
        metric_names=list(scores),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1, 1),
        (5, 5),
        ("4", 4),
        (3.4, 3),
        (0, 1),
        (9, 5),
        ("pass", 5),
        ("fail", 1),
        (True, 5),
        (None, None),
        ("n/a", None),
        (float("nan"), None),
    ],
)
def test_parse_rubric_score_is_tolerant_and_clamped(raw, expected) -> None:
    assert SpanJudge.parse_rubric_score(raw) == expected


def test_judge_normalizes_rubric_scores_to_unit_interval() -> None:
    scores = {"Groundedness": 1, "IntentRecognition": 3, "Relevancy": "5"}

    out = _judge(scores).evaluate(_SPAN, context_state=_CONTEXT)

    by_name = {item["metric_name"]: item for item in out["results"]}
    assert by_name["Groundedness"]["value"] == 0.0
    assert by_name["IntentRecognition"]["value"] == 0.5
    assert by_name["Relevancy"]["value"] == 1.0
    assert by_name["IntentRecognition"]["raw_score"] == 3
    assert out["failed_metrics"] == []


def test_judge_rejects_missing_score() -> None:
    content = json.dumps({"metrics": [{"metric_name": "Relevancy"}]})
    judge = SpanJudge(
        query=lambda messages, **kwargs: _response(content),
        options=TemporalMetricOptions(span_judge_max_attempts=1),
        metric_names=["Relevancy"],
    )

    out = judge.evaluate(_SPAN, context_state=_CONTEXT)

    assert out["results"] == []
    assert [f["metric_name"] for f in out["failed_metrics"]] == ["Relevancy"]


def test_pass_threshold_option_defaults_to_half() -> None:
    assert TemporalMetricOptions().span_pass_threshold == 0.5


# ---------------------------------------------------------------------------
# Intent resolution
# ---------------------------------------------------------------------------


def _events(*scores: float) -> list:
    return [
        {
            "score": score,
            "span_index": index,
            "span_type": "tool",
            "entity_name": "lookup",
            "reasoning": "",
            "output_payload": {"x": "data"},
        }
        for index, score in enumerate(scores)
    ]


@pytest.mark.parametrize(
    ("scores", "threshold", "state"),
    [
        ((0.25,), 0.5, "dormant"),
        ((0.25, 0.25), 0.5, "drifting"),
        ((0.25, 0.5), 0.5, "fulfilled"),
        ((0.25, 0.75), 0.5, "fulfilled"),
        ((0.5, 0.5), 0.75, "drifting"),
        ((0.5, 0.75), 0.75, "fulfilled"),
    ],
)
def test_intent_state_uses_pass_threshold(scores, threshold, state) -> None:
    states = TemporalMetricsProcessor._resolve_intent_states(
        _events(*scores), 10, threshold
    )

    assert states[0].state == state


def test_unsatisfied_intents_count_only_below_threshold() -> None:
    weak = TemporalMetricsProcessor._resolve_intent_states(_events(0.25, 0.25), 10, 0.5)
    passing = TemporalMetricsProcessor._resolve_intent_states(
        _events(0.25, 0.5), 10, 0.5
    )

    assert TemporalMetricsProcessor._count_unsatisfied_intents(weak, 0.5) == 1
    assert TemporalMetricsProcessor._count_unsatisfied_intents(passing, 0.5) == 0


# ---------------------------------------------------------------------------
# Session: failures, expansion trigger, usage split
# ---------------------------------------------------------------------------

_RAW_SPAN = {
    "SpanId": "1",
    "TraceId": "trace-1",
    "ParentSpanId": "",
    "Timestamp": "2024-01-01T00:00:00Z",
    "ServiceName": "test-app",
    "SpanName": "model.chat",
    "StatusCode": "OK",
    "SpanAttributes": {
        "gen_ai.prompt.0.role": "system",
        "gen_ai.prompt.0.content": "Answer the user's request.",
        "gen_ai.prompt.1.role": "user",
        "gen_ai.prompt.1.content": "Say hello.",
        "gen_ai.completion.0.role": "assistant",
        "gen_ai.completion.0.content": "Hello.",
    },
}


def _session_processor(values: dict, usages: list, **options):
    processor = object.__new__(TemporalMetricsProcessor)
    processor.options = TemporalMetricOptions(**options)
    processor.metric_names = list(CORE_METRICS)
    processor.llm_config = SimpleNamespace(LLM_MODEL_NAME="gpt-4o")
    processor.fetch_spans_for_session = lambda _session_id: [_RAW_SPAN]
    calls = []

    def judge(*args, **kwargs):
        calls.append(kwargs)
        usage = usages[min(len(calls), len(usages)) - 1]
        return {
            "results": [
                {
                    "metric_name": name,
                    "value": value,
                    "raw_score": round(value * 4 + 1),
                    "reasoning": "r",
                    "success": True,
                }
                for name, value in values.items()
            ],
            "failed_metrics": [],
            "usage": usage,
        }

    processor.compute_span_state_delta = judge

    def audit(**kwargs):
        calls_audit.append(kwargs)
        return [], [], [], [], {}

    calls_audit: list = []
    processor._run_unified_final_audit = audit
    processor.audit_calls = calls_audit
    return processor, calls


_USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def _failed_metrics(processor) -> list:
    (audit_call,) = processor.audit_calls
    return [f.metric_name for f in audit_call["failures"]]


@pytest.mark.parametrize(
    ("value", "fails"), [(0.0, True), (0.25, True), (0.5, False), (0.75, False)]
)
def test_span_failure_requires_value_below_threshold(value, fails) -> None:
    values = {name: 1.0 for name in CORE_METRICS}
    values["Groundedness"] = value
    processor, _ = _session_processor(values, [_USAGE])

    processor.evaluate_session("session-1")

    assert (_failed_metrics(processor) == ["Groundedness"]) is fails
    assert fails or _failed_metrics(processor) == []


def test_custom_threshold_changes_pass_boundary() -> None:
    values = {name: 1.0 for name in CORE_METRICS}
    values["Groundedness"] = 0.5
    processor, _ = _session_processor(values, [_USAGE], span_pass_threshold=0.75)

    processor.evaluate_session("session-1")

    assert _failed_metrics(processor) == ["Groundedness"]


@pytest.mark.parametrize(("value", "expected_calls"), [(0.25, 2), (0.5, 1)])
def test_expansion_triggers_only_below_threshold(
    monkeypatch, value, expected_calls
) -> None:
    from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext

    values = {name: 1.0 for name in CORE_METRICS}
    values["Groundedness"] = value
    processor, calls = _session_processor(values, [_USAGE])
    real_retrieve = TrajectoryContext.retrieve_for_span

    def retrieve(self, *args, **kwargs):
        state = real_retrieve(self, *args, **kwargs)
        state["selection"]["omitted_artifacts"] = ["older"]
        return state

    monkeypatch.setattr(TrajectoryContext, "retrieve_for_span", retrieve)

    processor.evaluate_session("session-1")

    assert len(calls) == expected_calls


def test_span_usage_is_split_evenly_and_sums_to_call_usage() -> None:
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    processor, _ = _session_processor({n: 1.0 for n in CORE_METRICS}, [usage])

    result = processor.evaluate_session("session-1")

    metrics = result.span_metric_results
    assert len(metrics) == len(CORE_METRICS) == 3
    assert sum(m.evaluation_prompt_tokens for m in metrics) == 100
    assert sum(m.evaluation_completion_tokens for m in metrics) == 20
    assert sum(m.evaluation_total_tokens for m in metrics) == 120
    assert [m.evaluation_prompt_tokens for m in metrics] == [34, 33, 33]
    assert all(m.evaluation_model == "gpt-4o" for m in metrics)
    assert sum(m.evaluation_cost_usd for m in metrics) == pytest.approx(
        estimate_usage_cost_usd(100, 20, "gpt-4o")
    )
    assert metrics[0].raw_score == 5


def test_auto_failed_error_span_has_no_evaluation_usage() -> None:
    raw = {**_RAW_SPAN, "StatusCode": "ERROR"}
    processor, calls = _session_processor({n: 1.0 for n in CORE_METRICS}, [_USAGE])
    processor.fetch_spans_for_session = lambda _session_id: [raw]

    result = processor.evaluate_session("session-1")

    assert calls == []
    assert {m.score for m in result.span_metric_results} == {0.0}
    assert all(m.evaluation_total_tokens is None for m in result.span_metric_results)


def test_usage_cost_helper_falls_back_to_default_model() -> None:
    known = estimate_usage_cost_usd(1000, 500, "gpt-4o")
    assert known > 0
    assert estimate_usage_cost_usd(1000, 500, "no-such-model") == known
