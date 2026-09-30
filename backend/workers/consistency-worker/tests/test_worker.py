#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import pytest

import consistency_worker.worker as worker_module
from consistency_worker.worker import ConsistencyInputMessage, ConsistencyWorker


def _make_fake_wrapper():
    class FakeWrapper:
        def __init__(self, **kwargs):
            pass

        def process_group(self, data):
            from dem.consistency import ConsistencySessions
            from dem.consistency.utils import ConsistencyResult

            result = ConsistencyResult(
                min=0.0,
                max=1.0,
                mean=0.9,
                confidence_interval=(0.8, 1.0),
                confidence_indicator="High",
                statistic="std",
            )
            return [
                ConsistencySessions(consistency_result=result, session_ids=["s1", "s2"], layer="metric", metadata={})
            ]

        def ingest_consistency(self, kg_dal, reports, group_id, node_hash=""):
            return True

    return FakeWrapper


@pytest.mark.asyncio
async def test_handle_message_returns_true(monkeypatch):
    import worker_base.base_worker as base_worker_module

    def _no_connector():
        raise RuntimeError("no db configured for test")

    monkeypatch.setattr(base_worker_module, "get_neo4j_connector", _no_connector)
    monkeypatch.setattr(worker_module, "ConsistencyWrapper", _make_fake_wrapper())

    worker = ConsistencyWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="new_session_to_consistency",
        embedding_model="azure/text-embedding-3-small",
    )

    msg = ConsistencyInputMessage(
        session_id="s1",
        group_id="g1",
        group_hash="h1",
        sessions=[
            {
                "session_id": "s1",
                "metrics": {"Cost": 0.5},
                "input_content": "q1",
                "input_embedding": [0.1] * 10,
                "output_content": "a1",
                "output_embedding": [0.2] * 10,
                "execution_graph": {},
            },
            {
                "session_id": "s2",
                "metrics": {"Cost": 0.6},
                "input_content": "q2",
                "input_embedding": [0.3] * 10,
                "output_content": "a2",
                "output_embedding": [0.4] * 10,
                "execution_graph": {},
            },
        ],
    )
    result = await worker.handle_message(msg)

    assert result is True
    assert len(worker.output_messages) == 1
    assert worker.output_messages[0].group_id == "g1"
    assert len(worker.output_messages[0].consistency) == 1


def test_queue_name_constant():
    from consistency_worker import queues

    assert queues.NEW_SESSION_TO_CONSISTENCY_Q == "new_session_to_consistency"
