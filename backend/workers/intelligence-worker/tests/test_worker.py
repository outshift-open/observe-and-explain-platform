#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from worker_base.queue_message import BaseTriggerMessage

from intelligence_worker.worker import IntelligenceWorker


class TestIntelligenceWorker:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        self.patcher_wrapper = patch("intelligence_worker.worker.IntelligenceWrapper")
        self.patcher_db = patch("worker_base.base_worker.get_neo4j_connector")
        self.mock_wrapper_class = self.patcher_wrapper.start()
        self.mock_db_class = self.patcher_db.start()
        self.mock_wrapper_instance = self.mock_wrapper_class.return_value
        self.mock_wrapper_instance.generate_insights = AsyncMock(return_value=[])
        yield
        self.patcher_wrapper.stop()
        self.patcher_db.stop()

    @pytest.fixture
    def worker(self):
        return IntelligenceWorker(
            rabbitmq_url="amqp://guest:guest@localhost/",
            input_queue="test_input",
            catalog_root=".",
        )

    def test_worker_initialization(self, worker):
        self.mock_wrapper_class.assert_called_once()
        _, kwargs = self.mock_wrapper_class.call_args
        assert kwargs["catalog_root"] == "."
        assert kwargs["db_handler"] is worker.db_handler
        assert worker.name == "IntelligenceWorker"

    @pytest.mark.asyncio
    async def test_handle_message_generates_insights(self, worker):
        mock_msg = MagicMock(spec=BaseTriggerMessage)
        mock_msg.application_id = "app_123"

        result = await worker.handle_message(mock_msg)

        self.mock_wrapper_instance.generate_insights.assert_called_once_with(
            application_id="app_123",
            max_concurrency=8,
        )
        assert result is True
