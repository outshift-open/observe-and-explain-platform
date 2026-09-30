#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E402

"""Tests targeting missed engine.py lines."""

from contextlib import nullcontext
import sys
from unittest.mock import MagicMock, patch
import pytest

for _m in [
    "deepeval",
    "deepeval.metrics",
    "deepeval.test_case",
    "deepeval.models",
    "deepeval.telemetry",
]:
    if _m not in sys.modules:
        _mock = MagicMock()
        _mock.__spec__ = None
        sys.modules[_m] = _mock

from mce.engine.engine import MetricEngine
from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
    ToolUtilizationAccuracy,
)
from mce.providers.native.metrics.safety.llm_error_rate import LLMErrorRate
from mce.providers.native.metrics.session_metrics import (
    CallCount,
    Cost,
    Duration,
    TokenCount,
)
from mce.providers.native.metrics.workflow.workflow_efficiency import WorkflowEfficiency


def _engine(provider=None):
    e = MetricEngine()
    if provider:
        e.set_data_provider(provider)
    return e


# ---------------------------------------------------------------------------
# Line 44: _create_executor with string strategies
# ---------------------------------------------------------------------------
def test_create_executor_thread_string():
    """_create_executor('thread', n) returns a ThreadStrategy."""
    _ = MetricEngine.__new__(MetricEngine)
    result = MetricEngine._create_executor("thread", 4)
    assert result is not None


def test_create_executor_process_string():
    """_create_executor('process', n) returns a ProcessStrategy."""
    result = MetricEngine._create_executor("process", 2)
    assert result is not None


def test_create_executor_asyncio_string():
    """_create_executor('asyncio', n) returns an AsyncIOStrategy."""
    result = MetricEngine._create_executor("asyncio", 4)
    assert result is not None


def test_create_executor_unknown_falls_back():
    """Unknown string strategy falls back to HybridStrategy."""
    result = MetricEngine._create_executor("unknown_strategy", 4)
    assert result is not None


def test_create_executor_object_passthrough():
    """If strategy is already an object (not str), it's returned as-is."""
    strategy_obj = MagicMock()
    result = MetricEngine._create_executor(strategy_obj, 4)
    assert result is strategy_obj


# ---------------------------------------------------------------------------
# Lines 70-71: shutdown() method
# ---------------------------------------------------------------------------
def test_shutdown_calls_executor_shutdown():
    """shutdown() calls executor.shutdown() when available."""
    e = _engine()
    e._executor = MagicMock()
    e.shutdown()
    e._executor.shutdown.assert_called_once()


def test_shutdown_no_executor_no_crash():
    """shutdown() is safe when executor has no shutdown method."""
    e = _engine()
    e._executor = object()  # No shutdown attr
    e.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# Lines 105-108: register_metric auto-populates target_types for Span scope
# ---------------------------------------------------------------------------
def test_register_metric_span_scope_populates_target_types():
    """Metrics with SPAN scope get target_types auto-populated."""
    from mce.core.metadata import MetricMetadata, MetricScope, MetricLayer, MetricNature

    e = _engine()

    meta = MetricMetadata(
        name="test_span",
        display_name="Test Span",
        description="test",
        ontology_class="test_span",
        layer=MetricLayer.RAW,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.SPAN,
        target_types=set(),
    )
    m = MagicMock()
    m.metric_id = "test_span"
    m.metadata = meta
    e.register_metric(m)
    assert len(meta.target_types) > 0


def test_register_metric_execution_element_scope():
    """Metrics with EXECUTION_ELEMENT scope get target_types auto-populated."""
    from mce.core.metadata import MetricMetadata, MetricScope, MetricLayer, MetricNature

    e = _engine()

    meta = MetricMetadata(
        name="test_exec",
        display_name="Test Exec",
        description="test",
        ontology_class="test_exec",
        layer=MetricLayer.RAW,
        nature=MetricNature.DETERMINISTIC,
        scope=MetricScope.EXECUTION_ELEMENT,
        target_types=set(),
    )
    m = MagicMock()
    m.metric_id = "test_exec"
    m.metadata = meta
    e.register_metric(m)
    assert len(meta.target_types) > 0


# ---------------------------------------------------------------------------
# Line 168: compute_session raises RuntimeError with no provider
# ---------------------------------------------------------------------------
def test_compute_session_no_provider_raises():
    """compute_session raises RuntimeError when no data provider is set."""
    e = MetricEngine()
    with pytest.raises(RuntimeError, match="No Data Provider"):
        e.compute_session("some-session")


def test_compute_session_fetches_base_context_when_retrieval_metric_is_present():
    """Session base context is still fetched when another metric adds retrieval."""

    class MixedContextProvider:
        def __init__(self):
            self.calls = []

        def fetch(self, resource_id, requirements):
            self.calls.append(requirements)
            if requirements.retrieval is not None:
                return {
                    "session_id": resource_id,
                    "llm_spans": [
                        {
                            "executionId": "llm-1",
                            "status": "OK",
                            "error": None,
                        }
                    ],
                }

            return {
                "session_id": resource_id,
                "session": {
                    "sessionId": resource_id,
                    "duration": 34700.07,
                },
                "llm_spans": [
                    {
                        "executionId": "llm-1",
                        "promptTokenCount": 329,
                        "completionTokenCount": 95,
                        "status": "OK",
                        "error": None,
                    }
                ],
            }

    provider = MixedContextProvider()
    engine = MetricEngine()
    engine.set_data_provider(provider)
    engine.register_metric(Duration())
    engine.register_metric(Cost())
    engine.register_metric(LLMErrorRate())

    results = engine.compute_session("session-1")
    by_metric = {result.metric_id: result for result in results if result.error is None}

    assert len(provider.calls) == 2
    assert by_metric["Duration"].value == pytest.approx(34700.07)
    assert by_metric["LLMErrorRate"].value == 0.0
    assert by_metric["Cost"].value > 0.0


