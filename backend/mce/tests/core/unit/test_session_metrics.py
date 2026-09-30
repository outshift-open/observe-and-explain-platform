#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.native.metrics.session_metrics — all helpers and metrics."""

import pytest
from mce.core.metadata import MetricLayer, MetricNature
from mce.providers.native.metrics.session_metrics import (
    TYPE_LLM_CALL,
    TYPE_SESSION,
    TYPE_TOOL_CALL,
    CallCount,
    Cost,
    Duration,
    TokenCount,
    _detect_resource_type,
    _extract_numeric_attribute,
    _extract_numeric_attribute_with_source,
    _get_llm_calls,
    _get_tool_calls,
    _search_spans_lists,
)

# ============================================================================
# Helpers: _get_llm_calls / _get_tool_calls
# ============================================================================


def test_get_llm_calls_returns_list():
    spans = [{"executionId": "lc1"}, {"executionId": "lc2"}]
    assert _get_llm_calls({"llm_spans": spans}) == spans


def test_get_llm_calls_missing_key():
    assert _get_llm_calls({}) == []


def test_get_llm_calls_canonical_key():
    calls = [{"executionId": "lc1"}, {"executionId": "lc2"}]
    assert _get_llm_calls({"llm_calls": calls}) == calls


def test_get_tool_calls_returns_list():
    spans = [{"executionId": "tc1"}]
    assert _get_tool_calls({"tool_spans": spans}) == spans


def test_get_tool_calls_missing_key():
    assert _get_tool_calls({}) == []


def test_get_tool_calls_canonical_key():
    calls = [{"executionId": "tc1"}]
    assert _get_tool_calls({"tool_calls": calls}) == calls


# ============================================================================
# Helpers: _extract_numeric_attribute
# ============================================================================


def test_extract_numeric_first_key_wins():
    node = {"duration": 42.5, "durationMs": 100}
    assert _extract_numeric_attribute(node, ["duration", "durationMs"]) == 42.5


def test_extract_numeric_fallback_key():
    node = {"durationMs": 77}
    assert _extract_numeric_attribute(node, ["duration", "durationMs"]) == 77.0


def test_extract_numeric_missing_returns_default():
    assert _extract_numeric_attribute({}, ["duration"]) == 0.0
    assert _extract_numeric_attribute({}, ["duration"], default=5.0) == 5.0


def test_extract_numeric_non_numeric_skipped():
    node = {"duration": "fast", "durationMs": 10}
    assert _extract_numeric_attribute(node, ["duration", "durationMs"]) == 10.0


def test_extract_numeric_parses_stringified_numbers():
    node = {"duration": " 42.5 "}
    assert _extract_numeric_attribute(node, ["duration"]) == 42.5


def test_extract_numeric_int_converted_to_float():
    node = {"duration": 100}
    val = _extract_numeric_attribute(node, ["duration"])
    assert isinstance(val, float)
    assert val == 100.0


def test_extract_numeric_with_source_reports_key():
    node = {"durationMs": "77"}
    value, key = _extract_numeric_attribute_with_source(
        node, ["duration", "durationMs"]
    )
    assert value == 77.0
    assert key == "durationMs"


# ============================================================================
# Helpers: _detect_resource_type — session
# ============================================================================


def test_detect_resource_type_session():
    session_node = {"sessionId": "s1"}
    ctx = {"session_id": "s1", "session": session_node}
    rtype, node = _detect_resource_type("s1", ctx)
    assert rtype == TYPE_SESSION
    assert node is session_node


def test_detect_resource_type_session_missing_node_raises():
    ctx = {"session_id": "s1", "session": None}
    with pytest.raises(ValueError):
        _detect_resource_type("s1", ctx)


def test_detect_resource_type_llm_call_via_explicit_binding():
    node = {"executionId": "llm1", "modelName": "gpt-4"}
    ctx = {
        "session_id": "sess",
        "session": {},
        "resource_type": TYPE_LLM_CALL,
        "resource_node": node,
    }
    rtype, _ = _detect_resource_type("llm1", ctx)
    assert rtype == TYPE_LLM_CALL


