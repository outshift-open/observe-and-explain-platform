#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import pytest
from worker_base.queue_message import SessionDetailMessage

import mce_worker.worker as mce_worker_module
from mce_worker.worker import MCEWorker


@pytest.mark.asyncio
async def test_handle_message_returns_true_on_success(monkeypatch):
    class FakeMCEWrapper:
        def __init__(self, **kwargs):
            pass

        async def process_mce_session(self, session_id, local_file=None):
            return {"session_metrics": []}

    monkeypatch.setattr(mce_worker_module, "MCEWrapper", FakeMCEWrapper)

    worker = MCEWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="in",
        output_queue=["out"],
    )

    msg = SessionDetailMessage(session_id="session-1")
    result = await worker.handle_message(msg)
    assert result is True


@pytest.mark.asyncio
async def test_handle_message_passes_session_id_and_local_file(monkeypatch):
    received = {}

    class FakeMCEWrapper:
        def __init__(self, **kwargs):
            pass

        async def process_mce_session(self, session_id, local_file=None):
            received["session_id"] = session_id
            received["local_file"] = local_file
            return {"session_metrics": []}

    monkeypatch.setattr(mce_worker_module, "MCEWrapper", FakeMCEWrapper)

    worker = MCEWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="in",
        output_queue=[],
    )

    msg = SessionDetailMessage(session_id="session-42", local_file="/tmp/session.json")
    await worker.handle_message(msg)

    assert received["session_id"] == "session-42"
    assert received["local_file"] == "/tmp/session.json"


@pytest.mark.asyncio
async def test_handle_message_preserves_all_fields(monkeypatch):
    class FakeMCEWrapper:
        def __init__(self, **kwargs):
            pass

        async def process_mce_session(self, session_id, local_file=None):
            return {"session_metrics": []}

    monkeypatch.setattr(mce_worker_module, "MCEWrapper", FakeMCEWrapper)

    worker = MCEWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="in",
        output_queue=["out"],
    )

    msg = SessionDetailMessage(
        session_id="session-3",
        workflow_id="wf-1",
        metrics={"existing": 1},
        input_content="hello",
        output_content="world",
        execution_graph={},
    )
    await worker.handle_message(msg)

    out = worker.output_messages[0]
    assert out.session_id == "session-3"
    assert out.input_content == "hello"
    assert out.output_content == "world"
    assert out.metrics == {"existing": 1}
