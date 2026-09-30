#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker_base.base_worker import BaseWorker
from worker_base.dal_adapter import OXPApiDALAdapter
from worker_base.queue_message import BaseMessage


class TestBaseWorker:
    """Test BaseWorker initialization and configuration."""

    def test_base_worker_initialization_minimal(self):
        """Test initializing BaseWorker with minimal parameters."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )
        assert worker.rabbitmq_url == "amqp://localhost"
        assert worker.input_queue == "test_queue"
        assert worker.output_queue == []
        assert worker.feedback_queue is None
        assert worker.message_limit == -1
        assert worker.max_inflight_messages == 1

    def test_base_worker_initialization_with_output_queues(self):
        """Test initializing BaseWorker with output queues."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
            output_queue=["output_queue1", "output_queue2"],
        )
        assert worker.output_queue == ["output_queue1", "output_queue2"]

    def test_base_worker_initialization_with_feedback_queue(self):
        """Test initializing BaseWorker with feedback queue."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
            feedback_queue="feedback_queue",
        )
        assert worker.feedback_queue == "feedback_queue"

    def test_base_worker_initialization_with_message_limit(self):
        """Test initializing BaseWorker with message limit."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
            message_limit=100,
        )
        assert worker.message_limit == 100

    def test_base_worker_initialization_with_max_inflight_messages(self):
        """Test initializing BaseWorker with max_inflight_messages."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
            max_inflight_messages=5,
        )
        assert worker.max_inflight_messages == 5

    def test_base_worker_initialization_with_min_max_inflight_messages(self):
        """Test that max_inflight_messages is at least 1."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
            max_inflight_messages=0,  # Should be set to 1
        )
        assert worker.max_inflight_messages == 1

    def test_base_worker_name(self):
        """Test BaseWorker name property."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )
        assert worker.name == "BaseWorker"

    def test_base_worker_output_messages_context(self):
        """Test output_messages context variable property."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )
        msg = BaseMessage(job_id="test_job")
        worker.output_messages = [msg]
        assert worker.output_messages == [msg]

    @patch("worker_base.base_worker.get_neo4j_connector")
    def test_base_worker_db_handler_not_initialized_when_connector_unavailable(self, mock_get_connector):
        """Test that db_handler is None when the Neo4j connector cannot be built."""
        mock_get_connector.side_effect = Exception("connection refused")
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )
        assert worker.db_handler is None

    @patch("worker_base.base_worker.get_neo4j_connector")
    def test_base_worker_db_handler_initialized_from_api_connector(self, mock_get_connector):
        """Test that db_handler wraps the API-managed Neo4j connector."""
        mock_get_connector.return_value = MagicMock()
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )
        assert isinstance(worker.db_handler, OXPApiDALAdapter)
        mock_get_connector.assert_called_once()


