# Norm Worker

Standalone normalization worker that converts a completed MAS session's raw OTel spans into a Knowledge Graph.

**Source:** [`workers/norm-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/norm-worker)

## Overview

The norm worker is the deployable, queue-driven wrapper around the [norm](../components/norm.md)
library. It is the first stage of the ingestion pipeline (see the
[architecture overview](../architecture/overview.md)): triggered once a session is complete, it
fetches the session's raw spans, normalizes them into Knowledge Graph nodes/edges following the
MAS ontology, pushes them to Neo4j, and fans the session out to the next two stages.

- **Input queue**: `new_session_in`
- **Output queues**: `new_session_to_mce`, `new_session_to_embedding` — read next by
  [mce-worker](mce-worker.md) and [embedding-worker](embedding-worker.md) respectively
- **CLI**: `norm-worker-cli`

Internally, `NormWorker` (`workers/norm-worker/src/norm_worker/worker.py`) subclasses the shared
[`worker-base`](../components/worker-base.md) `BaseWorker`, and delegates the actual work to
`NormWrapper` (`workers/norm-worker/src/norm_worker/wrapper/norm_wrapper.py`), which:

1. fetches the session's raw ClickHouse-shaped spans via `oxp-api`'s `LocalClient` (see the
   [api](../components/api.md) component),
2. delegates span → events → Knowledge Graph normalization to `norm.normalize()` (the
   [norm](../components/norm.md) library),
3. pushes the resulting nodes/edges to Neo4j (via `oxp.client.dal.ingest_normalized_kg`), and
   optionally dumps the KG to a JSON file (`--kg-output`).

## Usage

```bash
# Queue-based mode (long-running worker)
norm-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_in \
  --output-queue new_session_to_mce \
  --output-queue new_session_to_embedding

# Run-once mode (Argo Workflows compatible)
norm-worker-cli \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/norm-output-message.json \
  --kg-output /tmp/kg.json   # optional: also dump the KG as JSON

# Test liveness
norm-worker-cli --test
```

`input.json` / `output.json` both carry `{"session_id": "<session_id>"}`.

### Configuration

Copy `workers/norm-worker/.env.template` to `.env` and fill in the values, or pass everything via
CLI flags / environment variables:

| Env var | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full RabbitMQ connection URL. Alternative to the split `RABBITMQ_HOST`/`PORT`/`USER`/`PASSWORD`/`VHOST` vars. |
| `NORM_INPUT_QUEUE` | `--input-queue` | Input queue name (default `new_session_in`) |
| `NORM_OUTPUT_QUEUE` | `--output-queue` | Output queue(s), comma-separated (default `new_session_to_mce,new_session_to_embedding`) |
| `NORM_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | Max concurrent sessions per worker process (`-1` = auto, CPU count) |
| — | `--max-sessions` | Stop after N sessions (`-1` = unlimited) |
| — | `--debug` | Verbose logging plus `/tmp/norm_worker_events_<session_id>.jsonl` and `/tmp/norm_worker_kg_<session_id>.json` dumps |
| — | `--override` | Delete any existing Neo4j data for the session before pushing (used for re-processing) |
| `CLICKHOUSE_HOST` / `CLICKHOUSE_PORT` / `CLICKHOUSE_USERNAME` / `CLICKHOUSE_PASSWORD` / `CLICKHOUSE_DATABASE` | — | ClickHouse connection, read by the underlying `oxp-api` DB layer |
| `NEO4J_URI` / `NEO4J_AUTH` / `NEO4J_DB` | — | Neo4j connection, read by the underlying `oxp-api` DB layer |

Also supported: the common worker flags `--run-once`, `--input`, `--output`, `--test`, shared by
all [workers](index.md).

### Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/norm-worker

# Sync dependencies and run the CLI directly
uv run --package norm-worker norm-worker-cli --test
```

### Development

```bash
uv run --package norm-worker --extra dev pytest workers/norm-worker/tests/ -v
```