def test_detect_resource_type_tool_call_via_explicit_binding():
    node = {"executionId": "tool1", "toolName": "search"}
    ctx = {
        "session_id": "sess",
        "session": {},
        "resource_type": TYPE_TOOL_CALL,
        "resource_node": node,
    }
    rtype, _ = _detect_resource_type("tool1", ctx)
    assert rtype == TYPE_TOOL_CALL


def test_detect_resource_type_from_llm_spans():
    llm = {"executionId": "lc3", "model": "gpt-4"}
    ctx = {"session_id": "sess", "session": {}, "llm_spans": [llm], "tool_spans": []}
    rtype, _ = _detect_resource_type("lc3", ctx)
    assert rtype == TYPE_LLM_CALL


def test_detect_resource_type_from_tool_spans():
    tool = {"executionId": "tc3", "toolName": "calc"}
    ctx = {"session_id": "sess", "session": {}, "llm_spans": [], "tool_spans": [tool]}
    rtype, _ = _detect_resource_type("tc3", ctx)
    assert rtype == TYPE_TOOL_CALL


def test_detect_resource_type_not_found_raises():
    ctx = {"session_id": "sess", "session": {}, "llm_spans": [], "tool_spans": []}
    with pytest.raises(ValueError):
        _detect_resource_type("unknown", ctx)


# ============================================================================
# Helpers: _search_spans_lists
# ============================================================================


def test_search_llm_span_found():
    llm_node = {"executionId": "lc1", "model": "gpt-4"}
    ctx = {"llm_spans": [llm_node], "tool_spans": []}
    rtype, node = _search_spans_lists("lc1", ctx)
    assert rtype == TYPE_LLM_CALL
    assert node is llm_node


def test_search_tool_span_found():
    tool_node = {"executionId": "tc1", "toolName": "search"}
    ctx = {"llm_spans": [], "tool_spans": [tool_node]}
    rtype, _ = _search_spans_lists("tc1", ctx)
    assert rtype == TYPE_TOOL_CALL


def test_search_span_missing_raises():
    ctx = {"llm_spans": [], "tool_spans": []}
    with pytest.raises(ValueError):
        _search_spans_lists("missing_id", ctx)


def test_search_span_by_id_key():
    llm_node = {"id": "lc2", "model": "gpt-4"}
    ctx = {"llm_spans": [llm_node], "tool_spans": []}
    rtype, _ = _search_spans_lists("lc2", ctx)
    assert rtype == TYPE_LLM_CALL


def test_search_span_by_span_id_key():
    tool_node = {"span_id": "tc2", "toolName": "calc"}
    ctx = {"llm_spans": [], "tool_spans": [tool_node]}
    rtype, _ = _search_spans_lists("tc2", ctx)
    assert rtype == TYPE_TOOL_CALL


def test_search_span_found_in_canonical_keys():
    llm_node = {"executionId": "lc4", "model": "gpt-4"}
    tool_node = {"executionId": "tc4", "toolName": "calc"}
    rtype_llm, _ = _search_spans_lists(
        "lc4", {"llm_calls": [llm_node], "tool_calls": []}
    )
    rtype_tool, _ = _search_spans_lists(
        "tc4", {"llm_calls": [], "tool_calls": [tool_node]}
    )
    assert rtype_llm == TYPE_LLM_CALL
    assert rtype_tool == TYPE_TOOL_CALL


# ============================================================================
# Duration.compute
# ============================================================================


def _session_ctx(session_id="sess1", duration=None, start=None, end=None, extra=None):
    node = {"sessionId": session_id}
    if duration is not None:
        node["duration"] = duration
    if start is not None:
        node["startTime"] = start
    if end is not None:
        node["endTime"] = end
    if extra:
        node.update(extra)
    return {
        "session_id": session_id,
        "session": node,
        "resource_type": TYPE_SESSION,
        "resource_node": node,
    }


