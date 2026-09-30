#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
from mce.providers.native.metrics import (
    GraphDeterminismScore,
    ToolError,
    LLMAverageConfidence,
)


class MockSpan:
    def __init__(self, name, type="tool", status="OK", logprobs=None):
        self.toolName = name
        self.entity_type = type
        self.status_code = status
        self.output_payload = {"logprobs": {"content": logprobs}} if logprobs else {}
        self.attributes = {}


class MockSession:
    def __init__(self, spans):
        self.spans = spans
        self.llm_spans = [s for s in spans if s.entity_type == "llm"]


def test_tool_error_metric():
    metric = ToolError()

    # Test Success
    res = metric.compute("span-1", context={"status_code": "OK", "error": None})
    assert res.value == 0.0

    # Test Failure
    res = metric.compute("span-2", context={"status_code": "ERROR", "error": "timeout"})
    assert res.value == 1.0


def test_graph_determinism():
    metric = GraphDeterminismScore()

    # Session 1: A -> B
    s1 = MockSession([MockSpan("A", type="agent"), MockSpan("B", type="tool")])

    # Session 2: A -> B
    s2 = MockSession([MockSpan("A", type="agent"), MockSpan("B", type="tool")])

    # Identical graphs -> variance 0
    res = metric.compute("pop-1", context={"sessions": [s1, s2]})
    assert res.value == 0.0

    # Session 3: A -> C
    s3 = MockSession([MockSpan("A", type="agent"), MockSpan("C", type="tool")])

    # Diff graphs -> variance > 0
    res = metric.compute("pop-2", context={"sessions": [s1, s3]})
    assert res.value > 0.0


def test_llm_confidence():
    metric = LLMAverageConfidence()

    # Logprob 0.0 -> probability 1.0
    s1 = MockSession(
        [MockSpan("L1", type="llm", logprobs=[{"logprob": 0.0}, {"logprob": 0.0}])]
    )

    res = metric.compute("sess-1", context={"session": s1})
    assert res.value == pytest.approx(1.0)

    # Logprob -0.693 -> probability 0.5
    s2 = MockSession([MockSpan("L2", type="llm", logprobs=[{"logprob": -0.693147}])])

    res = metric.compute("sess-2", context={"session": s2})
    assert res.value == pytest.approx(0.5, rel=1e-3)
