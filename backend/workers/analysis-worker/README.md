# analysis-worker

Standalone worker that runs anomaly detection, consistency analysis, and normal behaviour analysis concurrently for each semantic session group.

## Overview

The `analysis-worker` is a combined worker that replaces running three separate workers (anomaly-detection-worker, consistency-worker, normal-behaviour-worker) by executing all three analyses in parallel within a single process.

## Usage

### RabbitMQ mode

```bash
analysis-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_analysis \
  --embedding-model azure/text-embedding-3-small \
  --max-inflight-messages 4
```

### Run-once mode (Argo Workflows compatible)

```bash
analysis-worker-cli \
  --embedding-model azure/text-embedding-3-small \
  --max-inflight-messages 4 \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/output.json
```

### Input message format (run-once mode)

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "group_hash": "abc123",
  "sessions": [
    {
      "session_id": "session-abc",
      "metrics": {"Cost": 1.0},
      "input_content": "...",
      "input_embedding": [...],
      "output_content": "...",
      "output_embedding": [...],
      "execution_graph": {}
    }
  ]
}
```

When `sessions` is empty the worker fetches group data from Neo4j using `group_id`, `group_hash`, and `embedding_model`.

## Configuration

Copy `.env.template` to `.env` and fill in your values. All options can also be passed via CLI flags.

Neo4j connection settings are resolved by the API layer (`oxp.dependencies`) from environment variables. The analysis worker does not expose Neo4j CLI flags.

| Environment variable | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full RabbitMQ connection URL. Alternative to split RabbitMQ settings below. |
| `RABBITMQ_HOST` | _(env only)_ | RabbitMQ host when not using `RABBITMQ_URL` |
| `RABBITMQ_PORT` | _(env only)_ | RabbitMQ port when not using `RABBITMQ_URL` |
| `RABBITMQ_USER` | _(env only)_ | RabbitMQ username required in split mode |
| `RABBITMQ_PASSWORD` | _(env only)_ | RabbitMQ password required in split mode |
| `RABBITMQ_VHOST` | _(env only)_ | Optional RabbitMQ virtual host |
| `ANALYSIS_INPUT_QUEUE` | `--input-queue` | Input queue name |
| `EMBEDDING_MODEL` | `--embedding-model` | Embedding model identifier |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | Max inflight messages per process (`-1` auto: `max(1, cpu_count//3)`) |
| `NEO4J_HOST`/`NEO4J_URI`, `NEO4J_PORT`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | _(API-managed)_ | Neo4j connection used by API DAL |
| `ANOMALY_CONFIG_FILE` | `--anomaly-config-file` | YAML layers config for anomaly detection |
| `CONSISTENCY_CONFIG_FILE` | `--consistency-config-file` | YAML layers config for consistency |
| `NORMAL_BEHAVIOUR_CONFIG_FILE` | `--normal-behaviour-config-file` | YAML layers config for normal behaviour |

Set either `RABBITMQ_URL`, or `RABBITMQ_USER` and `RABBITMQ_PASSWORD` with optional `RABBITMQ_HOST`, `RABBITMQ_PORT`, and `RABBITMQ_VHOST`.

## Parameters

- `--max-inflight-messages` (`--max_inflight_messages`): Single concurrency knob for server mode. Sets inflight messages per process.
- Process pool size is derived as `max_inflight_messages * 3` to preserve 3-track analysis parallelism.
- The three analysis tracks (anomaly, consistency, normal behaviour) always run in parallel per message.

## Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/analysis-worker

# Run the CLI (syncs dependencies automatically)
uv run --directory workers/analysis-worker analysis-worker-cli --test
```
