#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import pytest
import worker_base.base_worker as base_worker_module

from normal_behaviour_worker.worker import NormalBehaviourInputMessage, NormalBehaviourWorker
from normal_behaviour_worker.wrapper import normal_behaviour_wrapper


def _make_fake_dal():
    class FakeKGDAL:
        def analysis_pre_check(self, **kwargs):
            return True

        def get_analysis_data_for_semantic_group(self, *args):
            return [
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
            ]

        def ingest_normal_behaviour_report(self, **kwargs):
            return True

    return FakeKGDAL()


@pytest.mark.asyncio
async def test_handle_message_returns_true(monkeypatch):
    fake_dal = _make_fake_dal()
    monkeypatch.setattr(base_worker_module, "get_neo4j_connector", lambda: None)
    monkeypatch.setattr(base_worker_module, "OXPApiDALAdapter", lambda connector: fake_dal)

    class FakeWrapper:
        def __init__(self, **kwargs):
            pass

        def process_group(self, data):
            from dem.normal_behaviour.utils import NormalBehaviourSessions

            class FakeReport:
                __dict__ = {"centroid": {}, "statistic": "gaussian"}

            return [
                NormalBehaviourSessions(
                    normal_behaviour=FakeReport(), session_ids=["s1", "s2"], layer="metric", metadata={}
                )
            ]

    monkeypatch.setattr(normal_behaviour_wrapper, "NormalBehaviourWrapper", FakeWrapper)

    worker = NormalBehaviourWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="new_session_to_normal_behaviour",
        embedding_model="azure/text-embedding-3-small",
    )

    msg = NormalBehaviourInputMessage(session_id="s1", group_id="g1", group_hash="h1", sessions=[])
    result = await worker.handle_message(msg)

    assert result is True
    assert len(worker.output_messages) == 1
    assert worker.output_messages[0].group_id == "g1"
    assert worker.output_messages[0].session_id == "s1"


def test_queue_name_constant():
    from normal_behaviour_worker import queues

    assert queues.NEW_SESSION_TO_NORMAL_BEHAVIOUR_Q == "new_session_to_normal_behaviour"
