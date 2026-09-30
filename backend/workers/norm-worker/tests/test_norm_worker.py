#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from norm_worker import worker as norm_worker_module
from norm_worker.worker import NormWorker
from norm_worker.wrapper import norm_wrapper as norm_wrapper_module


@pytest.mark.asyncio
async def test_handle_message_returns_none_when_normalization_fails(monkeypatch):
    class FakeWrapper:
        def __init__(self, **_):
            pass

        def retrieve_and_normalize(self, session_id):
            return None

        def ingest_to_neo4j(self, kg):
            raise AssertionError("ingest_to_neo4j should not be called when normalization fails")

    monkeypatch.setattr(norm_worker_module, "NormWrapper", FakeWrapper)

    worker = NormWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="in",
        output_queue=["out"],
    )

    msg = SimpleNamespace(session_id="session-1", local_file=None)
    result = await worker.handle_message(msg)
    assert result is None


@pytest.mark.asyncio
async def test_handle_message_returns_none_when_neo4j_push_fails(monkeypatch):
    fake_kg = {"nodes": [], "edges": [], "run_id": "session-2"}

    class FakeWrapper:
        def __init__(self, **_):
            pass

        def retrieve_and_normalize(self, session_id):
            return fake_kg

        def ingest_to_neo4j(self, kg):
            return False

    monkeypatch.setattr(norm_worker_module, "NormWrapper", FakeWrapper)

    worker = NormWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="in",
        output_queue=["out"],
    )

    msg = SimpleNamespace(session_id="session-2", local_file=None)
    result = await worker.handle_message(msg)
    assert result is None


@pytest.mark.asyncio
async def test_handle_message_happy_path(monkeypatch):
    calls = {"retrieve": False, "ingest": False}
    fake_kg = {"nodes": [{"id": "n1"}], "edges": [], "run_id": "session-3"}

    class FakeWrapper:
        def __init__(self, **_):
            pass

        def retrieve_and_normalize(self, session_id):
            calls["retrieve"] = True
            assert session_id == "session-3"
            return fake_kg

        def ingest_to_neo4j(self, kg):
            calls["ingest"] = True
            assert kg is fake_kg
            return True

    monkeypatch.setattr(norm_worker_module, "NormWrapper", FakeWrapper)

    worker = NormWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="in",
        output_queue=["out"],
        debug=True,
        override=True,
    )

    msg = SimpleNamespace(session_id="session-3", local_file=None)
    result = await worker.handle_message(msg)
    assert result is True
    assert calls["retrieve"] is True
    assert calls["ingest"] is True


def test_push_to_neo4j_uses_injected_db_handler():
    """_push_to_neo4j must have no Neo4j connection logic of its own -- it
    delegates straight to the injected db_handler's ingest_normalized_kg,
    nothing more. The connector itself is built once by NormWorker and never
    touched by the wrapper."""
    calls = {
        "nodes": None,
        "edges": None,
        "run_id": None,
        "override": None,
    }

    class FakeDBHandler:
        def ingest_normalized_kg(self, nodes, edges, run_id, override, batch_size=200):
            calls["nodes"] = nodes
            calls["edges"] = edges
            calls["run_id"] = run_id
            calls["override"] = override
            return True

    wrapper = norm_wrapper_module.NormWrapper(db_handler=FakeDBHandler(), override=True)
    kg = {
        "run_id": "session-1",
        "app_name": "test-app",
        "nodes": [{"node_type": "Session", "id": "session-node"}],
        "edges": [],
    }

    assert wrapper._push_to_neo4j(kg) is True
    assert calls["run_id"] == "session-1"
    assert calls["override"] is True
    assert calls["nodes"] == [{"node_type": "Session", "id": "session-node"}]
    assert calls["edges"] == []


