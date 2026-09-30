# Hierarchical Grouping Worker

A standalone worker for periodic hierarchical grouping over session embeddings. It listens for trigger messages, computes or updates semantic groups, and emits group IDs for downstream analysis.

Built on the reusable [worker-base](../worker-base/README.md) framework.

## Quick Start

```bash
cp .env.template .env
# edit .env with your Neo4j and LLM settings
hierarchical-grouping-worker-cli
```

## Usage

### RabbitMQ mode

```bash
hierarchical-grouping-worker-cli \
	--input-queue new_session_to_periodic_grouping \
	--output-queue new_session_to_analysis \
	--embedding-model azure/text-embedding-3-small
```

## Configuration

All options can be set via CLI flags or environment variables. See `.env.template` for common variables.

Neo4j connection settings are resolved by the API layer (`oxp.dependencies`) from environment variables. The hierarchical-grouping worker does not expose Neo4j CLI flags.

| Env var | Default | Description |
|---|---|---|
| `RABBITMQ_URL` | unset | Full RabbitMQ connection URL. Alternative to split RabbitMQ settings below. |
| `RABBITMQ_HOST` | `localhost` | RabbitMQ host when not using `RABBITMQ_URL` |
| `RABBITMQ_PORT` | `5672` | RabbitMQ port when not using `RABBITMQ_URL` |
| `RABBITMQ_USER` | required in split mode | RabbitMQ username |
| `RABBITMQ_PASSWORD` | required in split mode | RabbitMQ password |
| `RABBITMQ_VHOST` | `/` | Optional RabbitMQ virtual host |
| `HIERARCHICAL_GROUPING_INPUT_QUEUE` | `new_session_to_periodic_grouping` | Input trigger queue |
| `HIERARCHICAL_GROUPING_OUTPUT_QUEUE` | `new_session_to_analysis` | Output queue(s, comma-separated) |
| `NEO4J_HOST`/`NEO4J_URI`, `NEO4J_PORT`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | API defaults | Neo4j connection used by API DAL |
| `HIERARCHICAL_GROUPING_EMBEDDING_MODEL` | `azure/text-embedding-3-small` | Embedding model |
| `HIERARCHICAL_GROUPING_MAX_DISTANCE` | CLI default | Max cosine distance for grouping |
| `HIERARCHICAL_GROUPING_MAX_NEIGHBORS` | `10` | Max neighbours to consider |
| `HIERARCHICAL_GROUPING_MIN_SAMPLES` | CLI default | Min samples for clustering |
| `PERIODIC_TRIGGER_INTERVAL_SECONDS` | `60` | Periodic trigger interval |

Set either `RABBITMQ_URL`, or `RABBITMQ_USER` and `RABBITMQ_PASSWORD` with optional `RABBITMQ_HOST`, `RABBITMQ_PORT`, and `RABBITMQ_VHOST`.

## Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/hierarchical-grouping-worker

# Run the CLI (syncs dependencies automatically)
uv run --directory workers/hierarchical-grouping-worker hierarchical-grouping-worker-cli --test
```