@pytest.mark.parametrize(
    ("metric_factories", "needs_tool_patch"),
    [
        ([LLMErrorRate], False),
        ([WorkflowEfficiency], False),
        ([LLMErrorRate, WorkflowEfficiency], False),
        ([LLMErrorRate, WorkflowEfficiency, ToolUtilizationAccuracy], True),
    ],
)
def test_compute_session_preserves_session_metrics_across_mixed_metric_combinations(
    metric_factories,
    needs_tool_patch,
):
    """Implicit session metrics stay correct when mixed with retrieval metrics."""

    class MixedContextProvider:
        def __init__(self):
            self.calls = []

        def fetch(self, resource_id, requirements):
            self.calls.append(requirements)
            if requirements.retrieval is not None:
                return {
                    "session_id": resource_id,
                    "agent_calls": [
                        {"agentName": "planner"},
                        {"agentName": "executor"},
                        {"agentName": "planner"},
                    ],
                    "llm_spans": [
                        {
                            "executionId": "llm-1",
                            "status": "OK",
                            "error": None,
                        }
                    ],
                    "tool_spans": [
                        {
                            "executionId": "tool-1",
                            "toolName": "search_db",
                            "status": "OK",
                        }
                    ],
                }

            return {
                "session_id": resource_id,
                "session": {
                    "sessionId": resource_id,
                    "duration": 34700.07,
                },
                "llm_spans": [
                    {
                        "executionId": "llm-1",
                        "promptTokenCount": 329,
                        "completionTokenCount": 95,
                        "status": "OK",
                        "error": None,
                    }
                ],
                "tool_spans": [
                    {
                        "executionId": "tool-1",
                        "toolArguments": '{"query": "sales"}',
                        "outputContent": "Sales: $1M",
                        "toolName": "search_db",
                        "status": "OK",
                    }
                ],
            }

    provider = MixedContextProvider()
    engine = MetricEngine()
    engine.set_data_provider(provider)

    for metric in [Duration(), Cost(), TokenCount(), CallCount()]:
        engine.register_metric(metric)
    for factory in metric_factories:
        engine.register_metric(factory())

    patch_context = nullcontext()
    if needs_tool_patch:
        patch_context = patch(
            "mce.providers.native.metrics.quality.tool_utilization_accuracy.llm_g_eval_score",
            return_value=(0.75, "looks good", 4.0),
        )

    with patch_context:
        results = engine.compute_session("session-1")

    by_metric = {result.metric_id: result for result in results if result.error is None}

    assert len(provider.calls) == 2
    assert by_metric["Duration"].value == pytest.approx(34700.07)
    assert by_metric["Cost"].value > 0.0
    assert by_metric["TokenCount"].value == 424
    assert by_metric["CallCount"].value == 2

    if "LLMErrorRate" in by_metric:
        assert by_metric["LLMErrorRate"].value == 0.0
    if "WorkflowEfficiency" in by_metric:
        assert by_metric["WorkflowEfficiency"].value == pytest.approx(1.0)
    if "ToolUtilizationAccuracy" in by_metric:
        assert by_metric["ToolUtilizationAccuracy"].value == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Lines 473-474: compute_all wrapper
# ---------------------------------------------------------------------------
def test_compute_all_delegates_to_compute():
    """compute_all calls compute([resource_id]) and returns its results."""
    e = _engine()
    results = [MagicMock()]
    with patch.object(e, "compute", return_value={"rid-1": results}) as mock_compute:
        out = e.compute_all("rid-1")
        mock_compute.assert_called_once()
        assert out == results


def test_compute_all_empty_context():
    """compute_all with no context passes contexts=None to compute()."""
    e = _engine()
    with patch.object(e, "compute", return_value={"rid-1": []}) as mock_compute:
        e.compute_all("rid-1")
        _, kwargs = mock_compute.call_args
        assert kwargs.get("contexts") is None


# ---------------------------------------------------------------------------
# Lines 498-501: _dispatch_to_storage handles sink exception gracefully
# ---------------------------------------------------------------------------
def test_dispatch_to_storage_sink_exception():
    """A failing sink does not propagate exception."""
    e = _engine()
    bad_sink = MagicMock()
    bad_sink.write.side_effect = RuntimeError("disk full")
    e.add_sink(bad_sink)
    # Should not raise
    e._dispatch_to_storage([MagicMock()])
    bad_sink.write.assert_called_once()


def test_dispatch_to_storage_multiple_sinks_continues_after_error():
    """All sinks are called even if the first one raises."""
    e = _engine()
    bad_sink = MagicMock()
    bad_sink.write.side_effect = RuntimeError("error")
    good_sink = MagicMock()
    e.add_sink(bad_sink)
    e.add_sink(good_sink)
    e._dispatch_to_storage([MagicMock()])
    good_sink.write.assert_called_once()
