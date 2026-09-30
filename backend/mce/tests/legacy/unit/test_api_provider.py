#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.legacy.adapters.api_provider.ApiDataProvider."""

import pytest
from unittest.mock import MagicMock, patch
from mce.legacy.adapters.api_provider import ApiDataProvider
from mce.core.metric import MetricRequirements


# ============================================================================
# Construction
# ============================================================================


def test_init_defaults(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("API_VERIFY_SSL", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    prov = ApiDataProvider()
    assert prov.base_url == "http://localhost:8000"
    assert prov.verify_ssl is True
    assert prov.timeout == 30


def test_init_custom_url():
    prov = ApiDataProvider(base_url="http://myapi:9090")
    assert prov.base_url == "http://myapi:9090"


def test_init_env_url(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://env-host:7777")
    prov = ApiDataProvider()
    assert prov.base_url == "http://env-host:7777"


def test_init_verify_ssl_false(monkeypatch):
    monkeypatch.setenv("API_VERIFY_SSL", "false")
    prov = ApiDataProvider()
    assert prov.verify_ssl is False


# ============================================================================
# fetch — delegates to _fetch_session_spans
# ============================================================================


def test_fetch_returns_context_structure():
    prov = ApiDataProvider(base_url="http://test")
    mock_spans = [
        {
            "SpanAttributes": {"traceloop.span.kind": "llm"},
            "StatusCode": "Unset",
            "StatusMessage": None,
            "SpanId": "s1",
            "SpanName": "call",
            "Timestamp": "2024-01-01",
        },
        {
            "SpanAttributes": {"traceloop.span.kind": "tool"},
            "StatusCode": "OK",
            "StatusMessage": None,
            "SpanId": "s2",
            "SpanName": "tool",
            "Timestamp": "2024-01-01",
        },
    ]
    with patch.object(prov, "_fetch_session_spans", return_value=mock_spans):
        ctx = prov.fetch("session_1", MetricRequirements())
    assert ctx["session_id"] == "session_1"
    assert len(ctx["llm_spans"]) == 1
    assert len(ctx["tool_spans"]) == 1


def test_fetch_propagates_lookup_error():
    prov = ApiDataProvider()
    with patch.object(
        prov, "_fetch_session_spans", side_effect=LookupError("not found")
    ):
        with pytest.raises(LookupError):
            prov.fetch("bad_id", MetricRequirements())


# ============================================================================
# _fetch_session_spans
# ============================================================================


def test_fetch_session_spans_success():
    prov = ApiDataProvider(base_url="http://test")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"sess1": [{"SpanId": "sp1"}]},
        "notfound_session_ids": [],
    }
    with patch("requests.get", return_value=mock_resp):
        spans = prov._fetch_session_spans("sess1")
    assert len(spans) == 1
    assert spans[0]["SpanId"] == "sp1"


def test_fetch_session_spans_not_in_response():
    prov = ApiDataProvider(base_url="http://test")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {}}
    with patch("requests.get", return_value=mock_resp):
        spans = prov._fetch_session_spans("sess_missing")
    assert spans == []


def test_fetch_session_spans_http_error():
    prov = ApiDataProvider(base_url="http://test")
    with patch("requests.get", side_effect=Exception("connection error")):
        with pytest.raises(LookupError):
            prov._fetch_session_spans("sess_fail")


# ============================================================================
# _normalize_span
# ============================================================================


def test_normalize_span_error_status():
    prov = ApiDataProvider()
    span = {
        "SpanAttributes": {"traceloop.span.kind": "llm"},
        "StatusCode": "Error",
        "StatusMessage": "timeout",
        "SpanId": "sp1",
        "SpanName": "call",
        "Timestamp": "2024-01-01",
    }
    result = prov._normalize_span(span)
    assert result["status_code"] == "ERROR"
    assert result["error"] == "timeout"
    assert result["span_id"] == "sp1"


def test_normalize_span_ok_status():
    prov = ApiDataProvider()
    span = {
        "SpanAttributes": {"traceloop.span.kind": "tool"},
        "StatusCode": "OK",
        "StatusMessage": None,
        "SpanId": "sp2",
        "SpanName": "mytool",
        "Timestamp": "2024-01-02",
    }
    result = prov._normalize_span(span)
    assert result["status_code"] == "OK"
    assert result["type"] == "tool"
    assert result["name"] == "mytool"


def test_normalize_span_status_code_error_variant():
    prov = ApiDataProvider()
    span = {
        "SpanAttributes": {},
        "StatusCode": "STATUS_CODE_ERROR",
        "StatusMessage": "fail",
        "SpanId": "sp3",
        "SpanName": "test",
        "Timestamp": None,
    }
    result = prov._normalize_span(span)
    assert result["status_code"] == "ERROR"
