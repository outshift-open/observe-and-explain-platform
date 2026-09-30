#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker_base.queue_message import (
    BaseMessage,
    BaseQueueMessage,
    BaseTriggerMessage,
    FeedbackMessage,
)


class TestBaseMessage:
    def test_base_message_creation(self):
        """Test creating a BaseMessage with required fields."""
        msg = BaseMessage(job_id="job123", workflow_id="workflow456")
        assert msg.job_id == "job123"
        assert msg.workflow_id == "workflow456"
        assert msg.local_file is None

    def test_base_message_with_all_fields(self):
        """Test creating a BaseMessage with all fields."""
        msg = BaseMessage(
            job_id="job123",
            workflow_id="workflow456",
            local_file="/path/to/file",
        )
        assert msg.job_id == "job123"
        assert msg.workflow_id == "workflow456"
        assert msg.local_file == "/path/to/file"

    def test_base_message_with_none_values(self):
        """Test creating a BaseMessage with None values."""
        msg = BaseMessage()
        assert msg.job_id is None
        assert msg.workflow_id is None
        assert msg.local_file is None

    def test_base_message_model_dump(self):
        """Test dumping BaseMessage to dict."""
        msg = BaseMessage(job_id="job123", workflow_id="workflow456")
        dumped = msg.model_dump(by_alias=True)
        assert dumped["job_id"] == "job123"
        assert dumped["workflow_id"] == "workflow456"

    def test_base_message_dump_message(self):
        """Test dumping BaseMessage to JSON string."""
        msg = BaseMessage(job_id="job123", workflow_id="workflow456")
        json_str = msg.dump_message()
        parsed = json.loads(json_str)
        assert parsed["job_id"] == "job123"
        assert parsed["workflow_id"] == "workflow456"

    def test_base_message_from_body(self):
        """Test creating BaseMessage from JSON body."""
        json_body = json.dumps({"job_id": "job123", "workflow_id": "workflow456"})
        msg = BaseMessage.from_body(json_body.encode())
        assert msg.job_id == "job123"
        assert msg.workflow_id == "workflow456"

    @pytest.mark.asyncio
    async def test_base_message_write_message(self):
        """Test writing BaseMessage to RabbitMQ queue."""
        msg = BaseMessage(job_id="job123", workflow_id="workflow456")

        # Mock the channel and exchange
        mock_exchange = AsyncMock()
        mock_channel = MagicMock()
        mock_channel.default_exchange = mock_exchange

        await msg.write_message(mock_channel, "test_queue")

        # Verify the message was published
        mock_exchange.publish.assert_called_once()
        call_args = mock_exchange.publish.call_args
        published_message = call_args[0][0]

        # Verify message body
        body_dict = json.loads(published_message.body.decode())
        assert body_dict["job_id"] == "job123"
        assert body_dict["workflow_id"] == "workflow456"


class TestBaseQueueMessage:
    def test_base_queue_message_creation(self):
        """Test creating a BaseQueueMessage with session_id."""
        msg = BaseQueueMessage(
            session_id="session123",
            job_id="job456",
            workflow_id="workflow789",
        )
        assert msg.session_id == "session123"
        assert msg.job_id == "job456"
        assert msg.workflow_id == "workflow789"

    def test_base_queue_message_requires_session_id(self):
        """Test that BaseQueueMessage requires session_id."""
        with pytest.raises(ValueError):
            BaseQueueMessage(job_id="job456", workflow_id="workflow789")

    def test_base_queue_message_dump_message(self):
        """Test dumping BaseQueueMessage to JSON."""
        msg = BaseQueueMessage(
            session_id="session123",
            job_id="job456",
        )
        json_str = msg.dump_message()
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "session123"
        assert parsed["job_id"] == "job456"

    def test_base_queue_message_from_body(self):
        """Test creating BaseQueueMessage from JSON body."""
        json_body = json.dumps(
            {
                "session_id": "session123",
                "job_id": "job456",
                "workflow_id": "workflow789",
            }
        )
        msg = BaseQueueMessage.from_body(json_body.encode())
        assert msg.session_id == "session123"
        assert msg.job_id == "job456"


