# Base Worker Framework

A reusable RabbitMQ-based worker framework for building message processing workers. Provides a foundation for implementing workers that process messages from queues, with support for multiple concurrent messages, feedback queues, and Argo Workflows integration.

## Overview

The Base Worker framework provides:
- **RabbitMQ Integration**: Async message queue handling with `aio_pika`
- **Message Models**: Pydantic-based message types for queue communication
- **Error Handling**: Comprehensive error handling and feedback mechanisms
- **Argo Support**: Process single messages without RabbitMQ (Argo Workflows mode)
- **Concurrent Processing**: Handle multiple messages in parallel with configurable limits

## Architecture

```
BaseWorker (abstract)
├── RabbitMQ message handling
├── Message parsing and validation
├── Feedback queue support
├── Output message propagation
└── Argo Workflows mode
```

## Installation

```bash
pip install worker-base
# or for development
pip install -e .
```

## Usage

### Creating a Custom Worker

```python
from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseQueueMessage

class MyCustomWorker(BaseWorker):
    def __init__(self, rabbitmq_url: str, input_queue: str, **kwargs):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            **kwargs
        )
        self.name = "MyCustomWorker"
        self.input_message_class = BaseQueueMessage

    async def handle_message(self, msg: BaseQueueMessage):
        # Implement your processing logic here
        session_id = msg.session_id
        
        # Process the message
        result = process_session(session_id)
        
        # Return True to propagate to output queues
        # Return None for errors
        # Return False for success without propagation
        return True if result else None
```

### Running the Worker

```python
import asyncio

async def main():
    worker = MyCustomWorker(
        rabbitmq_url="amqp://<user>:<password>@rabbitmq:5672/",
        input_queue="my_input_queue",
        output_queue=["output_queue_1", "output_queue_2"],
        feedback_queue="feedback_queue",
        message_limit=-1,  # -1 for unlimited
        max_inflight_messages=1,
    )
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Components

### BaseWorker

The abstract base class for all workers. Key methods:

- `async run()`: Start the worker (reads from RabbitMQ)
- `async run_argo_message(input_path, output_path)`: Process single Argo message
- `async handle_message(msg)`: Override to implement processing logic
- `async propagate_message()`: Send output to output queues

Key attributes:

- `self.name`: Worker name (for logging)
- `self.input_message_class`: Message type to deserialize
- `self.output_messages`: List to populate with output messages

### Message Types

#### BaseMessage

Base message class with:
- `job_id`: Optional job identifier
- `workflow_id`: Optional workflow identifier
- `local_file`: Optional file reference

#### BaseQueueMessage

Queue-based message extending BaseMessage:
- `session_id`: Required session identifier

#### BaseTriggerMessage

Trigger-based message:
- `application_id`: Required application identifier

#### FeedbackMessage

Status feedback messages (not a Pydantic model):
- `session_id`: Session identifier
- `event`: Event type (start, complete, error)
- `workflow`: Worker name
- `workflow_id`: Workflow identifier
- `queue_name`: Queue name

### Configuration

#### Constructor Parameters

```python
BaseWorker(
    rabbitmq_url: str,                    # RabbitMQ connection URL
    input_queue: str,                   # Input queue name
    output_queue: list[str] = [],       # Output queue names
    feedback_queue: str | None = None,  # Feedback queue (optional)
    message_limit: int = -1,            # Max messages to process (-1=unlimited)
    max_inflight_messages: int = 1,     # Concurrent messages to process
    db_type: str = "neo4j",             # DB type for optional KG_DAL
    db_uri: str | None = None,          # Database URI
    db_user: str | None = None,         # Database user
    db_password: str | None = None,     # Database password
    db_database: str | None = None,     # Database name
)
```

`rabbitmq_url` must resolve to a real connection string. At the application layer,
workers can now be configured with either:
- `RABBITMQ_URL`
- or split env vars: `RABBITMQ_HOST`/`RABBITMQ_PORT` plus required `RABBITMQ_USER` and `RABBITMQ_PASSWORD`, and optional `RABBITMQ_VHOST`

## Message Flow

```
RabbitMQ Queue
     ↓
 Parse Message
     ↓
Feedback: start event
     ↓
handle_message() ← IMPLEMENT THIS
     ↓
     ├─ Returns True
     │   ↓
     │ propagate_message()
     │   ↓
     │ Output Queue(s)
     │
     ├─ Returns False
     │   ↓
     │ No output
     │
     └─ Returns None (error)
         ↓
      Feedback: error event
```

## Error Handling

- Message parsing errors: Logged and skipped
- Processing errors: Caught, logged, feedback sent
- Worker lifecycle errors: Logged and raised

Feedback messages are sent for:
- `start`: When message processing begins
- `complete`: When processing completes successfully
- `error`: When an error occurs

## Concurrent Message Processing

Control concurrency with:

```python
# Process one message at a time
max_inflight_messages=1

# Process up to 5 messages in parallel
max_inflight_messages=5
```

RabbitMQ prefetch count is automatically set based on `max_inflight_messages`.

## Argo Workflows Integration

Process a single message file without RabbitMQ:

```python
worker = MyWorker(
    rabbitmq_url="dummy",  # Not used in Argo mode
    input_queue="argo",
)

# Process single message
await worker.run_argo_message(
    raw_input="input.json",
    output_path="output.json"
)
```

Input file (JSON):
```json
{
  "session_id": "session_123",
  "job_id": "job_456",
  "workflow_id": "wf_789"
}
```

Output file (JSON):
```json
{
  "session_id": "session_123",
  "workflow_id": "wf_789"
}
```

## Advanced Features

### Custom Message Types

Extend `BaseQueueMessage` with additional fields:

```python
from worker_base.queue_message import BaseQueueMessage
from pydantic import Field

class CustomMessage(BaseQueueMessage):
    priority: int = Field(alias="priority", default=0)
    tags: list[str] = Field(alias="tags", default=[])
```

### Database Integration

Optional knowledge graph database integration:

```python
worker = MyWorker(
    rabbitmq_url=...,
    input_queue=...,
    db_uri="neo4j://localhost:7687",
    db_user="neo4j",
    db_password="password",
    db_database="neo4j",
)

# Access with worker.db_handler
graph = worker.db_handler
```

### Feedback Queues

Enable processing feedback:

```python
worker = MyWorker(
    ...,
    feedback_queue="feedback_queue"
)

# Worker automatically sends feedback messages
```

## Examples

See the `norm-worker` project for a complete example of a worker built on `worker-base`.

## Dependencies

- **pydantic**: Data validation
- **aio_pika**: Async RabbitMQ client
- **pika**: RabbitMQ library
- **dal**: Data Access Layer (optional KG integration)

## Testing

```bash
pytest tests/
pytest tests/ -v
pytest tests/ --cov
```

## Contributing

When creating custom workers:
1. Extend `BaseWorker`
2. Override `handle_message()`
3. Set `self.name` and `self.input_message_class`
4. Return appropriate values (True/False/None)
5. Populate `self.output_messages` if needed

## License

Apache-2.0

See LICENSE file and copyright headers in source files.
