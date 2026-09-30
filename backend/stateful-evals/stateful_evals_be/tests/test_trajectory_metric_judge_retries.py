#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from types import SimpleNamespace

from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    LLMMetricJudge,
)


def _response(
    content: str,
    *,
    finish_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


class SequencedClient:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def query(self, messages: list[dict], **kwargs: object) -> SimpleNamespace:
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return self.responses.pop(0)


def test_judge_retries_truncated_json_with_larger_output_budget() -> None:
    client = SequencedClient(
        [
            _response(
                '{"score": 0, "reasoning": "truncated',
                finish_reason="length",
                prompt_tokens=100,
                completion_tokens=4096,
            ),
            _response(
                (
                    '{"score": 1, "reasoning": "passes", '
                    '"fatal_failures": [], "minor_failures": []}'
                ),
                finish_reason="stop",
                prompt_tokens=110,
                completion_tokens=30,
            ),
        ]
    )
    judge = LLMMetricJudge(
        llm_client=client,
        model_name="vertex_ai/gemini-2.5-flash",
        max_tokens=4096,
        max_attempts=3,
        retry_max_tokens=16384,
    )

    result = judge.judge(
        metric_name="Groundedness",
        rubric="Evaluate groundedness.",
        context_payload={"claims": []},
    )

    assert result["score"] == 1
    assert [call["kwargs"]["max_tokens"] for call in client.calls] == [4096, 8192]
    assert judge.last_attempt_count == 2
    assert judge.last_usage.prompt_tokens == 210
    assert judge.last_usage.completion_tokens == 4126
    assert "previous response" in client.calls[1]["messages"][-1]["content"]


def test_batch_retry_stays_within_configured_maximum() -> None:
    client = SequencedClient(
        [
            _response(
                "",
                finish_reason="length",
                prompt_tokens=50,
                completion_tokens=16384,
            ),
            _response(
                '{"metrics": []}',
                finish_reason="stop",
                prompt_tokens=60,
                completion_tokens=5,
            ),
        ]
    )
    judge = LLMMetricJudge(
        llm_client=client,
        model_name="vertex_ai/gemini-2.5-flash",
        max_tokens=8192,
        max_attempts=2,
        retry_max_tokens=16384,
    )

    result = judge.judge_batch(metrics_payload=[], shared_context={})

    assert result == {"metrics": []}
    assert [call["kwargs"]["max_tokens"] for call in client.calls] == [
        16384,
        16384,
    ]
    assert judge.last_usage.total_tokens == 16499
