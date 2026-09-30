#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import pytest
from worker_base.queue_message import SessionGroupMessage

import grouping_worker.worker as worker_module
from grouping_worker.worker import GroupingWorker


def _make_fake_wrapper():
    class FakeWrapper:
        def __init__(self, **kwargs):
            pass

        async def wait_for_hierarchical_grouping_unlock(self):
            return True

        def get_analysis_data_for_semantic_group(self, group_id, node_hash, embedding_model):
            return [
                {
                    "session_id": "s1",
                    "metrics": {"Cost": 0.5},
                    "input_content": "q1",
                    "input_embedding": [0.1] * 10,
                    "output_content": "a1",
                    "output_embedding": [0.2] * 10,
                    "execution_graph": {},
                }
            ]

        def process_session(self, session_id):
            from grouping_worker.wrapper.grouping_wrapper import GroupInfo

            return GroupInfo(group_id="group-1", node_hash="hash-abc")

    return FakeWrapper


@pytest.mark.asyncio
async def test_handle_message_returns_true(monkeypatch):
    monkeypatch.setattr(worker_module, "GroupingWrapper", _make_fake_wrapper())

    worker = GroupingWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="new_session_to_grouping",
        embedding_model="azure/text-embedding-3-small",
    )

    from worker_base.queue_message import SessionDetailMessage

    msg = SessionDetailMessage(session_id="s1")
    result = await worker.handle_message(msg)

    assert result is True
    assert len(worker.output_messages) == 1
    assert isinstance(worker.output_messages[0], SessionGroupMessage)
    assert worker.output_messages[0].group_id == "group-1"
    assert worker.output_messages[0].session_id == "s1"
    assert len(worker.output_messages[0].sessions) == 1


def test_queue_name_constant():
    from grouping_worker import queues

    assert queues.NEW_SESSION_TO_GROUPING_Q == "new_session_to_grouping"