def _llm_ctx(exec_id="lc1", **props):
    node = {
        "session_id": "sess",
        "executionId": exec_id,
        "model": "gpt-4",
    }
    node.update(props)
    return {
        "session_id": "sess",
        "session": {},
        "resource_type": TYPE_LLM_CALL,
        "resource_node": node,
        **node,
    }


def _tool_ctx(exec_id="tc1", **props):
    node = {"executionId": exec_id, "toolName": "t"}
    node.update(props)
    return {
        "session_id": "sess",
        "session": {},
        "resource_type": TYPE_TOOL_CALL,
        "resource_node": node,
        **node,
    }


class TestDurationMetric:
    def setup_method(self):
        self.metric = Duration()

    def test_metadata(self):
        assert self.metric.metadata.name == "Duration"
        assert self.metric.metadata.layer == MetricLayer.EXECUTION
        assert self.metric.metadata.nature == MetricNature.DETERMINISTIC
        # target_types is injected by the ontology-resolution layer (discovery.py),
        # not by the class itself — no assertion here.

    def test_input_requirements(self):
        req = self.metric.input_requirements
        assert req is not None

    def test_compute_session_direct_duration(self):
        ctx = _session_ctx(duration=1234.5)
        result = self.metric.compute("sess1", ctx)
        assert result.value == pytest.approx(1234.5)
        assert result.resource_id == "sess1"
        assert result.provider == "Native"

    def test_compute_session_fallback_timestamps(self):
        ctx = _session_ctx(start=1000.0, end=2500.0)
        result = self.metric.compute("sess1", ctx)
        assert result.value == pytest.approx(1500000.0)

    def test_compute_session_zero_when_no_data(self):
        ctx = _session_ctx()
        result = self.metric.compute("sess1", ctx)
        assert result.value == pytest.approx(0.0)

    def test_compute_llm_call_direct_duration(self):
        ctx = _llm_ctx(durationMs=500.0)
        result = self.metric.compute("lc1", ctx)
        assert result.value == pytest.approx(500.0)

    def test_compute_tool_call_timestamp_fallback(self):
        ctx = _tool_ctx(startTime=100.0, endTime=300.0)
        result = self.metric.compute("tc1", ctx)
        assert result.value == pytest.approx(200000.0)

    def test_compute_duration_ms_key(self):
        ctx = _session_ctx(extra={"duration_ms": 999.0})
        result = self.metric.compute("sess1", ctx)
        assert result.value == pytest.approx(999.0)

    def test_compute_metadata_contains_unit(self):
        ctx = _session_ctx(duration=100.0)
        result = self.metric.compute("sess1", ctx)
        assert result.metadata["unit"] == "milliseconds"
        assert result.metadata["resource_type"] == TYPE_SESSION


# ============================================================================
# TokenCount.compute
# ============================================================================


class TestTokenCountMetric:
    def setup_method(self):
        self.metric = TokenCount()

    def test_metadata(self):
        assert self.metric.metadata.name == "TokenCount"

    def test_tool_call_always_zero(self):
        ctx = _tool_ctx()
        result = self.metric.compute("tc1", ctx)
        assert result.value == 0
        assert "ToolCall does not use tokens" in result.reasoning

    def test_llm_call_total_tokens(self):
        ctx = _llm_ctx(totalTokens=150)
        result = self.metric.compute("lc1", ctx)
        assert result.value == 150

    def test_llm_call_total_token_count_key(self):
        ctx = _llm_ctx(totalTokenCount=200)
        result = self.metric.compute("lc1", ctx)
        assert result.value == 200

    def test_llm_call_total_token_count_string_key(self):
        ctx = _llm_ctx(totalTokenCount="1569")
        result = self.metric.compute("lc1", ctx)
        assert result.value == 1569

    def test_llm_call_fallback_input_output_sum(self):
        ctx = _llm_ctx(inputTokens=80, outputTokens=40)
        result = self.metric.compute("lc1", ctx)
        assert result.value == 120

    def test_llm_call_prompt_completion_keys(self):
        ctx = _llm_ctx(promptTokenCount=50, completionTokenCount=30)
        result = self.metric.compute("lc1", ctx)
        assert result.value == 80

    def test_session_precomputed_total(self):
        ctx = _session_ctx(extra={"totalTokens": 500})
        result = self.metric.compute("sess1", ctx)
        assert result.value == 500
        assert "kg_precomputed" in result.metadata["source"]

    def test_session_aggregate_from_llm_spans(self):
        llm1 = {"executionId": "lc1", "totalTokens": 100}
        llm2 = {"executionId": "lc2", "totalTokens": 200}
        ctx = _session_ctx()
        ctx["llm_spans"] = [llm1, llm2]
        result = self.metric.compute("sess1", ctx)
        assert result.value == 300
        assert "kg_llm_aggregation" in result.metadata["source"]

    def test_session_aggregate_fallback_input_output(self):
        llm1 = {"executionId": "lc1", "inputTokens": 60, "outputTokens": 40}
        ctx = _session_ctx()
        ctx["llm_spans"] = [llm1]
        result = self.metric.compute("sess1", ctx)
        assert result.value == 100

    def test_session_no_llm_spans_zero(self):
        ctx = _session_ctx()
        ctx["llm_spans"] = []
        result = self.metric.compute("sess1", ctx)
        assert result.value == 0


