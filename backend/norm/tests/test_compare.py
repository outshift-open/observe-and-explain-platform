#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

from norm import normalize
from norm.compare import compare_kg, read_kg_json, write_kg_json


def _minimal_spans():
    return [
        {
            "Timestamp": "2026-01-01 00:00:00.000000000",
            "SpanId": "s1",
            "ParentSpanId": "",
            "SpanName": "planner.agent",
            "Duration": 5_000_000_000,
            "SpanAttributes": {
                "application_id": "app",
                "session.id": "app_sess-1",
                "agent_id": "planner",
                "ioa_observe.entity.input": "hello",
                "ioa_observe.entity.output": "world",
            },
        },
        {
            "Timestamp": "2026-01-01 00:00:01.000000000",
            "SpanId": "s2",
            "ParentSpanId": "s1",
            "SpanName": "planner.tool",
            "Duration": 3_000_000_000,
            "SpanAttributes": {
                "application_id": "app",
                "session.id": "app_sess-1",
                "agent_id": "planner",
                "ioa_observe.agent.span_id": "s1",
                "ioa_observe.entity.name": "search",
            },
        },
    ]


def _graph_doc():
    nodes, edges = normalize(_minimal_spans())
    return {"nodes": nodes, "edges": edges}


def test_compare_kg_passes_for_equivalent_graphs() -> None:
    doc = _graph_doc()
    result = compare_kg(doc, doc)
    assert result.passed
    assert result.summary["failed"] == 0


def test_write_and_read_kg_json_round_trip(tmp_path) -> None:
    doc = _graph_doc()
    path = tmp_path / "kg.json"
    write_kg_json(doc, path)
    loaded = read_kg_json(path)
    assert len(loaded["nodes"]) == len(doc["nodes"])
    assert json.loads(path.read_text(encoding="utf-8"))["nodes"]