class TestBaseTriggerMessage:
    def test_base_trigger_message_creation(self):
        """Test creating a BaseTriggerMessage with application_id."""
        msg = BaseTriggerMessage(
            application_id="app123",
            job_id="job456",
            workflow_id="workflow789",
        )
        assert msg.application_id == "app123"
        assert msg.job_id == "job456"
        assert msg.workflow_id == "workflow789"

    def test_base_trigger_message_requires_application_id(self):
        """Test that BaseTriggerMessage requires application_id."""
        with pytest.raises(ValueError):
            BaseTriggerMessage(job_id="job456", workflow_id="workflow789")

    def test_base_trigger_message_from_body(self):
        """Test creating BaseTriggerMessage from JSON body."""
        json_body = json.dumps(
            {
                "application_id": "app123",
                "job_id": "job456",
                "workflow_id": "workflow789",
            }
        )
        msg = BaseTriggerMessage.from_body(json_body.encode())
        assert msg.application_id == "app123"


class TestFeedbackMessage:
    def test_feedback_message_creation(self):
        """Test creating a FeedbackMessage."""
        msg = FeedbackMessage(
            session_id="session123",
            input='{"test": "data"}',
            event="start",
            workflow="TestWorker",
            workflow_id="workflow456",
            queue_name="feedback_queue",
        )
        assert msg.session_id == "session123"
        assert msg.event == "start"
        assert msg.workflow == "TestWorker"

    def test_feedback_message_with_minimal_fields(self):
        """Test creating FeedbackMessage with only required field."""
        msg = FeedbackMessage(session_id="session123")
        assert msg.session_id == "session123"
        assert msg.input == ""
        assert msg.event == ""
        assert msg.workflow == ""
        assert msg.workflow_id == ""

    def test_feedback_message_dump_message(self):
        """Test dumping FeedbackMessage to JSON."""
        msg = FeedbackMessage(
            session_id="session123",
            event="start",
            workflow="TestWorker",
        )
        json_str = msg.dump_message()
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "session123"
        assert parsed["event"] == "start"
        assert parsed["workflow"] == "TestWorker"

    def test_feedback_message_from_body(self):
        """Test creating FeedbackMessage from JSON body."""
        body_dict = {
            "session_id": "session123",
            "event": "complete",
            "workflow": "TestWorker",
            "workflow_id": "workflow456",
            "queue_name": "feedback_queue",
        }
        msg = FeedbackMessage.from_body(json.dumps(body_dict))
        assert msg.session_id == "session123"
        assert msg.event == "complete"
        assert msg.workflow == "TestWorker"
        assert msg.workflow_id == "workflow456"
        assert msg.queue_name == "feedback_queue"

    def test_feedback_message_from_body_with_missing_fields(self):
        """Test creating FeedbackMessage from incomplete JSON body."""
        body_dict = {"session_id": "session123", "event": "error"}
        msg = FeedbackMessage.from_body(json.dumps(body_dict))
        assert msg.session_id == "session123"
        assert msg.event == "error"
        assert msg.workflow is None
        assert msg.workflow_id is None

    @pytest.mark.asyncio
    async def test_feedback_message_write_message(self):
        """Test writing FeedbackMessage to RabbitMQ queue."""
        msg = FeedbackMessage(
            session_id="session123",
            event="start",
            workflow="TestWorker",
        )

        # Mock the channel and exchange
        mock_exchange = AsyncMock()
        mock_channel = MagicMock()
        mock_channel.default_exchange = mock_exchange

        await msg.write_message(mock_channel, "feedback_queue")

        # Verify the message was published
        mock_exchange.publish.assert_called_once()
        call_args = mock_exchange.publish.call_args
        published_message = call_args[0][0]

        # Verify message body
        body_dict = json.loads(published_message.body.decode())
        assert body_dict["session_id"] == "session123"
        assert body_dict["event"] == "start"
        assert body_dict["workflow"] == "TestWorker"
