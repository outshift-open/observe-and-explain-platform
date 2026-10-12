#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json

from norm import InMemoryGraph

from rt_norm_worker.store import Neo4jStore
from rt_norm_worker.worker import read_spans, run

SPAN = {
    "Timestamp": "2026-07-09 12:00:00.000000000",
    "SpanId": "span-1",
    "ParentSpanId": "",
    "SpanName": "concierge.agent",
    "Duration": 1_000_000_000,
    "SpanAttributes": {"application_id": "app", "session.id": "app_s1", "agent_id": "concierge"},
}


class FakeDB:
    def __init__(self):
        self.commands = []

    def execute_command(self, command, params=None):
        self.commands.append((command, params))


def test_read_spans(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([{"SpanId": "a"}, {"SpanId": "b"}]))
    assert list(read_spans(f)) == [{"SpanId": "a"}, {"SpanId": "b"}]


def test_run_writes_each_span_to_graph(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([SPAN]))
    graph = InMemoryGraph()
    assert run(graph, f) == 1
    assert any(node_type == "AgentCall" for node_type, _ in graph.nodes)
    assert graph.edges


def test_neo4j_store_writes_delta(tmp_path):
    db = FakeDB()
    db.execute = lambda query, params=None: []  # nothing stored yet
    f = tmp_path / "t.json"
    f.write_text(json.dumps([SPAN]))
    assert run(Neo4jStore(db), f) == 1
    assert any("AgentCall" in c for c, _ in db.commands if c.startswith("MERGE (n:"))
    assert any("MERGE (a)-[r:" in c for c, _ in db.commands)


def test_existing_nodes_keep_start_and_end_time():
    db = FakeDB()
    Neo4jStore(db)._upsert_node(
        {"node_type": "AgentCall", "id": "x", "startTime": 1.0, "endTime": 2.0, "name": "n"}
    )
    _, params = db.commands[0]
    assert params["props"]["startTime"] == 1.0
    assert "startTime" not in params["on_match"] and "endTime" not in params["on_match"]
    assert params["on_match"]["name"] == "n"
