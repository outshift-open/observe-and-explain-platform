#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from worker_base.queue_message import BaseTriggerMessage, SessionGroupMessage

from hierarchical_grouping_worker.worker import HierarchicalGroupingWorker


class TestHierarchicalGroupingWorker:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        self.patcher_wrapper = patch("hierarchical_grouping_worker.worker.HierarchicalGroupingWrapper")
        self.mock_wrapper_class = self.patcher_wrapper.start()
        self.mock_wrapper_instance = self.mock_wrapper_class.return_value
        self.mock_wrapper_instance.compute_semantic_groups = AsyncMock(return_value=[])
        self.mock_wrapper_instance.db_handler.get_semantic_groups_needing_analysis.return_value = []
        yield
        self.patcher_wrapper.stop()

    @pytest.fixture
    def worker(self):
        return HierarchicalGroupingWorker(
            rabbitmq_url="amqp://guest:guest@localhost/",
            input_queue="test_input",
            llm_base_url="http://llm",
            llm_model_name="gpt-4",
            llm_api_key="key",
            embedding_model="text-embedding-3-large",
            max_neighbors=5,
            max_distance=0.15,
        )

    def test_worker_initialization(self, worker):
        self.mock_wrapper_class.assert_called_once()
        _, kwargs = self.mock_wrapper_class.call_args
        assert kwargs["max_distance"] == 0.15
        assert worker.name == "hierarchical_grouping_worker"

    @pytest.mark.asyncio
    async def test_handle_message_triggers_computation(self, worker):
        mock_msg = MagicMock(spec=BaseTriggerMessage)
        mock_msg.application_id = "app_999"
        mock_msg.job_id = "job-1"
        mock_msg.workflow_id = "wf-1"
        mock_msg.local_file = None

        result = await worker.handle_message(mock_msg)

        self.mock_wrapper_instance.compute_semantic_groups.assert_called_once_with(application_id="app_999")
        assert result is True

    @pytest.mark.asyncio
    async def test_handle_message_merges_and_emits_groups(self, worker):
        self.mock_wrapper_instance.compute_semantic_groups.return_value = [("group-1", "hash-1")]
        self.mock_wrapper_instance.db_handler.get_semantic_groups_needing_analysis.return_value = [
            ("group-1", "hash-1"),
            ("group-2", "hash-2"),
        ]
        mock_msg = MagicMock(spec=BaseTriggerMessage)
        mock_msg.application_id = "app_999"
        mock_msg.job_id = "job-1"
        mock_msg.workflow_id = "wf-1"
        mock_msg.local_file = None

        result = await worker.handle_message(mock_msg)

        assert result is True
        assert len(worker.output_messages) == 2
        assert isinstance(worker.output_messages[0], SessionGroupMessage)
        assert worker.output_messages[0].group_id == "group-1"
        assert worker.output_messages[0].sessions == []
        assert worker.output_messages[1].group_id == "group-2"
        assert worker.output_messages[1].sessions == []