# ============================================================================
# CallCount.compute
# ============================================================================


class TestCallCountMetric:
    def setup_method(self):
        self.metric = CallCount()

    def test_metadata(self):
        assert self.metric.metadata.name == "CallCount"

    def test_llm_call_leaf_returns_zero(self):
        ctx = _llm_ctx()
        result = self.metric.compute("lc1", ctx)
        assert result.value == 0
        assert "leaf node" in result.reasoning

    def test_tool_call_leaf_returns_zero(self):
        ctx = _tool_ctx()
        result = self.metric.compute("tc1", ctx)
        assert result.value == 0

    def test_session_counts_llm_and_tool(self):
        ctx = _session_ctx()
        ctx["llm_spans"] = [{"executionId": "lc1"}, {"executionId": "lc2"}]
        ctx["tool_spans"] = [{"executionId": "tc1"}]
        result = self.metric.compute("sess1", ctx)
        assert result.value == 3
        assert result.metadata["llm_calls"] == 2
        assert result.metadata["tool_calls"] == 1

    def test_session_no_children_zero(self):
        ctx = _session_ctx()
        ctx["llm_spans"] = []
        ctx["tool_spans"] = []
        result = self.metric.compute("sess1", ctx)
        assert result.value == 0


# ============================================================================
# Cost.compute
# ============================================================================


