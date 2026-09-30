#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E402

"""Tests targeting missed wrapper.py (deepeval) lines."""

import sys
from unittest.mock import MagicMock, patch

# Inject deepeval stubs
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

from mce.providers.deepeval.wrapper import DeepEvalMetricWrapper
from mce.core.metric import MetricResult


def _wrapper(model=None):
    """Construct a wrapper with deepeval stubs injected."""
    w = DeepEvalMetricWrapper(
        "TestMetric", {"requirements": {"aggregation_level": "session"}}
    )
    w._provider = None  # Reset so _get_provider uses mock
    if model is not None:
        w._model = model
    else:
        w._model = None
    return w


# ---------------------------------------------------------------------------
# Line 50: _get_provider with _model set calls set_model
# ---------------------------------------------------------------------------
def test_get_provider_with_model_calls_set_model():
    """When _model is set, _get_provider() calls set_model on the provider."""
    w = _wrapper(model="gpt-4-turbo")
    mock_prov = MagicMock()
    with patch(
        "mce.providers.deepeval.wrapper.DeepEvalProvider", return_value=mock_prov
    ):
        prov = w._get_provider()
    mock_prov.set_model.assert_called_once_with("gpt-4-turbo")
    assert prov is mock_prov


def test_get_provider_without_model_no_set_model():
    """When _model is None, set_model is NOT called."""
    w = _wrapper(model=None)
    mock_prov = MagicMock()
    with patch(
        "mce.providers.deepeval.wrapper.DeepEvalProvider", return_value=mock_prov
    ):
        prov = w._get_provider()
    mock_prov.set_model.assert_not_called()
    assert prov is mock_prov


def test_get_provider_returns_cached():
    """Second call reuses cached provider (no new instantiation)."""
    w = _wrapper()
    mock_prov = MagicMock()
    with patch(
        "mce.providers.deepeval.wrapper.DeepEvalProvider", return_value=mock_prov
    ) as cls:
        w._get_provider()
        w._get_provider()
    assert cls.call_count == 1


# ---------------------------------------------------------------------------
# Lines 68-100: compute_batch parallel execution
# ---------------------------------------------------------------------------
def test_compute_batch_empty_resources_returns_empty():
    """compute_batch with empty lists returns []."""
    w = _wrapper()
    result = w.compute_batch([], [])
    assert result == []


def test_compute_batch_single_item():
    """compute_batch with one resource calls compute and returns result."""
    w = _wrapper()
    expected = MetricResult(
        metric_id="TestMetric", resource_id="r1", provider="DeepEval", value=0.9
    )
    with patch.object(w, "compute", return_value=expected):
        results = w.compute_batch(["r1"], [{"ctx": "a"}])
    assert len(results) == 1
    assert results[0].value == 0.9


def test_compute_batch_multiple_items_parallel():
    """compute_batch with multiple resources processes all in parallel."""
    w = _wrapper()
    call_count = 0

    def fake_compute(rid, ctx):
        nonlocal call_count
        call_count += 1
        return MetricResult(
            metric_id="TestMetric", resource_id=str(rid), provider="DeepEval", value=0.5
        )

    with patch.object(w, "compute", side_effect=fake_compute):
        results = w.compute_batch(["r1", "r2", "r3", "r4"], [{} for _ in range(4)])
    assert len(results) == 4
    assert call_count == 4


def test_compute_batch_exception_captured_as_error_result():
    """When compute raises, compute_batch returns MetricResult with error set."""
    w = _wrapper()
    with patch.object(w, "compute", side_effect=ValueError("compute failed")):
        results = w.compute_batch(["r1"], [{}])
    assert len(results) == 1
    assert results[0].error is not None
    assert "compute failed" in results[0].error


def test_compute_batch_preserves_order():
    """Results are returned in the same order as input resources."""
    w = _wrapper()
    rid_to_value = {"r0": 0.1, "r1": 0.2, "r2": 0.3}

    def fake_compute(rid, ctx):
        return MetricResult(
            metric_id="TestMetric",
            resource_id=str(rid),
            provider="DeepEval",
            value=rid_to_value[str(rid)],
        )

    with patch.object(w, "compute", side_effect=fake_compute):
        results = w.compute_batch(["r0", "r1", "r2"], [{} for _ in range(3)])
    assert [r.value for r in results] == [0.1, 0.2, 0.3]
