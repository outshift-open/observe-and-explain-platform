#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Consistency Worker

Standalone worker that computes consistency scores (text, graph, metric) for a semantic group.

## Usage

```bash
consistency-worker-cli --run-once \
  --config_file /tmp/consistency-config.yaml \
  --input /tmp/input-message.json \
  --output /tmp/consistency-output-message.json
```

The input message is the output of the `grouping-worker` (`GroupingOutputMessage`) which includes inline sessions, so no Neo4j access is needed in run-once mode.

## Configuration

All settings can be provided via `.env` (copy `.env.template`) or environment variables.

| Env var | Default | Description |
|---|---|---|
| `RABBITMQ_URL` | unset | Full RabbitMQ connection URL. Alternative to split RabbitMQ settings below. |
| `RABBITMQ_HOST` | `localhost` | RabbitMQ host when not using `RABBITMQ_URL` |
| `RABBITMQ_PORT` | `5672` | RabbitMQ port when not using `RABBITMQ_URL` |
| `RABBITMQ_USER` | required in split mode | RabbitMQ username |
| `RABBITMQ_PASSWORD` | required in split mode | RabbitMQ password |
| `RABBITMQ_VHOST` | `/` | Optional RabbitMQ virtual host |
| `CONSISTENCY_INPUT_QUEUE` | `new_session_to_consistency` | Input queue |
| `NEO4J_URI` / `NEO4J_HOST` | `bolt://localhost:7687` | Neo4j URI |
| `NEO4J_USERNAME` | | Neo4j user |
| `NEO4J_PASSWORD` | | Neo4j password |
| `NEO4J_DB` | `neo4j` | Neo4j database |
| `EMBEDDING_MODEL` | | Embedding model name |
| `CONSISTENCY_CONFIG_FILE` | | Path to YAML layers config |

Set either `RABBITMQ_URL`, or `RABBITMQ_USER` and `RABBITMQ_PASSWORD` with optional `RABBITMQ_HOST`, `RABBITMQ_PORT`, and `RABBITMQ_VHOST`.

## Input message

`ConsistencyInputMessage` — extends `BaseQueueMessage` with `group_id`, `group_hash`, and `sessions[]`.
When `sessions` is non-empty the worker uses them directly (run-once mode), skipping Neo4j.

## Output message

`ConsistencyOutputMessage` — contains `session_id`, `group_id`, `sessions[]`, `consistency[]`.

## Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/consistency-worker

# Run the CLI (syncs dependencies automatically)
uv run --directory workers/consistency-worker consistency-worker-cli --test
```