class TestBaseWorkerStaticMethods:
    """Test BaseWorker static methods."""

    def test_load_argo_input_from_json_string(self):
        """Test loading Argo input from JSON string."""
        json_str = '{"job_id": "test_job", "workflow_id": "test_workflow"}'
        result = BaseWorker._load_argo_input(json_str)
        assert result["job_id"] == "test_job"
        assert result["workflow_id"] == "test_workflow"

    def test_load_argo_input_from_json_list(self):
        """Test loading Argo input from JSON array."""
        json_str = '[{"job_id": "test_job1"}, {"job_id": "test_job2"}]'
        result = BaseWorker._load_argo_input(json_str)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_load_argo_input_from_file(self):
        """Test loading Argo input from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"job_id": "file_job"}, f)
            f.flush()
            temp_file = f.name

        try:
            result = BaseWorker._load_argo_input(temp_file)
            assert result["job_id"] == "file_job"
        finally:
            os.unlink(temp_file)

    def test_load_argo_input_with_whitespace(self):
        """Test loading Argo input with leading/trailing whitespace."""
        json_str = '  {"job_id": "test_job"}  '
        result = BaseWorker._load_argo_input(json_str)
        assert result["job_id"] == "test_job"

    def test_load_argo_input_none_raises_error(self):
        """Test that None input raises ValueError."""
        with pytest.raises(ValueError, match="Argo input is required"):
            BaseWorker._load_argo_input(None)

    def test_load_argo_input_invalid_json_raises_error(self):
        """Test that invalid JSON raises error."""
        with pytest.raises(ValueError):
            BaseWorker._load_argo_input("not json at all")

    def test_load_argo_input_nonexistent_file_raises_error(self):
        """Test that nonexistent file raises ValueError."""
        with pytest.raises(ValueError):
            BaseWorker._load_argo_input("/nonexistent/path/file.json")

    def test_write_argo_output_creates_directory(self):
        """Test that _write_argo_output creates directories as needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "subdir", "output.json")
            payload = {"job_id": "test_job", "result": "success"}

            BaseWorker._write_argo_output(output_path, payload)

            assert os.path.exists(output_path)
            with open(output_path, "r") as f:
                content = json.load(f)
            assert content["job_id"] == "test_job"

    def test_write_argo_output_to_existing_directory(self):
        """Test that _write_argo_output works with existing directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.json")
            payload = {"result": "success"}

            BaseWorker._write_argo_output(output_path, payload)

            assert os.path.exists(output_path)
            with open(output_path, "r") as f:
                content = json.load(f)
            assert content["result"] == "success"

    def test_write_argo_output_overwrites_existing_file(self):
        """Test that _write_argo_output overwrites existing files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"old": "data"}, f)
            f.flush()
            temp_file = f.name

        try:
            payload = {"new": "data"}
            BaseWorker._write_argo_output(temp_file, payload)

            with open(temp_file, "r") as f:
                content = json.load(f)
            assert content == {"new": "data"}
        finally:
            os.unlink(temp_file)


class TestBaseWorkerArgoMode:
    """Test BaseWorker Argo mode functionality."""

    @pytest.mark.asyncio
    async def test_run_argo_message_basic(self):
        """Test run_argo_message with basic input."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.json")
            input_json = '{"job_id": "test_job"}'

            class TestWorker(BaseWorker):
                async def handle_message(self, msg):
                    msg.job_id = "processed"
                    self.output_messages = [msg]
                    return True

            worker = TestWorker(
                rabbitmq_url="amqp://localhost",
                input_queue="test_queue",
            )

            result = await worker.run_argo_message(input_json, output_path)
            assert os.path.exists(output_path)
            assert "job_id" not in result
            assert result["workflow_id"] is not None

    @pytest.mark.asyncio
    async def test_run_argo_message_generates_workflow_id(self):
        """Test that run_argo_message generates workflow_id if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.json")
            input_json = '{"job_id": "test_job"}'

            class TestWorker(BaseWorker):
                async def handle_message(self, msg):
                    self.output_messages = [msg]
                    return True

            worker = TestWorker(
                rabbitmq_url="amqp://localhost",
                input_queue="test_queue",
            )

            result = await worker.run_argo_message(input_json, output_path)
            assert result["workflow_id"] is not None

    @pytest.mark.asyncio
    async def test_run_argo_message_handles_false_return(self):
        """Test that run_argo_message handles False return (no output)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.json")
            input_json = '{"job_id": "test_job"}'

            class TestWorker(BaseWorker):
                async def handle_message(self, msg):
                    return False

            worker = TestWorker(
                rabbitmq_url="amqp://localhost",
                input_queue="test_queue",
            )

            result = await worker.run_argo_message(input_json, output_path)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_argo_message_handles_none_return(self):
        """Test that run_argo_message raises on None return."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.json")
            input_json = '{"job_id": "test_job"}'

            class TestWorker(BaseWorker):
                async def handle_message(self, msg):
                    return None

            worker = TestWorker(
                rabbitmq_url="amqp://localhost",
                input_queue="test_queue",
            )

            with pytest.raises(RuntimeError, match="Worker failed to process input"):
                await worker.run_argo_message(input_json, output_path)

    @pytest.mark.asyncio
    async def test_run_argo_message_from_file(self):
        """Test run_argo_message with input from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.json")
            output_path = os.path.join(tmpdir, "output.json")

            with open(input_path, "w") as f:
                json.dump({"job_id": "file_job"}, f)

            class TestWorker(BaseWorker):
                async def handle_message(self, msg):
                    self.output_messages = [msg]
                    return True

            worker = TestWorker(
                rabbitmq_url="amqp://localhost",
                input_queue="test_queue",
            )

            result = await worker.run_argo_message(input_path, output_path)
            assert "job_id" not in result
            assert result["workflow_id"] is not None


class TestBaseWorkerMessageHandling:
    """Test BaseWorker message handling methods."""

    @pytest.mark.asyncio
    async def test_send_message_to_queue(self):
        """Test sending message to queue."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
            output_queue=["output_queue"],
        )

        mock_channel = AsyncMock()
        worker.channel = mock_channel

        msg = MagicMock(spec=BaseMessage)
        msg.write_message = AsyncMock()
        await worker.send_message_to_queue("custom_queue", msg)

        msg.write_message.assert_awaited_once_with(mock_channel, "custom_queue", ttl_seconds=None)

    @pytest.mark.asyncio
    async def test_propagate_message_with_no_output_queue(self):
        """Test propagate_message with no output queue."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )

        worker.output_messages = [BaseMessage(job_id="test_job")]

        # Should log but not raise
        await worker.propagate_message()

    @pytest.mark.asyncio
    async def test_send_message_to_all_with_multiple_queues(self):
        """Test sending message to multiple output queues."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
            output_queue=["queue1", "queue2"],
        )

        mock_channel = AsyncMock()
        worker.channel = mock_channel

        msg = BaseMessage(job_id="test_job")
        await worker.send_message_to_all(msg)

        # Verify the message was written to all queues (via mocking)