class TestCostMetric:
    def setup_method(self):
        self.metric = Cost()

    def test_default_pricing_model(self):
        assert self.metric.pricing_model == "gpt-4"

    def test_custom_pricing_model(self):
        m = Cost(pricing_model="gpt-3.5")
        assert m.pricing_model == "gpt-3.5"

    def test_metadata(self):
        assert self.metric.metadata.name == "Cost"

    def test_tool_call_zero_cost(self):
        ctx = _tool_ctx()
        result = self.metric.compute("tc1", ctx)
        assert result.value == pytest.approx(0.0)
        assert "ToolCall has no LLM cost" in result.reasoning

    def test_llm_call_with_tokens(self):
        # 1M input tokens = $10, 1M output tokens = $30
        # 1000 input @ $10/1M = $0.01
        # 500 output @ $30/1M = $0.015
        ctx = _llm_ctx(inputTokens=1000, outputTokens=500)
        result = self.metric.compute("lc1", ctx)
        assert result.value == pytest.approx(0.025, rel=1e-3)
        assert result.metadata["input_tokens"] == 1000
        assert result.metadata["output_tokens"] == 500

    def test_llm_call_prompt_completion_keys(self):
        ctx = _llm_ctx(promptTokenCount=2000, completionTokenCount=1000)
        result = self.metric.compute("lc1", ctx)
        expected = 2000 * 10 / 1_000_000 + 1000 * 30 / 1_000_000
        assert result.value == pytest.approx(expected, rel=1e-5)

    def test_llm_call_no_tokens_zero_cost(self):
        ctx = _llm_ctx()
        result = self.metric.compute("lc1", ctx)
        assert result.value == pytest.approx(0.0)

    def test_session_aggregates_from_llm_spans(self):
        llm1 = {"executionId": "lc1", "inputTokens": 500, "outputTokens": 250}
        llm2 = {"executionId": "lc2", "inputTokens": 500, "outputTokens": 250}
        ctx = _session_ctx()
        ctx["llm_spans"] = [llm1, llm2]
        result = self.metric.compute("sess1", ctx)
        # 1000 input @ $10/1M = $0.01; 500 output @ $30/1M = $0.015
        assert result.value == pytest.approx(0.025, rel=1e-3)
        assert result.metadata["llm_call_count"] == 2
        assert result.metadata["source"] == "kg_llm_aggregation"

    def test_session_aggregates_from_canonical_llm_calls(self):
        llm1 = {"executionId": "lc1", "inputTokens": 500, "outputTokens": 250}
        llm2 = {"executionId": "lc2", "inputTokens": 500, "outputTokens": 250}
        ctx = _session_ctx()
        ctx["llm_calls"] = [llm1, llm2]
        result = self.metric.compute("sess1", ctx)
        assert result.value == pytest.approx(0.025, rel=1e-3)
        assert result.metadata["llm_call_count"] == 2

    def test_session_no_llm_spans_zero_cost(self):
        ctx = _session_ctx()
        ctx["llm_spans"] = []
        result = self.metric.compute("sess1", ctx)
        assert result.value == pytest.approx(0.0)

    def test_session_logs_zero_cost_when_llm_tokens_missing(self, caplog):
        ctx = _session_ctx()
        ctx["llm_spans"] = [{"executionId": "lc1", "modelName": "azure/gpt-4o"}]

        with caplog.at_level("INFO"):
            result = self.metric.compute("sess1", ctx)

        assert result.value == pytest.approx(0.0)
        assert "produced zero tokens" in caplog.text
        assert "mas:Session sess1" in caplog.text
        assert "'lc1'" in caplog.text

    def test_session_logs_total_token_fallback(self, caplog):
        ctx = _session_ctx()
        ctx["llm_spans"] = [{"executionId": "lc1", "totalTokenCount": 1000}]

        with caplog.at_level("INFO"):
            result = self.metric.compute("sess1", ctx)

        expected = int(1000 * 0.7) * 10 / 1_000_000 + int(1000 * 0.3) * 30 / 1_000_000
        assert result.value == pytest.approx(expected, rel=1e-5)
        assert result.metadata["fallback_count"] == 1
        assert "Estimating 70/30 split" in caplog.text
        assert "totalTokenCount=1000" in caplog.text

    def test_session_llm_spans_prompt_completion_keys(self):
        llm = {
            "executionId": "lc1",
            "promptTokenCount": 1000,
            "completionTokenCount": 500,
        }
        ctx = _session_ctx()
        ctx["llm_spans"] = [llm]
        result = self.metric.compute("sess1", ctx)
        expected = 1000 * 10 / 1_000_000 + 500 * 30 / 1_000_000
        assert result.value == pytest.approx(expected, rel=1e-5)

    def test_session_llm_spans_ontology_string_token_keys(self):
        llm = {
            "executionId": "lc1",
            "promptTokenCount": "1500",
            "completionTokenCount": "69",
            "totalTokenCount": "1569",
        }
        ctx = _session_ctx()
        ctx["llm_spans"] = [llm]
        result = self.metric.compute("sess1", ctx)
        expected = 1500 * 10 / 1_000_000 + 69 * 30 / 1_000_000
        assert result.value == pytest.approx(expected, rel=1e-5)
        assert result.metadata["input_tokens"] == 1500
        assert result.metadata["output_tokens"] == 69

    def test_cost_metadata_contains_pricing_model(self):
        ctx = _tool_ctx()
        result = self.metric.compute("tc1", ctx)
        assert result.metadata["pricing_model"] == "gpt-4"
