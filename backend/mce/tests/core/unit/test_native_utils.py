#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.native.utils — utility functions."""

import math

import pytest
from unittest.mock import MagicMock
from mce.engine.llm import CompletionResult
from mce.providers.native.utils import (
    JudgeScoreError,
    expected_score_from_logprobs,
    extract_conversation_text,
    extract_query_response,
    judge_settings,
    llm_binary_score,
    llm_cot_score,
    llm_g_eval_score,
    parse_score,
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

    def test_accepts_a_reply_that_is_only_a_number(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "4"
        score, _ = llm_cot_score(mock_metric, "prompt")
        assert score == 4.0

    def test_does_not_guess_a_number_out_of_prose(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "This is good. Final: 4"
        with pytest.raises(JudgeScoreError):
            llm_cot_score(mock_metric, "prompt")

    def test_raises_when_no_number(self):
        mock_metric = MagicMock()
        mock_metric.call_llm.return_value = "no numbers"
        with pytest.raises(JudgeScoreError):
            llm_cot_score(mock_metric, "prompt")


class TestParseScore:
    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ("Reasoning: fine\nScore: 4", 4.0),
            ("Score: **4**", 4.0),
            ("score - 3.5", 3.5),
            ("Score: 2\nScore: 5", 5.0),  # the last label wins
            ("  **5**  ", 5.0),
        ],
    )
    def test_extracts_the_score(self, reply, expected):
        assert parse_score(reply) == expected

    @pytest.mark.parametrize("reply", ["", "great answer", "I give it a 4 out of 5"])
    def test_raises_without_a_score_label(self, reply):
        with pytest.raises(JudgeScoreError):
            parse_score(reply)


def _logprobs(digit_probs, chosen):
    """Token log-probabilities of ``...Score: <chosen>`` with the given digit alternatives."""
    tokens = [
        {"token": t, "logprob": 0.0, "top": []}
        for t in ("Reasoning", ":", " ok", "\n", "Score", ":", " ")
    ]
    top = [{"token": d, "logprob": math.log(p)} for d, p in digit_probs.items()]
    tokens.append(
        {"token": chosen, "logprob": math.log(digit_probs[chosen]), "top": top}
    )
    return tokens


class TestExpectedScore:
    def test_is_the_expectation_over_the_digit_alternatives(self):
        logprobs = _logprobs({"4": 0.6, "5": 0.3, "3": 0.1}, "4")
        assert expected_score_from_logprobs(logprobs, 4.0, 5) == pytest.approx(4.2)

    def test_ignores_non_digit_alternatives_and_renormalizes(self):
        logprobs = _logprobs({"4": 0.4, "5": 0.4}, "4")
        logprobs[-1]["top"].append({"token": "Four", "logprob": math.log(0.2)})
        assert expected_score_from_logprobs(logprobs, 4.0, 5) == pytest.approx(4.5)

    def test_confident_judge_gives_the_digit_itself(self):
        assert expected_score_from_logprobs(
            _logprobs({"5": 0.999}, "5"), 5.0, 5
        ) == pytest.approx(5.0, abs=0.01)

    def test_none_when_the_score_token_is_not_found(self):
        assert expected_score_from_logprobs(_logprobs({"4": 0.9}, "4"), 2.0, 5) is None
        assert expected_score_from_logprobs([], 4.0, 5) is None

    def test_a_digit_not_after_a_score_label_is_not_the_score(self):
        tokens = [
            {"token": "Step", "logprob": 0.0, "top": []},
            {"token": "4", "logprob": -0.1, "top": [{"token": "4", "logprob": -0.1}]},
        ]
        assert expected_score_from_logprobs(tokens, 4.0, 5) is None


class _JudgeMetric:
    """Minimal metric whose LLM replies and completions are scripted."""

    metric_id = "FakeJudge"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self._completion = None

    def call_llm(self, prompt, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        text, logprobs = reply if isinstance(reply, tuple) else (reply, None)
        self._completion = CompletionResult(text=text, logprobs=logprobs)
        return text

    def pop_completion(self):
        completion, self._completion = self._completion, None
        return completion


class TestJudgeScoring:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        for name in (
            "MCE_JUDGE_SAMPLES",
            "MCE_JUDGE_TEMPERATURE",
            "MCE_JUDGE_LOGPROBS",
        ):
            monkeypatch.delenv(name, raising=False)

    def test_defaults_are_deterministic_and_ask_for_logprobs(self):
        metric = _JudgeMetric(["Reasoning: ok\nScore: 4"])
        llm_g_eval_score(metric, "p")
        assert metric.calls == [
            {"temperature": 0.0, "logprobs": True, "top_logprobs": 5}
        ]

    def test_score_is_continuous_when_the_endpoint_returns_logprobs(self):
        logprobs = _logprobs({"4": 0.6, "5": 0.3, "3": 0.1}, "4")
        metric = _JudgeMetric([("Reasoning: ok\nScore: 4", logprobs)])
        normalized, reasoning, raw = llm_g_eval_score(metric, "p")
        assert raw == pytest.approx(4.2)
        assert normalized == pytest.approx((4.2 - 1) / 4)
        assert reasoning.startswith("Reasoning: ok")

    def test_falls_back_to_the_sampled_digit_without_logprobs(self):
        normalized, _, raw = llm_g_eval_score(_JudgeMetric(["Score: 4"]), "p")
        assert (raw, normalized) == (4.0, 0.75)

    def test_samples_are_averaged(self, monkeypatch):
        monkeypatch.setenv("MCE_JUDGE_SAMPLES", "3")
        metric = _JudgeMetric(["Score: 5", "Score: 4", "Score: 3"])
        normalized, _, raw = llm_g_eval_score(metric, "p")
        assert raw == pytest.approx(4.0)
        assert normalized == pytest.approx(0.75)
        assert [c.get("sample") for c in metric.calls] == [None, 1, 2]
        assert all(c["temperature"] == 0.7 for c in metric.calls)

    def test_an_unusable_sample_is_skipped_not_scored_as_zero(self, monkeypatch):
        monkeypatch.setenv("MCE_JUDGE_SAMPLES", "2")
        metric = _JudgeMetric(["I cannot say", "Score: 4"])
        _, _, raw = llm_g_eval_score(metric, "p")
        assert raw == 4.0

    def test_no_usable_sample_raises(self):
        with pytest.raises(JudgeScoreError):
            llm_g_eval_score(_JudgeMetric(["I cannot say"]), "p")

    def test_out_of_range_scores_are_clamped(self):
        assert llm_g_eval_score(_JudgeMetric(["Score: 9"]), "p")[2] == 5.0
        assert llm_g_eval_score(_JudgeMetric(["Score: 0"]), "p")[2] == 1.0

    def test_environment_controls_the_settings(self, monkeypatch):
        monkeypatch.setenv("MCE_JUDGE_SAMPLES", "5")
        monkeypatch.setenv("MCE_JUDGE_TEMPERATURE", "0.2")
        monkeypatch.setenv("MCE_JUDGE_LOGPROBS", "false")
        settings = judge_settings()
        assert (settings.samples, settings.temperature, settings.logprobs) == (
            5,
            0.2,
            False,
        )
        metric = _JudgeMetric(["Score: 3"] * 5)
        llm_g_eval_score(metric, "p")
        assert all("logprobs" not in c for c in metric.calls)

    def test_bad_settings_fall_back_to_defaults(self, monkeypatch):
        monkeypatch.setenv("MCE_JUDGE_SAMPLES", "many")
        monkeypatch.setenv("MCE_JUDGE_TEMPERATURE", "hot")
        settings = judge_settings()
        assert (settings.samples, settings.temperature) == (1, 0.0)


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