def test_fetch_spans_uses_oxp_api_local_client(monkeypatch):
    calls = {
        "db": None,
        "session_ids": None,
        "limit": None,
        "order": None,
    }

    class FakeDbConnector:
        pass

    class FakeSpan:
        span_id = "abc123"
        session_id = "session-9"
        span_name = "workflow.agent"
        span_type = "agent"
        timestamp = "2026-07-09T12:00:00+00:00"
        duration = 1_000_000
        status_code = "StatusCode.OK"
        parent_span_id = ""
        service_name = "test-service"
        span_attributes = {"ioa_observe.span.kind": "agent"}

    class FakeLocalClient:
        def __init__(self, db):
            calls["db"] = db

        def get_session_spans(self, *, session_ids, limit, order):
            calls["session_ids"] = session_ids
            calls["limit"] = limit
            calls["order"] = order
            return SimpleNamespace(spans=[FakeSpan()])

    def fake_get_db():
        yield FakeDbConnector()

    monkeypatch.setattr(
        norm_wrapper_module,
        "get_db",
        fake_get_db,
    )
    monkeypatch.setattr(norm_wrapper_module, "OXPLocalClient", FakeLocalClient)

    wrapper = norm_wrapper_module.NormWrapper(db_handler=object())
    spans = wrapper._fetch_spans("session-9")

    assert isinstance(calls["db"], FakeDbConnector)
    assert calls["session_ids"] == ["session-9"]
    assert calls["limit"] == 10000
    assert calls["order"] == "asc"

    assert spans is not None
    assert len(spans) == 1
    assert isinstance(spans[0], FakeSpan)
    assert spans[0].span_name == "workflow.agent"
    assert spans[0].session_id == "session-9"


@pytest.mark.asyncio
async def test_worker_logs_neo4j_writes_to_json(monkeypatch, tmp_path):
    """Integration test that captures Neo4j writes from the worker and logs them to JSON.

    This test intercepts the oxp_api_ingest_normalized_kg call to capture all nodes
    and edges before they're written to Neo4j, then logs them to a JSON file.
    """
    output_file = tmp_path / "neo4j_writes.json"
    captured_data = []

    class FakeSpan:
        span_id = "0000000000000001"
        session_id = "session-test-1"
        span_name = "workflow.agent"
        span_type = "agent"
        timestamp = "2026-07-09 12:00:00.000000"
        duration = 1_000_000
        status_code = "StatusCode.OK"
        parent_span_id = ""
        service_name = "test-service"
        span_attributes = {
            "application_id": "test-app",
            "session.id": "test-app_session-test-1",
            "agent_id": "test-agent",
            "ioa_start_time": "1783670400.0",
        }
        links_trace_id = []
        links_span_id = []
        links_trace_state = []
        links_attributes = []

    class FakeDbConnector:
        pass

    class FakeLocalClient:
        def __init__(self, db):
            pass

        def get_session_spans(self, *, session_ids, limit, order):
            return SimpleNamespace(spans=[FakeSpan()])

    def fake_get_db():
        yield FakeDbConnector()

    # Capture the actual nodes and edges being written
    def capturing_ingest_normalized_kg(db, nodes, edges, run_id, override, batch_size=200):
        captured_data.append(
            {
                "run_id": run_id,
                "override": override,
                "batch_size": batch_size,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "nodes": [json.loads(json.dumps(n, default=str)) for n in nodes],
                "edges": [json.loads(json.dumps(e, default=str)) for e in edges],
            }
        )
        return True

    class FakeConnector:
        pass

    monkeypatch.setattr(norm_wrapper_module, "get_db", fake_get_db)
    monkeypatch.setattr(norm_wrapper_module, "OXPLocalClient", FakeLocalClient)
    # The Neo4j connector and oxp_api_ingest_normalized_kg are now owned by
    # NormWorker/OXPApiNormDALAdapter (worker.py), not by NormWrapper.
    monkeypatch.setattr(
        norm_worker_module,
        "get_neo4j_connector",
        lambda: FakeConnector(),
    )
    monkeypatch.setattr(
        norm_worker_module,
        "oxp_api_ingest_normalized_kg",
        capturing_ingest_normalized_kg,
    )

    worker = NormWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="in",
        output_queue=["out"],
    )

    msg = SimpleNamespace(session_id="session-test-1", local_file=None)
    result = await worker.handle_message(msg)

    assert result is True
    assert len(captured_data) > 0

    # Log all writes to JSON file
    log_data = {
        "test": "worker_neo4j_writes",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_captures": len(captured_data),
            "total_nodes": sum(c["node_count"] for c in captured_data),
            "total_edges": sum(c["edge_count"] for c in captured_data),
        },
        "writes": captured_data,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"neo4j_writes.json created at: {output_file}")
    with open(output_file, "w") as f:
        json.dump(log_data, f, indent=2, default=str)

    assert output_file.exists()
    with open(output_file) as f:
        data = json.load(f)
        assert data["summary"]["total_nodes"] > 0
