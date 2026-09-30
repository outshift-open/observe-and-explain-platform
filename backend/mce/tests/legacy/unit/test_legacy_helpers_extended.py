#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.legacy.metrics.helpers — extended coverage."""

from unittest.mock import MagicMock
from mce.legacy.metrics.helpers import (
    _safe_session,
    _conversation_data,
    _conversation_text,
    _query_response,
    _span_dict,
    _span_attrs,
    _span_value,
    _first_number,
    _find_key_value,
    _extract_logprobs,
    _session_logprobs,
)


class TestSafeSession:
    def test_returns_session_object(self):
        s = MagicMock()
        assert _safe_session({"session": s}) is s

    def test_returns_none_when_absent(self):
        assert _safe_session({}) is None


class TestConversationData:
    def test_from_dict(self):
        ctx = {"conversation_data": {"q": "hello"}}
        assert _conversation_data(ctx)["q"] == "hello"

    def test_from_session_attribute(self):
        session = MagicMock()
        session.conversation_data = {"q": "world"}
        assert _conversation_data({"session": session})["q"] == "world"

    def test_non_dict_conversation_data(self):
        ctx = {"conversation_data": "raw string"}
        # Non-dict falls through to session check
        result = _conversation_data(ctx)
        assert result == {}

    def test_returns_empty_when_none(self):
        assert _conversation_data({}) == {}


class TestConversationText:
    def test_from_conversation_text_key(self):
        ctx = {"conversation_text": "hello world"}
        assert _conversation_text(ctx) == "hello world"

    def test_from_transcript_key(self):
        ctx = {"transcript": "transcript text"}
        assert _conversation_text(ctx) == "transcript text"

    def test_from_conversation_key(self):
        ctx = {"conversation": "convo text"}
        assert _conversation_text(ctx) == "convo text"

    def test_from_conversation_data_dict(self):
        ctx = {"conversation_data": {"conversation": "nested"}}
        assert _conversation_text(ctx) == "nested"

    def test_from_elements_list(self):
        ctx = {"conversation_data": {"elements": [{"role": "user"}]}}
        result = _conversation_text(ctx)
        assert result  # Should serialize to JSON

    def test_from_elements_string(self):
        ctx = {"conversation_data": {"elements": "elem text"}}
        assert _conversation_text(ctx) == "elem text"

    def test_returns_empty_when_none(self):
        assert _conversation_text({}) == ""


class TestQueryResponse:
    def test_from_input_query(self):
        q, r = _query_response({"input_query": "q?", "final_response": "a!"})
        assert q == "q?"
        assert r == "a!"

    def test_from_input_text(self):
        q, r = _query_response({"input_text": "ask", "output_text": "reply"})
        assert q == "ask"
        assert r == "reply"

    def test_from_conversation_data(self):
        ctx = {"conversation_data": {"query": "cv_q", "response": "cv_r"}}
        q, r = _query_response(ctx)
        assert q == "cv_q"
        assert r == "cv_r"

    def test_from_session_attributes(self):
        session = MagicMock()
        session.input_query = "sq"
        session.final_response = "sr"
        q, r = _query_response({"session": session})
        assert q == "sq"
        assert r == "sr"

    def test_returns_empty_strings_when_none(self):
        q, r = _query_response({})
        assert q == ""
        assert r == ""


class TestSpanHelpers:
    def test_span_dict_from_dict(self):
        d = {"name": "span1"}
        assert _span_dict(d) is d

    def test_span_dict_from_object(self):
        span = MagicMock()
        span.__dict__ = {"name": "span1"}
        result = _span_dict(span)
        assert "name" in result

    def test_span_attrs_from_nested_attrs(self):
        span = {"attrs": {"key": "val"}}
        assert _span_attrs(span) == {"key": "val"}

    def test_span_attrs_from_raw_span(self):
        span = {"raw_span_data": {"SpanAttributes": {"k": "v"}}}
        assert _span_attrs(span) == {"k": "v"}

    def test_span_attrs_fallback_attributes_key(self):
        span = {"raw_span_data": {"attributes": {"a": "b"}}}
        assert _span_attrs(span) == {"a": "b"}

    def test_span_attrs_empty(self):
        assert _span_attrs({}) == {}

    def test_span_value_from_data(self):
        span = {"name": "myspan"}
        assert _span_value(span, "name") == "myspan"

    def test_span_value_from_attrs(self):
        span = {"attrs": {"tool.name": "mytool"}}
        assert _span_value(span, "tool.name") == "mytool"

    def test_span_value_returns_none_when_absent(self):
        assert _span_value({}, "missing") is None


class TestFirstNumber:
    def test_returns_first_match(self):
        assert _first_number({"a": 1.5, "b": 2.0}, ["a", "b"]) == 1.5

    def test_returns_second_on_miss(self):
        assert _first_number({"b": 3}, ["a", "b"]) == 3.0

    def test_returns_zero_when_none(self):
        assert _first_number({}, ["x"]) == 0.0


class TestFindKeyValue:
    def test_finds_top_level(self):
        assert _find_key_value({"x": 42}, "x") == 42

    def test_finds_nested(self):
        data = {"a": {"b": {"c": "found"}}}
        assert _find_key_value(data, "c") == "found"

    def test_finds_in_list(self):
        data = [{"x": 1}, {"y": 2}]
        assert _find_key_value(data, "y") == 2

    def test_returns_none_when_absent(self):
        assert _find_key_value({"a": 1}, "missing") is None


class TestExtractLogprobs:
    def test_extracts_logprobs(self):
        span = {
            "output_payload": {
                "logprobs": {"content": [{"logprob": -0.1}, {"logprob": -0.5}]}
            }
        }
        probs = _extract_logprobs(span)
        assert probs == [-0.1, -0.5]

    def test_returns_empty_when_no_output(self):
        assert _extract_logprobs({}) == []

    def test_returns_empty_when_no_logprobs_block(self):
        assert _extract_logprobs({"output_payload": {"other": 1}}) == []

    def test_returns_empty_when_content_not_list(self):
        assert (
            _extract_logprobs({"output_payload": {"logprobs": {"content": "bad"}}})
            == []
        )


class TestSessionLogprobs:
    def test_extracts_from_llm_spans(self):
        span = {"output_payload": {"logprobs": {"content": [{"logprob": -0.2}]}}}
        result = _session_logprobs({"llm_spans": [span]})
        assert result == [-0.2]

    def test_extracts_from_session_object(self):
        span = {"output_payload": {"logprobs": {"content": [{"logprob": -0.3}]}}}
        session = MagicMock()
        session.llm_spans = [span]
        result = _session_logprobs({"session": session})
        assert result == [-0.3]

    def test_returns_empty_when_no_spans(self):
        assert _session_logprobs({}) == []
