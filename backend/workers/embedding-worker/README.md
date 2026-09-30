# Embedding Worker

A standalone worker for processing telemetry sessions with vector embeddings. This worker is a focused, minimal version of the full workflows system, containing only the embedding processing component.

Built on the reusable [worker-base](../worker-base/README.md) framework.

## Overview

The Embedding Worker:
- Listens to a RabbitMQ queue for normalized session processing requests
- Generates vector embeddings for telemetry traces using configurable embedders (OpenAI, etc.)
- Stores embeddings in the knowledge graph
- Forwards processed sessions to downstream queues (MCE)

## Architecture

```
RabbitMQ Input Queue
         ↓
    EmbeddingWorker (extends worker-base.BaseWorker)
         ↓
    EmbeddingWrapper (embedder integration)
         ↓
    KG Embedding Storage
         ↓
RabbitMQ Output Queues
(MCE, etc.)
```

### Component Separation

- **worker-base**: Reusable RabbitMQ worker framework
  - `BaseWorker`: Core worker lifecycle and message handling
  - `BaseQueueMessage`: Standard queue message format
  - `FeedbackMessage`: Worker feedback/status reporting

- **embedding-worker**: Embedding-specific implementation
  - `EmbeddingWorker`: Extends BaseWorker for embedding processing
  - `EmbeddingWrapper`: Embedder library integration
  - `EmbeddingWorkerCLI`: Command-line interface

## Dependencies

The worker has minimal dependencies:
- **worker-base**: Base worker framework for RabbitMQ message processing
- **ontology-hub**: Knowledge graph integration
- **openai**: OpenAI API client for embeddings (can be extended for other providers)

## Running the Worker

### Via CLI

```bash
# Standard mode (queue-based)
embedding-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_embedding \
  --output-queue new_session_to_grouping \
  --embedder-type OpenAIEmbedder \
  --embedding-model azure/text-embedding-3-small

# Run-once mode (Argo Workflows compatible, single message)
embedding-worker-cli \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/embedding-output-message.json \
  --embedder-type OpenAIEmbedder \
  --embedding-model azure/text-embedding-3-small
```

## Configuration

Set environment variables for default values:

```bash
# Either a full RabbitMQ URL...
RABBITMQ_URL=amqp://<user>:<password>@rabbitmq:5672/

# ...or split settings
# RABBITMQ_HOST=localhost
# RABBITMQ_PORT=5672
# RABBITMQ_USER=<user>
# RABBITMQ_PASSWORD=<password>
# RABBITMQ_VHOST=/
EMBEDDING_INPUT_QUEUE=new_session_to_embedding
EMBEDDING_OUTPUT_QUEUE=new_session_to_grouping
EMBEDDING_EMBEDDER_TYPE=OpenAIEmbedder
EMBEDDING_MODEL=azure/text-embedding-3-small
OPENAI_API_KEY=your-api-key
```

## Testing

```bash
pytest tests/
```

## Development

Install in development mode:

```bash
pip install -e ".[dev]"
```

Format and lint:

```bash
black src/ tests/
ruff check src/ tests/
```

## Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/embedding-worker

# Run the CLI (syncs dependencies automatically)
uv run --directory workers/embedding-worker embedding-worker-cli --test
```
