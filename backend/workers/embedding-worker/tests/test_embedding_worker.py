#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from worker_base.queue_message import BaseQueueMessage

from embedding_worker.worker import EmbeddingWorker


class MockEmbeddingWrapper:
    def __init__(self, *args, **kwargs):
        pass


def test_embedding_worker_init(mocker):
    mock_embedder = mocker.Mock()
    # Needed to avoid the wrapper to connect to Neo4j

    mocker.patch(
        "embedding_worker.wrapper.embedding_wrapper.EmbeddingWrapper",
        return_value=mock_embedder,
    )
    worker = EmbeddingWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        output_queue=[],
    )
    assert worker.rabbitmq_url == "amqp://guest:guest@localhost/"
    assert worker.embedder is not None


# Testing the input message processing
def test_embedding_worker_run_worker(mocker):
    mock_embedder = mocker.Mock()
    # Needed to avoid the wrapper to connect to Neo4j
    mocker.patch(
        "embedding_worker.wrapper.embedding_wrapper.EmbeddingWrapper",
        return_value=mock_embedder,
    )

    worker = EmbeddingWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        output_queue=[],
    )

    # Mock aio_pika.connect_robust and channel/queue
    class MockAsyncIterator:
        def __aiter__(self):
            async def gen():
                yield mock_message

            return gen()

    # Mock async context manager for queue.iterator()
    class MockAsyncContextManager:
        async def __aenter__(self):
            return MockAsyncIterator()

        async def __aexit__(self, exc_type, exc, tb):
            pass

    class MockMessageProcessor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_connection = mocker.AsyncMock()
    mock_channel = mocker.AsyncMock()
    mock_message = mocker.Mock()
    message_body = BaseQueueMessage(session_id="sess1", job_id="job1")
    mock_message.body = message_body.dump_message()

    mock_message.process.return_value = MockMessageProcessor()

    mock_queue = mocker.Mock()
    mock_queue.iterator.return_value = MockAsyncContextManager()

    mock_channel.declare_queue.return_value = mock_queue
    mock_connection.channel.return_value = mock_channel
    mocker.patch("aio_pika.connect_robust", return_value=mock_connection)

    # Mock embedder.process_session
    worker.embedder.process_session = mocker.Mock()
    # Run
    import asyncio

    asyncio.run(worker.run_worker())
    worker.embedder.process_session.assert_called_with("sess1")
