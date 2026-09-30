#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from unittest.mock import patch

from mce.providers.native.metrics.safety.completion_rate import CompletionRate
from mce.providers.native.metrics.safety.llm_error_rate import LLMErrorRate
from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
    ToolUtilizationAccuracy,
)


class TestSessionHealthMetrics:
    def test_llm_error_rate_declares_retrieval_requirements(self):
        reqs = LLMErrorRate().input_requirements

        assert reqs.retrieval is not None
        assert reqs.retrieval.nodes[0].alias == "llm_spans"
        assert [edge.relation_type for edge in reqs.retrieval.edges] == [
            "hasMASCalls",
            "hasAgentCalls",
            "invokesLLM",
        ]

    def test_llm_error_rate_counts_failed_llm_calls_from_raw_fields(self):
        result = LLMErrorRate().compute(
            "s1",
            {
                "llm_spans": [
                    {"executionId": "l1", "status": "ERROR"},
                    {"executionId": "l2", "error": "timeout"},
                    {"executionId": "l3", "status": "OK"},
                ]
            },
        )

        assert result.value == 2 / 3
        assert result.metadata["error_count"] == 2

    def test_completion_rate_returns_binary_value_for_single_session(self):
        result = CompletionRate().compute(
            "s1",
            {
                "llm_spans": [{"executionId": "l1", "status": "ERROR"}],
                "tool_spans": [],
            },
        )

        assert result.value == 0.0
        assert result.metadata["completion"] is False

    def test_completion_rate_averages_over_sessions(self):
        result = CompletionRate().compute(
            "population-1",
            {
                "sessions": [
                    {"completion": True},
                    {"completion": False},
                    {"llm_spans": [], "tool_spans": []},
                ]
            },
        )

        assert result.value == 2 / 3
        assert result.metadata["session_count"] == 3
        assert result.metadata["failed_sessions"] == 1

    def test_tool_utilization_accuracy_accepts_output_content_alias(self):
        metric = ToolUtilizationAccuracy()
        with patch(
            "mce.providers.native.metrics.quality.tool_utilization_accuracy.llm_g_eval_score",
            return_value=(4.0, "looks good", "4"),
        ):
            result = metric.compute(
                "tc1",
                {
                    "toolArguments": '{"query": "sales"}',
                    "outputContent": "Sales: $1M",
                    "toolName": "search_db",
                },
            )

        assert result.value == 4.0

    def test_tool_utilization_accuracy_declares_retrieval_requirements(self):
        reqs = ToolUtilizationAccuracy().input_requirements

        assert reqs.retrieval is not None
        assert reqs.retrieval.nodes[0].alias == "tool_spans"
        assert [edge.relation_type for edge in reqs.retrieval.edges] == [
            "hasMASCalls",
            "hasAgentCalls",
            "invokesTool",
        ]

    def test_tool_utilization_accuracy_accepts_legacy_workaround_fields(self):
        metric = ToolUtilizationAccuracy()
        with patch(
            "mce.providers.native.metrics.quality.tool_utilization_accuracy.llm_g_eval_score",
            return_value=(5.0, "legacy payload handled", "5"),
        ):
            result = metric.compute(
                "tc-legacy",
                {
                    "inputParams": '{"query": "sales"}',
                    "toolOutput": "Sales: $1M",
                    "toolName": "search_db",
                },
            )

        assert result.value == 5.0
