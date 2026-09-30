#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock
from mce.providers.native.metrics import (
    GraphDeterminismScore,
)
from mce.providers.native.metrics.uncertainty.llm_confidence import _extract_logprobs
from mce.core.helpers import _find_key_value


def test_find_key_value():
    data = {"a": {"b": {"c": 1}}}
    assert _find_key_value(data, "c") == 1
    assert _find_key_value(data, "d") is None

    # List recursion
    data_list = [{"k": "v"}, {"target": 123}]
    assert _find_key_value(data_list, "target") == 123


def test_extract_logprobs():
    # Direct payload
    payload = {"logprobs": {"content": [{"logprob": -0.1}, {"logprob": -0.2}]}}
    span = {"output_payload": payload}
    assert _extract_logprobs(span) == [-0.1, -0.2]

    # Nested payload
    nested = {"data": {"nested_output": payload}}
    span2 = {"output_payload": nested}
    assert _extract_logprobs(span2) == [-0.1, -0.2]

    # Missing/Empty
    assert _extract_logprobs({}) == []


def test_graph_determinism_score():
    metric = GraphDeterminismScore()

    # 2 sessions, identical graphs (A->B)
    # Edit distance = 0

    s1 = MagicMock()
    s1.spans = [
        {"entity_type": "tool", "entity_name": "A"},
        {"entity_type": "tool", "entity_name": "B"},
    ]
    # MagicMock attrs need careful handling if code uses _span_dict helper which checks __dict__
    # The helper says: return getattr(span, "__dict__", {}) if not dict.
    # MagicMock doesn't have __dict__ populated with arbitrary keys by default in the way _span_dict expects if it's looking for data fields.
    # So better use dicts for spans.

    s1_spans = [{"toolName": "A"}, {"toolName": "B"}]
    s1.spans = s1_spans

    s2 = MagicMock()
    s2.spans = [{"toolName": "A"}, {"toolName": "B"}]

    ctx = {"sessions": [s1, s2]}
    res = metric.compute("id", ctx)
    assert res.value == 0.0  # No variance

    # Different graphs
    s3 = MagicMock()
    s3.spans = [{"toolName": "A"}, {"toolName": "C"}]

    ctx_diff = {"sessions": [s1, s3]}
    res_diff = metric.compute("id", ctx_diff)
    # A->B vs A->C. Edges: {(A,B)} vs {(A,C)}. Sym diff size = 2.
    assert res_diff.value == 2.0
