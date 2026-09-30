# Embedding Worker

Standalone embedding worker for processing telemetry sessions with vector embeddings.

**Source:** [`workers/embedding-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/embedding-worker)

## Overview

The embedding worker computes, for each `State` in a session's trajectory, an embedded vector of
its textual content, and writes the resulting embeddings back to the knowledge graph. These
embeddings are what [grouping-worker](grouping-worker.md) later uses to assign the session to a
semantic group.

It sits right after [norm-worker](norm-worker.md) in the ingestion pipeline (see the
[architecture overview](../architecture/overview.md) and [pipelines](../architecture/pipelines.md)
docs), running in parallel with [mce-worker](mce-worker.md):

- **Input queue**: `new_session_to_embedding`
- **Output queue**: `new_session_to_grouping`
- **CLI**: `embedding-worker-cli`

Internally, `EmbeddingWorker` (`workers/embedding-worker/src/embedding_worker/worker.py`)
subclasses the shared [`worker-base`](../components/worker-base.md) `BaseWorker`. On each message
it fetches the session's state content from the knowledge graph (via `oxp.client.dal`), delegates
to `EmbeddingWrapper.process_session()`
(`workers/embedding-worker/src/embedding_worker/wrapper/embedding_wrapper.py`), and ingests the
resulting vectors back through the same DAL. `EmbeddingWrapper` is a thin adapter around the
[`dem.embedding`](../components/analysis.md) submodule's `SentenceTransformerEmbedder` /
`OpenAIEmbedder` classes: it builds the selected embedder, encodes each state's content (falling
back to a placeholder string `OXP_EMPTY_STATE` for empty content), and attaches the model name and
vector to each record before ingestion.

## Usage

```bash
# Queue-based mode (long-running worker)
embedding-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_embedding \
  --output-queue new_session_to_grouping

# Run-once mode (Argo Workflows compatible)
embedding-worker-cli \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/embedding-output-message.json

# Test liveness
embedding-worker-cli --test
```

### Configuration

Copy `workers/embedding-worker/.env.example` to `.env` and fill in the values, or pass everything
via CLI flags / environment variables:

| Env var | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full RabbitMQ connection URL |
| `EMBEDDING_INPUT_QUEUE` | `--input-queue` | Input queue name (default `new_session_to_embedding`) |
| `EMBEDDING_OUTPUT_QUEUE` | `--output-queue` | Output queue(s), comma-separated (default `new_session_to_grouping`) |
| `EMBEDDING_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `EMBEDDING_EMBEDDER_TYPE` | `--embedder-type` | `SentenceTransformerEmbedder` (default) or `OpenAIEmbedder` |
| `EMBEDDING_MODEL` | `--embedding-model` | Model identifier (default `all-MiniLM-L6-v2`; e.g. `azure/text-embedding-3-small` for `OpenAIEmbedder`) |
| `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | — | Neo4j connection, used by the KG DAL |
| `AI_GATEWAY_API_KEY` / `AI_GATEWAY_BASE_URL` | — | Required when using `OpenAIEmbedder` |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | Sessions processed concurrently per worker process (default 16; each in-flight session issues one batched embedding-API call) |

Also supported: the common worker flags `--max-sessions`, `--debug` (also dumps embeddings to
`/tmp/embedding_embeddings_<session_id>.csv`), `--run-once`, `--input`, `--output`, `--test`,
shared by all [workers](index.md).

### Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/embedding-worker

# Sync dependencies and run the CLI directly
uv run --directory workers/embedding-worker embedding-worker-cli --test
```

### Development

```bash
uv run --package embedding-worker --extra dev pytest workers/embedding-worker/tests/ -v
```
