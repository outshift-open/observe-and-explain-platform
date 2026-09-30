#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.legacy.metrics.helpers utility functions."""

import pytest
from unittest.mock import MagicMock
from mce.legacy.metrics.helpers import (
    _safe_session,
    _conversation_data,
    _conversation_text,
    _query_response,
    _llm_binary_score,
    _span_dict,
    _span_attrs,
    _span_value,
)


# ---------------------------------------------------------------------------
# _safe_session
# ---------------------------------------------------------------------------


def test_safe_session_returns_none_when_absent():
    assert _safe_session({}) is None


def test_safe_session_returns_session_object():
    session = object()
    assert _safe_session({"session": session}) is session


# ---------------------------------------------------------------------------
# _conversation_data
# ---------------------------------------------------------------------------


def test_conversation_data_direct_from_context():
    data = {"query": "hi", "response": "hello"}
    ctx = {"conversation_data": data}
    assert _conversation_data(ctx) is data


def test_conversation_data_fallback_to_session():
    session = MagicMock()
    session.conversation_data = {"query": "q"}
    ctx = {"session": session}
    result = _conversation_data(ctx)
    assert result == {"query": "q"}


def test_conversation_data_returns_empty_dict_when_absent():
    assert _conversation_data({}) == {}


def test_conversation_data_non_dict_direct_value_ignored():
    ctx = {"conversation_data": "not a dict"}
    assert _conversation_data(ctx) == {}


# ---------------------------------------------------------------------------
# _conversation_text
# ---------------------------------------------------------------------------


def test_conversation_text_from_context_key():
    ctx = {"conversation_text": "hello world"}
    assert _conversation_text(ctx) == "hello world"


def test_conversation_text_from_transcript():
    ctx = {"transcript": "line1 line2"}
    assert _conversation_text(ctx) == "line1 line2"


def test_conversation_text_from_conversation_data():
    ctx = {"conversation_data": {"conversation": "data text"}}
    assert _conversation_text(ctx) == "data text"


def test_conversation_text_from_conversation_data_elements_list():
    ctx = {"conversation_data": {"elements": ["a", "b"]}}
    result = _conversation_text(ctx)
    assert isinstance(result, str)


def test_conversation_text_empty_when_nothing():
    assert _conversation_text({}) == ""


# ---------------------------------------------------------------------------
# _query_response
# ---------------------------------------------------------------------------


def test_query_response_from_context():
    ctx = {"input_query": "What?", "final_response": "Answer."}
    q, r = _query_response(ctx)
    assert q == "What?"
    assert r == "Answer."


def test_query_response_from_input_text():
    ctx = {"input_text": "Question", "output_text": "Reply"}
    q, r = _query_response(ctx)
    assert q == "Question"
    assert r == "Reply"


def test_query_response_from_session():
    session = MagicMock()
    session.input_query = "From session?"
    session.final_response = "Session answer"
    q, r = _query_response({"session": session})
    assert q == "From session?"
    assert r == "Session answer"


def test_query_response_fallback_empty_strings():
    assert _query_response({}) == ("", "")


def test_query_response_from_conversation_data():
    ctx = {"conversation_data": {"query": "data q", "response": "data r"}}
    q, r = _query_response(ctx)
    assert q == "data q"
    assert r == "data r"


# ---------------------------------------------------------------------------
# _llm_binary_score
# ---------------------------------------------------------------------------


def test_llm_binary_score_returns_float_and_response():
    metric = MagicMock()
    metric.call_llm.return_value = "0.8"
    score, response = _llm_binary_score(metric, "Score this: 0-1")
    assert isinstance(score, float)
    assert score == pytest.approx(0.8)
    assert response == "0.8"


def test_llm_binary_score_clips_above_one():
    metric = MagicMock()
    metric.call_llm.return_value = "2.5"
    score, _ = _llm_binary_score(metric, "score")
    assert score == pytest.approx(1.0)


def test_llm_binary_score_clips_below_zero():
    metric = MagicMock()
    metric.call_llm.return_value = "-0.5"
    score, _ = _llm_binary_score(metric, "score")
    assert score == pytest.approx(0.0)


def test_llm_binary_score_no_number_defaults_zero():
    metric = MagicMock()
    metric.call_llm.return_value = "no number here"
    score, _ = _llm_binary_score(metric, "score")
    assert score == pytest.approx(0.0)


def test_llm_binary_score_extracts_first_number():
    metric = MagicMock()
    metric.call_llm.return_value = "The score is 0.7 out of 1."
    score, _ = _llm_binary_score(metric, "score")
    assert score == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# _span_dict / _span_attrs / _span_value
# ---------------------------------------------------------------------------


def test_span_dict_passthrough_for_dict():
    d = {"key": "val"}
    assert _span_dict(d) is d


def test_span_dict_from_object_attrs():
    obj = MagicMock()
    obj.__dict__ = {"field": 42}
    result = _span_dict(obj)
    assert result.get("field") == 42


def test_span_attrs_from_dict_attrs():
    span = {"attrs": {"key": "value"}}
    assert _span_attrs(span) == {"key": "value"}


def test_span_attrs_from_raw_span_span_attributes():
    span = {"raw_span_data": {"SpanAttributes": {"k": "v"}}}
    assert _span_attrs(span).get("k") == "v"


def test_span_attrs_empty_when_nothing():
    assert _span_attrs({}) == {}


def test_span_value_finds_first_key():
    span = {"name": "my_tool", "other": "x"}
    result = _span_value(span, "name", "tool_name")
    assert result == "my_tool"


def test_span_value_fallback_key():
    span = {"tool_name": "fallback"}
    result = _span_value(span, "name", "tool_name")
    assert result == "fallback"


def test_span_value_from_attrs():
    span = {"attrs": {"toolName": "from_attrs"}}
    result = _span_value(span, "toolName")
    assert result == "from_attrs"


def test_span_value_none_when_absent():
    assert _span_value({}, "missing_key") is None
