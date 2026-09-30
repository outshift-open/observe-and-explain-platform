#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mce.providers.native.metrics import (
    CyclesCount,
    GraphDeterminismScore,
    LLMAverageConfidence,
)


def test_cycles_count():
    metric = CyclesCount()

    # A -> B -> A -> B (1 distinct contiguous cycle "A, B" repeated)
    spans = [{"toolName": "A"}, {"toolName": "B"}, {"toolName": "A"}, {"toolName": "B"}]
    # The metric logic counts repeations of any length >= 1.
    # Pattern: [A, B] appears at 0, repeats at 2.
    res = metric.compute("id", context={"spans": spans})
    assert res.value >= 1.0


def test_determinism_empty():
    metric = GraphDeterminismScore()
    # Should handle empty sessions gracefully
    res = metric.compute("id", context={"sessions": []})
    assert res.value == -1  # Or whatever default for empty


def test_confidence_empty():
    metric = LLMAverageConfidence()
    res = metric.compute("id", context={"llm_spans": []})
    assert res.value == 0.0
