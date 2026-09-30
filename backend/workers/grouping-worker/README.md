#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Grouping Worker

Standalone worker that assigns a session to a semantic group by looking up the nearest-neighbour group in the knowledge graph.

## Usage

```bash
grouping-worker-cli --run-once --input /tmp/input-message.json --output /tmp/grouping-output-message.json
```

## Configuration

All settings can be provided via `.env` (copy `.env.template`) or environment variables.

Neo4j connection settings are resolved by the API layer (`oxp.dependencies`) from environment variables. The grouping worker does not expose Neo4j CLI flags.

| Env var | Default | Description |
|---|---|---|
| `RABBITMQ_URL` | unset | Full RabbitMQ connection URL. Alternative to split RabbitMQ settings below. |
| `RABBITMQ_HOST` | `localhost` | RabbitMQ host when not using `RABBITMQ_URL` |
| `RABBITMQ_PORT` | `5672` | RabbitMQ port when not using `RABBITMQ_URL` |
| `RABBITMQ_USER` | required in split mode | RabbitMQ username |
| `RABBITMQ_PASSWORD` | required in split mode | RabbitMQ password |
| `RABBITMQ_VHOST` | `/` | Optional RabbitMQ virtual host |
| `GROUPING_INPUT_QUEUE` | `new_session_to_grouping` | Input queue |
| `GROUPING_OUTPUT_QUEUE` | `new_session_to_analysis` | Output queue(s, comma-separated) |
| `NEO4J_HOST`/`NEO4J_URI`, `NEO4J_PORT`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | API defaults | Neo4j connection used by API DAL |
| `GROUPING_EMBEDDING_MODEL` | `azure/text-embedding-3-small` | Embedding model |
| `GROUPING_MAX_DISTANCE` | `0.3` | Max cosine distance for grouping |
| `GROUPING_MAX_NEIGHBORS` | `10` | Max neighbours to consider |

Set either `RABBITMQ_URL`, or `RABBITMQ_USER` and `RABBITMQ_PASSWORD` with optional `RABBITMQ_HOST`, `RABBITMQ_PORT`, and `RABBITMQ_VHOST`.

## Input message

`SessionDetailMessage` — requires at least `session_id`.

## Output message

`SessionGroupMessage` — contains `session_id`, `group_id`, `group_hash`.

## Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/grouping-worker

# Run the CLI (syncs dependencies automatically)
uv run --directory workers/grouping-worker grouping-worker-cli --test
```
