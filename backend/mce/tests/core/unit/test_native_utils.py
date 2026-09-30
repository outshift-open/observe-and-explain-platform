#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.native.utils — utility functions."""

import pytest
from unittest.mock import MagicMock
from mce.providers.native.utils import (
    llm_binary_score,
    llm_cot_score,
    extract_conversation_text,
    extract_query_response,
)


class TestLlmBinaryScore:
    def test_extracts_float_from_response(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "Score: 0.85"
        score, response = llm_binary_score(mock_metric, "Is it good?")
        assert score == pytest.approx(0.85, abs=0.01)

    def test_clamps_to_one(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "5.0"
        score, _ = llm_binary_score(mock_metric, "prompt")
        assert score == 1.0

    def test_returns_zero_when_no_number(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "no numbers here"
        score, _ = llm_binary_score(mock_metric, "prompt")
        assert score == 0.0

    def test_handles_negative_clamped_to_zero(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "-2.0"
        score, _ = llm_binary_score(mock_metric, "p")
        assert score == 0.0


class TestLlmCotScore:
    def test_extracts_score_label(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "Reasoning: good\nScore: 0.9"
        score, _ = llm_cot_score(mock_metric, "prompt")
        assert score == pytest.approx(0.9, abs=0.01)

    def test_extracts_rating_label(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "Rating: 3.5"
        score, _ = llm_cot_score(mock_metric, "prompt")
        assert score == pytest.approx(3.5, abs=0.01)

    def test_fallback_to_last_number(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "This is good. Final: 4"
        score, _ = llm_cot_score(mock_metric, "prompt")
        assert score == 4.0

    def test_returns_zero_when_no_number(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "no numbers"
        score, _ = llm_cot_score(mock_metric, "prompt")
        assert score == 0.0


class TestExtractConversationText:
    def test_from_conversation_data(self):
        ctx = {"conversation_data": {"elements": "text"}}
        result = extract_conversation_text(ctx)
        assert result

    def test_from_conversation_text(self):
        ctx = {"conversation_text": "hello world"}
        assert extract_conversation_text(ctx) == "hello world"

    def test_from_transcript(self):
        ctx = {"transcript": "Q: hi A: hello"}
        assert extract_conversation_text(ctx) == "Q: hi A: hello"

    def test_from_input_output(self):
        ctx = {"input_text": "question", "output_text": "answer"}
        result = extract_conversation_text(ctx)
        assert "question" in result
        assert "answer" in result

    def test_from_conversation_data_query_response(self):
        ctx = {"conversation_data": {"query": "question", "response": "answer"}}
        result = extract_conversation_text(ctx)
        assert "question" in result
        assert "answer" in result

    def test_returns_empty_when_nothing(self):
        assert extract_conversation_text({}) == ""


class TestExtractQueryResponse:
    def test_from_input_output_text(self):
        ctx = {"input_text": "Q?", "output_text": "A."}
        q, r = extract_query_response(ctx)
        assert q == "Q?"
        assert r == "A."

    def test_from_input_query_final_response(self):
        ctx = {"input_query": "ask", "final_response": "reply"}
        q, r = extract_query_response(ctx)
        assert q == "ask"
        assert r == "reply"

    def test_from_llm_spans_kg_fields(self):
        ctx = {
            "llm_spans": [
                {"inputContent": "ask"},
                {"outputContent": "reply"},
            ]
        }
        q, r = extract_query_response(ctx)
        assert q == "ask"
        assert r == "reply"

    def test_returns_empty_strings_when_absent(self):
        q, r = extract_query_response({})
        assert q == ""
        assert r == ""
