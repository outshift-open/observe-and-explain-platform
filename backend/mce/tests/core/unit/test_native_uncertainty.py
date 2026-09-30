#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.native.metrics.uncertainty.llm_confidence."""

import math
import pytest
from mce.providers.native.metrics.uncertainty.llm_confidence import (
    LLMAverageConfidence,
    LLMMinimumConfidence,
    LLMMaximumConfidence,
    _extract_logprobs,
    _session_logprobs,
    _find_logprobs_block,
)


def _span_with_logprobs(probs):
    return {
        "output_payload": {"logprobs": {"content": [{"logprob": p} for p in probs]}}
    }


class TestFindLogprobsBlock:
    def test_finds_at_top_level(self):
        block = {"logprobs": {"content": []}}
        result = _find_logprobs_block(block)
        assert result == {"content": []}

    def test_finds_nested(self):
        data = {"choices": [{"logprobs": {"content": [{"logprob": -0.1}]}}]}
        result = _find_logprobs_block(data)
        assert result is not None

    def test_returns_none_when_absent(self):
        assert _find_logprobs_block({"a": 1}) is None

    def test_handles_list_search(self):
        data = [{"logprobs": {"content": []}}]
        result = _find_logprobs_block(data)
        assert result is not None


class TestExtractLogprobs:
    def test_extracts_from_output_payload(self):
        span = _span_with_logprobs([-0.1, -0.5])
        assert _extract_logprobs(span) == [-0.1, -0.5]

    def test_non_dict_payload(self):
        assert _extract_logprobs({"output_payload": "not-a-dict"}) == []

    def test_uses_recursive_fallback(self):
        span = {
            "output_payload": {
                "choices": [{"logprobs": {"content": [{"logprob": -0.3}]}}]
            }
        }
        assert _extract_logprobs(span) == [-0.3]


class TestSessionLogprobs:
    def test_from_llm_spans(self):
        span = _span_with_logprobs([-0.2])
        result = _session_logprobs({"llm_spans": [span]})
        assert result == [-0.2]

    def test_from_session_object(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        session.llm_spans = [_span_with_logprobs([-0.4])]
        result = _session_logprobs({"session": session})
        assert result == [-0.4]

    def test_empty_when_no_spans(self):
        assert _session_logprobs({}) == []


class TestLLMAverageConfidence:
    def test_compute_with_logprobs(self):
        m = LLMAverageConfidence()
        span = _span_with_logprobs([-0.1, -0.5])
        result = m.compute("s1", {"llm_spans": [span]})
        # Arithmetic mean of per-token probabilities (not geometric mean).
        expected = (math.exp(-0.1) + math.exp(-0.5)) / 2
        assert result.value == pytest.approx(expected, abs=0.001)

    def test_compute_no_logprobs(self):
        m = LLMAverageConfidence()
        result = m.compute("s1", {})
        assert result.value == 0.0

    def test_metadata(self):
        m = LLMAverageConfidence()
        assert m.metadata.name is not None


class TestLLMMinimumConfidence:
    def test_compute_with_logprobs(self):
        m = LLMMinimumConfidence()
        span = _span_with_logprobs([-0.1, -0.9])
        result = m.compute("s1", {"llm_spans": [span]})
        assert result.value == pytest.approx(math.exp(-0.9), abs=0.001)


class TestLLMMaximumConfidence:
    def test_compute_with_logprobs(self):
        m = LLMMaximumConfidence()
        span = _span_with_logprobs([-0.1, -0.9])
        result = m.compute("s1", {"llm_spans": [span]})
        assert result.value == pytest.approx(math.exp(-0.1), abs=0.001)
