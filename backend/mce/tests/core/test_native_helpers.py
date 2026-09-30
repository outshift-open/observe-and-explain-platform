#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mce.core.helpers import (
    _safe_session,
    _conversation_data,
    _conversation_text,
    _query_response,
    _span_dict,
    _span_attrs,
)
from mce.providers.native.metrics import ToolError, ToolErrorRate
from unittest.mock import MagicMock

# --- Helper Tests ---


def test_safe_session():
    # Case 1: Session in dict
    ctx = {"session": "my_session"}
    assert _safe_session(ctx) == "my_session"
    # Case 2: No session
    assert _safe_session({}) is None


def test_conversation_data():
    # Case 1: Direct in context
    ctx = {"conversation_data": {"k": "v"}}
    assert _conversation_data(ctx) == {"k": "v"}

    # Case 2: In session
    sess = MagicMock()
    sess.conversation_data = {"k": "session"}
    ctx = {"session": sess}
    assert _conversation_data(ctx) == {"k": "session"}


def test_conversation_text():
    # Case 1: direct key
    ctx = {"transcript": "hello"}
    assert _conversation_text(ctx) == "hello"

    # Case 2: via conversation_data
    ctx = {"conversation_data": {"conversation": "world"}}
    assert _conversation_text(ctx) == "world"


def test_query_response():
    # Case 1: direct keys
    ctx = {"input_query": "Q", "final_response": "A"}
    assert _query_response(ctx) == ("Q", "A")

    # Case 2: via data
    ctx = {"conversation_data": {"query": "Q2", "response": "A2"}}
    assert _query_response(ctx) == ("Q2", "A2")

    # Case 3: via KG-native llm_spans
    ctx = {
        "llm_spans": [
            {"inputContent": "Q3"},
            {"outputContent": "A3"},
        ]
    }
    assert _query_response(ctx) == ("Q3", "A3")

    # Case 4: first input, last output across spans
    ctx = {
        "llm_spans": [
            {"inputContent": "Q4"},
            {"outputContent": "intermediate"},
            {"outputContent": "A4"},
        ]
    }
    assert _query_response(ctx) == ("Q4", "A4")


def test_conversation_text_falls_back_to_query_response():
    ctx = {"conversation_data": {"query": "Q", "response": "A"}}
    result = _conversation_text(ctx)
    assert "Q" in result
    assert "A" in result


def test_span_helpers():
    # _span_dict
    obj = MagicMock()
    obj.__dict__ = {"a": 1}
    assert _span_dict(obj) == {"a": 1}
    assert _span_dict({"a": 2}) == {"a": 2}

    # _span_attrs
    span_with_attrs = {"attrs": {"k": "v"}}
    assert _span_attrs(span_with_attrs) == {"k": "v"}

    span_raw = {"raw_span_data": {"attributes": {"k": "v2"}}}
    assert _span_attrs(span_raw) == {"k": "v2"}


# --- Metric Tests ---


def test_tool_error():
    metric = ToolError()

    # Success
    res = metric.compute("id", {"status_code": "OK"})
    assert res.value == 0.0

    # Failure via status
    res = metric.compute("id", {"status_code": "ERROR"})
    assert res.value == 1.0

    # Failure via error field
    res = metric.compute("id", {"status_code": "OK", "error": "msg"})
    assert res.value == 1.0


def test_tool_error_rate():
    metric = ToolErrorRate()

    # Empty
    res = metric.compute("id", {"tool_spans": []})
    assert res.value == 0.0  # Or based on reasoning

    # Mixed
    spans = [
        {"status": "OK"},
        {"status": "ERROR"},
        {"status": "OK", "error": "yes"},  # treated as error
        {"status": "OK"},
    ]
    # Spans: OK, ERROR(err), ERROR(err), OK
    # 2 errors out of 4 -> 0.5
    res = metric.compute("id", {"tool_spans": spans})
    assert res.value == 0.5