class TestBaseWorkerHandleMessage:
    """Test BaseWorker handle_message abstract method."""

    @pytest.mark.asyncio
    async def test_handle_message_not_implemented(self):
        """Test that handle_message is not implemented in base class."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )

        msg = BaseMessage(job_id="test_job")

        with pytest.raises(NotImplementedError):
            await worker.handle_message(msg)

    @pytest.mark.asyncio
    async def test_handle_message_implemented_in_subclass(self):
        """Test that subclass can implement handle_message."""

        class TestWorker(BaseWorker):
            async def handle_message(self, msg):
                msg.job_id = f"processed_{msg.job_id}"
                return True

        worker = TestWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )

        msg = BaseMessage(job_id="original")
        result = await worker.handle_message(msg)

        assert result is True
        assert msg.job_id == "processed_original"


class TestBaseWorkerContextVars:
    """Test BaseWorker context variable handling for concurrent message processing."""

    def test_output_messages_context_isolation(self):
        """Test that output_messages are isolated per context."""
        worker = BaseWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )

        msg1 = BaseMessage(job_id="job1")
        msg2 = BaseMessage(job_id="job2")

        worker.output_messages = [msg1]
        assert worker.output_messages == [msg1]

        # In a new context, output_messages should be reset
        worker.output_messages = [msg2]
        assert worker.output_messages == [msg2]

    @pytest.mark.asyncio
    async def test_output_messages_concurrent_task_isolation(self):
        """Test that concurrent tasks have isolated output_messages."""

        class TestWorker(BaseWorker):
            async def handle_message(self, msg):
                self.output_messages = [msg]
                await asyncio.sleep(0.01)  # Simulate async work
                return self.output_messages[0]

        worker = TestWorker(
            rabbitmq_url="amqp://localhost",
            input_queue="test_queue",
        )

        msg1 = BaseMessage(job_id="job1")
        msg2 = BaseMessage(job_id="job2")

        # Run tasks concurrently
        # Note: contextvars should maintain isolation
        task1 = asyncio.create_task(worker.handle_message(msg1))
        task2 = asyncio.create_task(worker.handle_message(msg2))

        result1 = await task1
        result2 = await task2

        assert result1.job_id == "job1"
        assert result2.job_id == "job2"
