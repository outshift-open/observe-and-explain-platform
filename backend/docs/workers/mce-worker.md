# MCE Worker

Standalone Metrics Computation Engine (MCE) worker for processing telemetry sessions.

**Source:** [`workers/mce-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/mce-worker)

## Overview

The MCE worker is the deployable, queue-driven wrapper around the [MCE](../components/mce.md)
library. It reads session messages from a RabbitMQ queue (or a local JSON file in run-once mode),
computes the configured set of metrics for each session via `mce.client.worker.MCEWorkerService`,
writes the results to the knowledge graph, and forwards the message to the next stage.

It sits right after the normalization worker in the ingestion pipeline (see the
[architecture overview](../architecture/overview.md)), running in parallel with the
embedding worker:

- **Input queue**: `new_session_to_mce`
- **Output queue**: `new_session_to_grouping`
- **CLI**: `mce-worker-cli`
- **Config**: `mce_config.yaml` (`--config-file`)

Internally, `MCEWorker` (`workers/mce-worker/src/mce_worker/worker.py`) subclasses the shared
[`worker-base`](../components/worker-base.md) `BaseWorker`, and delegates the actual metric
computation to `MCEWrapper` (`workers/mce-worker/src/mce_worker/wrapper/mce_wrapper.py`), which
wraps `MCEWorkerService`.

## Usage

```bash
# Queue-based mode (long-running worker)
mce-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_mce \
  --output-queue new_session_to_grouping \
  --config-file /path/to/mce_config.yaml

# Run-once mode (Argo Workflows compatible)
mce-worker-cli \
  --run-once \
  --config-file /tmp/mce-config.yaml \
  --input /tmp/input-message.json \
  --output /tmp/mce-output-message.json

# Test liveness
mce-worker-cli --test
```

### Configuration

Which metrics get computed is declared in `mce_config.yaml` — see
[MCE Configuration](../components/mce.md#configuration) for the format. Copy
`workers/mce-worker/.env.template` to `.env` and fill in the values, or pass everything via CLI
flags / environment variables:

| Env var | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full RabbitMQ connection URL. Alternative to the split settings below. |
| `RABBITMQ_HOST` | _(env only)_ | RabbitMQ host when not using `RABBITMQ_URL` |
| `RABBITMQ_PORT` | _(env only)_ | RabbitMQ port when not using `RABBITMQ_URL` |
| `RABBITMQ_USER` | _(env only)_ | RabbitMQ username required in split mode |
| `RABBITMQ_PASSWORD` | _(env only)_ | RabbitMQ password required in split mode |
| `RABBITMQ_VHOST` | _(env only)_ | Optional RabbitMQ virtual host |
| `MCE_INPUT_QUEUE` | `--input-queue` | Input queue name |
| `MCE_OUTPUT_QUEUE` | `--output-queue` | Output queue(s), comma-separated |
| `MCE_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `MCE_CONFIG_PATH` | `--config-file` | Path to `mce_config.yaml` |
| `NEO4J_URI` | `--neo4j-uri` | Neo4j Bolt URI |
| `NEO4J_USERNAME` | `--neo4j-user` | Neo4j username |
| `NEO4J_PASSWORD` | `--neo4j-password` | Neo4j password |
| `NEO4J_DB` | `--neo4j-database` | Neo4j database name |
| `OPENAI_API_KEY` | `--llm-api-key` | LLM API key, for LLM-as-judge metrics |
| `LLM_MODEL_NAME` | `--llm-model-name` | LLM model identifier |
| `LLM_BASE_MODEL_URL_MCE` | `--llm-base-model-url` | LLM base URL (optional) |

Also supported: the common worker flags `--run-once`, `--input`, `--output`, `--test`, `--debug`,
and `--max-sessions`, shared by all [workers](index.md).

### Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/mce-worker

# Sync dependencies and run the CLI directly
uv run --directory workers/mce-worker mce-worker-cli --test
```

### Development

```bash
uv run --package mce-worker --extra dev pytest workers/mce-worker/tests/ -v
```
