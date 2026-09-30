# Embedding Worker - Quick Start Guide

This document provides quick setup and usage instructions for the standalone Embedding Worker.

## Project Structure

```
embedding-worker/
├── src/embedding_worker/
│   ├── embedding_worker.py          # Core worker class
│   ├── embedding_worker_cli.py       # CLI entry point
│   ├── queues.py                    # Queue name constants
│   └── wrapper/
│       └── embedding_wrapper.py      # Embedder integration
├── tests/
│   ├── test_embedding_worker.py     # Unit tests
│   └── conftest.py                  # Pytest fixtures
├── pyproject.toml                    # Python package config
├── README.md                         # Full documentation
├── QUICKSTART.md                     # This file
└── input.json                        # Example run-once input message
```

## Installation

### Local Development

```bash
# Navigate to the embedding-worker directory
cd workers/embedding-worker

# Create a virtual environment (recommended)
python3.11 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"
```

## Usage

### 1. Run-once Mode (Argo Workflows Compatible, Single Message)

This is the mode specified in your requirement. Perfect for processing a single session in run-once mode (Argo-compatible).

```bash
# Basic usage
embedding-worker-cli \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/embedding-output-message.json \
  --embedder-type OpenAIEmbedder \
  --embedding-model azure/text-embedding-3-small

# With additional configuration
embedding-worker-cli \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/embedding-output-message.json \
  --embedder-type OpenAIEmbedder \
  --embedding-model azure/text-embedding-3-small \
  --db-uri bolt://localhost:7687 \
  --db-user neo4j \
  --db-password password \
  --db-database neo4j \
  --debug
```

**Input file format** (`input-message.json`):
```json
{
  "session_id": "session_123",
  "job_id": "job_456",
  "local_file": null
}
```

**Output**: Processed message written to `/tmp/embedding-output-message.json`

### 2. Queue-Based Mode (Production)

This mode listens to RabbitMQ queues for continuous processing.

```bash
# Start the worker
embedding-worker-cli \
  --rabbitmq-url amqp://guest:guest@localhost:5672/ \
  --input-queue new_session_to_embedding \
  --output-queue new_session_to_grouping \
  --embedder-type OpenAIEmbedder \
  --embedding-model azure/text-embedding-3-small
```

## Configuration

### Environment Variables

```bash
# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
EMBEDDING_INPUT_QUEUE=new_session_to_embedding
EMBEDDING_OUTPUT_QUEUE=new_session_to_grouping
EMBEDDING_FEEDBACK_QUEUE=feedback_queue  # optional

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j

# Embedding Configuration
EMBEDDING_EMBEDDER_TYPE=SentenceTransformerEmbedder  # or OpenAIEmbedder
EMBEDDING_MODEL=all-MiniLM-L6-v2  # or azure/text-embedding-3-small

# API Keys (if using OpenAIEmbedder)
OPENAI_API_KEY=your-api-key
```

### CLI Options

All environment variables can be overridden via CLI flags:

```bash
# Common flags
--rabbitmq-url              RabbitMQ connection URL
--input-queue             Input queue name
--output-queue            Output queue(s) (can be multiple)
--max-sessions            Max sessions to process (-1 for unlimited)
--debug                   Enable debug logging and CSV dumps
--test                    Test mode (prints "I'm Alive" and exits)

# Database configuration
--db-uri                  Neo4j URI
--db-user                 Neo4j username
--db-password             Neo4j password
--db-database             Neo4j database name

# Embedding options
--embedder-type           Embedder to use
--embedding-model         Model identifier

# Run-once mode
--run-once                Run in single-message mode (process once and exit)
--input                   Input file path (for --run-once)
--output                  Output file path (for --run-once)
```

## Embedders

### SentenceTransformerEmbedder (Default)

Lightweight, runs locally. No API keys required.

```bash
--embedder-type SentenceTransformerEmbedder \
--embedding-model all-MiniLM-L6-v2
```

### OpenAIEmbedder

Requires OpenAI API key. Higher quality embeddings.

```bash
--embedder-type OpenAIEmbedder \
--embedding-model azure/text-embedding-3-small
```

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/embedding_worker

# Run specific test
pytest tests/test_embedding_worker.py::test_embedding_worker_init
```

## Development

### Code Style

```bash
# Format code
black src/ tests/

# Run linter
ruff check src/ tests/

# Type checking
mypy src/
```

### Debug Mode

Enable debug output and CSV dumps:

```bash
embedding-worker-cli \
  --run-once \
  --input /tmp/input.json \
  --output /tmp/output.json \
  --debug

# This will create: /tmp/embedding_embeddings_<session_id>.csv
```

## Troubleshooting

### Connection Issues

**RabbitMQ Connection Failed**
```bash
# Verify URL format: amqp://user:pass@host:port/
```

**Neo4j Connection Failed**
```bash
# Check Neo4j is running and credentials

# Verify connection: 
cypher-shell -u neo4j -p password -a bolt://localhost:7687
```

### Embedding Issues

**No content found to embed**
- Verify the session has state transitions in the graph

**Out of memory with large sessions**
- Process fewer sessions with `--max-sessions`
- Use smaller model with SentenceTransformerEmbedder

## Examples

### Example 1: Process single session with default embedder

```bash
embedding-worker-cli \
  --run-once \
  --input input.json \
  --output output.json
```

### Example 2: Process with OpenAI embeddings

```bash
embedding-worker-cli \
  --run-once \
  --input input.json \
  --output output.json \
  --embedder-type OpenAIEmbedder \
  --embedding-model azure/text-embedding-3-small
```

### Example 3: Continuous processing from queue

```bash
embedding-worker-cli \
  --rabbitmq-url amqp://guest:guest@rabbitmq:5672/ \
  --input-queue new_session_to_embedding \
  --output-queue new_session_to_grouping \
  --max-sessions -1  # unlimited
```

### Example 4: Health check

```bash
embedding-worker-cli --test
# Output: I'm Alive
```

## Next Steps

- Review [README.md](README.md) for detailed architecture
- Check [pyproject.toml](pyproject.toml) for dependencies
- Run tests: `pytest tests/`
