#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
from types import SimpleNamespace

from stateful_evals_be.evaluation.processor import (
    CORE_METRICS,
    TemporalMetricsProcessor,
)
from stateful_evals_be.models.requests import TemporalMetricOptions
from stateful_evals_be.models.requests import FailureDetail


class FakeCombinedClient:
    def __init__(self) -> None:
        self.calls = []

    def query(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "metrics": [
                                    {
                                        "metric_name": metric,
                                        "score": 1,
                                        "reasoning": "pass",
                                    }
                                    for metric in CORE_METRICS
                                ],
                                "state_delta": {"claims": []},
                            }
                        )
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=90,
                completion_tokens=30,
                total_tokens=120,
            ),
        )


class RetryCombinedClient:
    def __init__(self) -> None:
        self.calls = []

    def query(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if len(self.calls) == 1:
            metrics = CORE_METRICS[:-1]
            completion_tokens = 10
        else:
            metrics = json.loads(messages[1]["content"])["requested_metrics"]
            completion_tokens = 30
        content = json.dumps(
            {
                "metrics": [
                    {
                        "metric_name": metric,
                        "score": 1,
                        "reasoning": "pass",
                    }
                    for metric in metrics
                ],
                "state_delta": {"claims": []},
            }
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(
                prompt_tokens=90,
                completion_tokens=completion_tokens,
                total_tokens=90 + completion_tokens,
            ),
        )


class PerMetricFallbackClient:
    def __init__(self) -> None:
        self.calls = []

    def query(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        requested = json.loads(messages[1]["content"])["requested_metrics"]
        metrics = [] if len(self.calls) <= 3 else requested
        content = json.dumps(
            {
                "metrics": [
                    {
                        "metric_name": metric.replace(
                            "IntentRecognition", "Intent Recognition"
                        ),
                        "score": "pass",
                        "reasoning": "pass",
                    }
                    for metric in metrics
                ]
            }
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(
                prompt_tokens=90,
                completion_tokens=10,
                total_tokens=100,
            ),
        )


def _processor() -> TemporalMetricsProcessor:
    processor = object.__new__(TemporalMetricsProcessor)
    processor.options = TemporalMetricOptions(max_messages=2)
    processor.metric_names = list(CORE_METRICS)
    processor.llm_client = FakeCombinedClient()
    return processor


def _span() -> dict:
    return {
        "span_id": "span-1",
        "entity_type": "llm",
        "entity_name": "assistant",
        "input_payload": {
            "gen_ai.prompt.0.role": "system",
            "gen_ai.prompt.0.content": "very large system contract",
            "gen_ai.prompt.1.role": "user",
            "gen_ai.prompt.1.content": "old request that must not be resent",
            "gen_ai.prompt.2.role": "assistant",
            "gen_ai.prompt.2.content": "previous response",
            "gen_ai.prompt.3.role": "user",
            "gen_ai.prompt.3.content": "current request",
        },
        "output_payload": {
            "gen_ai.completion.0.content": "current answer",
        },
        "contains_error": False,
    }


def test_compact_span_delta_excludes_system_and_old_history() -> None:
    processor = _processor()

    delta = processor._compact_span_delta(_span())

    serialized = json.dumps(delta)
    assert "very large system contract" not in serialized
    assert "old request that must not be resent" not in serialized
    assert "current request" in serialized
    assert len(delta["current_input"]) == 2


def test_combined_span_judge_returns_three_metrics_from_one_call() -> None:
    processor = _processor()

    result = processor.compute_span_state_delta(
        _span(),
        context_state={"intents": [], "facts": [], "recent_claims": []},
        policy="single policy copy",
        metrics=list(CORE_METRICS),
    )

    assert len(processor.llm_client.calls) == 1
    assert len(result["results"]) == 3
    assert result["usage"]["total_tokens"] == 120
    call = processor.llm_client.calls[0]
    assert call["kwargs"]["max_tokens"] == 1200
    assert call["messages"][1]["content"].count("single policy copy") == 1


def test_combined_span_judge_retries_omitted_metrics_and_counts_usage() -> None:
    processor = _processor()
    processor.llm_client = RetryCombinedClient()

    result = processor.compute_span_state_delta(
        _span(),
        context_state={"intents": [], "facts": [], "recent_claims": []},
        policy="single policy copy",
        metrics=list(CORE_METRICS),
    )

    assert len(processor.llm_client.calls) == 2
    assert len(result["results"]) == 3
    assert result["failed_metrics"] == []
    assert result["usage"] == {
        "prompt_tokens": 180,
        "completion_tokens": 40,
        "total_tokens": 220,
    }
    assert [call["kwargs"]["max_tokens"] for call in processor.llm_client.calls] == [
        1200,
        2400,
    ]
    assert (
        "previous response omitted"
        in (processor.llm_client.calls[1]["messages"][-1]["content"])
    )
    assert json.loads(processor.llm_client.calls[1]["messages"][1]["content"])[
        "requested_metrics"
    ] == [CORE_METRICS[-1]]


def test_combined_span_judge_falls_back_to_one_call_per_missing_metric() -> None:
    processor = _processor()
    processor.llm_client = PerMetricFallbackClient()

    result = processor.compute_span_state_delta(
        _span(),
        context_state={"intents": [], "facts": [], "recent_claims": []},
        policy="single policy copy",
        metrics=list(CORE_METRICS),
    )

    assert len(processor.llm_client.calls) == 6
    assert len(result["results"]) == 3
    assert result["failed_metrics"] == []
    assert result["usage"]["total_tokens"] == 600


def test_evaluate_session_uses_one_unified_final_audit_and_accounts_for_it() -> None:
    processor = _processor()
    processor.options = TemporalMetricOptions(use_fatal_mode=True)
    processor.llm_config = SimpleNamespace(LLM_MODEL_NAME="gpt-4o")
    raw_span = {
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
    processor.fetch_spans_for_session = lambda _session_id: [raw_span]
    processor.compute_span_state_delta = lambda *args, **kwargs: {
        "results": [
            {
                "metric_name": metric,
                "value": 1.0,
                "reasoning": "pass",
                "success": True,
            }
            for metric in CORE_METRICS
        ],
        "failed_metrics": [],
        "usage": {
            "prompt_tokens": 90,
            "completion_tokens": 30,
            "total_tokens": 120,
        },
    }
    audit_calls = []

    def unified_audit(**kwargs):
        audit_calls.append(kwargs)
        return (
            [],
            [],
            [],
            [
                {
                    "high_level_metric": "Task Completeness",
                    "score": 1,
                    "reasoning": "pass",
                    "fatal_failures": [],
                    "minor_failures": [],
                    "metadata": {},
                }
            ],
            {
                "prompt_tokens": 400,
                "completion_tokens": 100,
                "total_tokens": 500,
            },
        )

    processor._run_unified_final_audit = unified_audit
    processor._cross_validate_final_answer = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("legacy cross-span review must not run")
    )
    processor._review_final_outcome = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("legacy final-outcome review must not run")
    )

    result = processor.evaluate_session("session-1")

    assert len(audit_calls) == 1
    assert result.error is None
    assert result.token_usage.mce_total_tokens == 120
    assert result.token_usage.high_level_total_tokens == 500
    assert result.token_usage.total_tokens == 620
    assert result.token_usage.review_total_tokens == 0
    assert result.token_usage.cross_span_total_tokens == 0
    assert result.token_usage.final_outcome_total_tokens == 0
    assert [item["high_level_metric"] for item in result.high_level_metrics] == [
        "Task Completeness",
        "Correctness",
    ]


def test_paper_suite_keeps_diagnostic_failure_without_failing_outcome() -> None:
    processor = _processor()
    processor.options = TemporalMetricOptions(
        use_fatal_mode=True,
        high_level_metric_suite="paper_v1",
    )
    processor.llm_config = SimpleNamespace(LLM_MODEL_NAME="gpt-4o")
    raw_span = {
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
    processor.fetch_spans_for_session = lambda _session_id: [raw_span]
    processor.compute_span_state_delta = lambda *args, **kwargs: {
        "results": [
            {
                "metric_name": metric,
                "value": 1.0,
                "reasoning": "pass",
                "success": True,
            }
            for metric in CORE_METRICS
        ],
        "failed_metrics": [],
        "usage": {},
    }
    diagnostic = FailureDetail(
        metric="Policy Safety",
        metric_score=0.0,
        fatality_score=0.9,
        reasoning="The policy suppresses verification.",
        explanation="Configuration-level diagnostic.",
        observed_impact="unsafe_policy",
        confidence=0.9,
        affects_trajectory_score=False,
    )
    processor._run_unified_final_audit = lambda **kwargs: (
        [diagnostic],
        [],
        [],
        [
            {
                "high_level_metric": "Policy Safety",
                "score": 0,
                "reasoning": diagnostic.reasoning,
                "fatal_failures": [],
                "minor_failures": [],
                "metadata": {
                    "metric_suite": "paper_v1",
                    "affects_trajectory_score": False,
                },
            }
        ],
        {},
    )

    result = processor.evaluate_session("session-paper")

    assert result.error is None
    assert result.high_level_metric_suite == "paper_v1"
    assert result.trajectory_score == 1
    assert len(result.fatal_failures) == 1
    assert result.fatal_failures[0].metric == "Policy Safety"
    assert result.fatal_failures[0].affects_trajectory_score is False
    assert [item["high_level_metric"] for item in result.high_level_metrics] == [
        "Policy Safety"
    ]


def test_configured_trajectory_metric_failure_is_additive_to_correctness() -> None:
    processor = _processor()
    processor.options = TemporalMetricOptions(
        use_fatal_mode=True,
        trajectory_metrics=["policy_safety"],
    )
    processor.llm_config = SimpleNamespace(LLM_MODEL_NAME="gpt-4o")
    raw_span = {
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
    processor.fetch_spans_for_session = lambda _session_id: [raw_span]
    processor.compute_span_state_delta = lambda *args, **kwargs: {
        "results": [
            {
                "metric_name": metric,
                "value": 1.0,
                "reasoning": "pass",
                "success": True,
            }
            for metric in CORE_METRICS
        ],
        "failed_metrics": [],
        "usage": {},
    }
    processor._run_unified_final_audit = lambda **kwargs: ([], [], [], [], {})
    configured_calls = []

    def configured_metrics(**kwargs):
        configured_calls.append(kwargs)
        return (
            [
                {
                    "high_level_metric": "Policy Safety",
                    "score": 0,
                    "reasoning": "The configured policy suppresses verification.",
                    "fatal_failures": [],
                    "minor_failures": [],
                    "metadata": {
                        "metric_code": "policy_safety",
                        "metric_set": "trajectory_v1",
                        "affects_trajectory_score": False,
                    },
                }
            ],
            {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
        )

    processor._run_configured_trajectory_metrics = configured_metrics

    result = processor.evaluate_session("session-configured-metrics")

    assert len(configured_calls) == 1
    assert configured_calls[0]["trajectory_score"] == 1
    assert configured_calls[0]["fatal_failures"] == []
    assert result.error is None
    assert result.trajectory_score == 1
    assert result.fatal_failures == []
    assert result.trajectory_metric_set == "trajectory_v1"
    assert [item["high_level_metric"] for item in result.trajectory_metrics] == [
        "Policy Safety"
    ]
    assert result.trajectory_metrics[0]["score"] == 0
    assert result.token_usage.high_level_total_tokens == 30
