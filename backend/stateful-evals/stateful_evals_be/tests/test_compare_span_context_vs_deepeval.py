#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from stateful_evals_be.scripts.compare_span_context_vs_deepeval import (
    _assert_valid_results,
    _load_env,
    build_comparison_summary,
    build_whole_trajectory_transcript,
)


def test_whole_trajectory_transcript_deduplicates_prompts_and_preserves_io() -> None:
    materialized = {
        "spans": [
            {
                "Timestamp": "2",
                "SpanName": "ToolCall",
                "SpanAttributes": {
                    "ioa_observe.span.kind": "tool",
                    "mas.agent.id": "planner",
                    "mas.tool.name": "get_fares",
                    "ioa_observe.entity.input": '{"route_id":"AB"}',
                    "ioa_observe.entity.output": '{"fare":20}',
                },
            },
            {
                "Timestamp": "1",
                "SpanName": "LLMCall",
                "SpanAttributes": {
                    "ioa_observe.span.kind": "llm",
                    "mas.agent.id": "planner",
                    "ioa_observe.entity.input": (
                        '{"messages":[{"role":"system","content":"Use tools."},'
                        '{"role":"user","content":"Plan."}]}'
                    ),
                    "ioa_observe.entity.output": (
                        '{"tool_calls":[{"function":{"name":"get_fares"}}]}'
                    ),
                },
            },
            {
                "Timestamp": "3",
                "SpanName": "LLMCall",
                "SpanAttributes": {
                    "ioa_observe.span.kind": "llm",
                    "mas.agent.id": "planner",
                    "ioa_observe.entity.input": (
                        '{"messages":[{"role":"system","content":"Use tools."}]}'
                    ),
                    "ioa_observe.entity.output": '{"content":"Fare is $20."}',
                },
            },
        ]
    }

    transcript = build_whole_trajectory_transcript(
        materialized,
        user_input="Plan a trip.",
    )

    assert transcript.count("Use tools.") == 1
    assert "STEP 1 | TOOL CALL | agent=planner | tool=get_fares" in transcript
    assert '"route_id": "AB"' in transcript
    assert '"fare": 20' in transcript
    assert "STEP 2 | LLM RESPONSE | agent=planner" in transcript
    assert "Fare is $20." in transcript


def test_comparison_summary_reports_directional_disagreement() -> None:
    records = [
        {
            "hash": "a",
            "domain": "trip",
            "scenario": "fault",
            "span_usage": {"prompt_tokens": 10, "completion_tokens": 2},
            "traditional_usage": {"prompt_tokens": 30, "completion_tokens": 4},
            "span_context_results": [
                {
                    "high_level_metric": "Groundedness",
                    "score": 0,
                    "reasoning": "Unsupported.",
                },
                {
                    "high_level_metric": "Task Completion",
                    "score": 1,
                    "reasoning": "Complete.",
                },
            ],
            "traditional_results": [
                {
                    "high_level_metric": "Groundedness",
                    "score": 1,
                    "reasoning": "Looks supported.",
                },
                {
                    "high_level_metric": "Task Completion",
                    "score": 0,
                    "reasoning": "Incomplete.",
                },
            ],
        }
    ]

    summary, disagreements = build_comparison_summary(
        records,
        input_per_million=0.3,
        output_per_million=2.5,
    )

    assert summary["metric_verdict_pairs"] == 2
    assert summary["overall_agreement_rate"] == 0
    assert summary["overall_span_only_fail"] == 1
    assert summary["overall_traditional_only_fail"] == 1
    assert len(disagreements) == 2
    groundedness = next(
        item for item in summary["metric_summaries"] if item["metric"] == "Groundedness"
    )
    assert groundedness["span_only_fail"] == 1


def test_load_env_strips_inline_comments(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'PLAIN_KEY=secret # replaced recently\nQUOTED_VALUE="two words"\n',
        encoding="utf-8",
    )

    _load_env(env_path)

    import os

    assert os.environ["PLAIN_KEY"] == "secret"
    assert os.environ["QUOTED_VALUE"] == "two words"


def test_invalid_metric_result_fails_fast() -> None:
    with pytest.raises(RuntimeError, match="evaluation failed"):
        _assert_valid_results(
            [
                {
                    "high_level_metric": "Groundedness",
                    "score": 1,
                    "metadata": {
                        "evaluation_invalid": True,
                        "evaluation_error": "evaluation failed",
                    },
                }
            ],
            arm="span context",
        )
