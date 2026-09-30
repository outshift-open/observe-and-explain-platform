# Grouping Worker

Standalone worker that assigns a session to a semantic group by nearest-neighbour lookup in the knowledge graph.

**Source:** [`workers/grouping-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/grouping-worker)

## Overview

`grouping-worker` is the "quick-grouping" step of the ingestion pipeline (see the
[architecture overview](../architecture/overview.md)): once a session has an embedding and its
metrics, it tries to attach the session to an existing semantic group by cosine-distance lookup —
it does **not** run the HDBSCAN clustering itself. That heavier reclustering job belongs to the
periodic [hierarchical-grouping-worker](hierarchical-grouping-worker.md), which is the one that
actually calls `SemanticGrouper` in the [analysis](../components/analysis.md) library
(`dem.grouping.grouping`). `grouping-worker` only queries the medioid embeddings of existing leaf
`SemanticGroup` nodes (via `oxp.client.dal.get_session_group`) and attaches the session if one is
within `max_distance` cosine distance — so it stays cheap enough to run inline, per session.

Pipeline position:

- **Input queue**: `new_session_to_grouping` (from [mce-worker](mce-worker.md) and
  [embedding-worker](embedding-worker.md))
- **Output queue**: `new_session_to_analysis` (to [analysis-worker](analysis-worker.md))
- **CLI**: `grouping-worker-cli`

`GroupingWorker` (`workers/grouping-worker/src/grouping_worker/worker.py`) subclasses the shared
[`worker-base`](../components/worker-base.md) `BaseWorker`. Before attempting a match, it first
calls `wait_for_hierarchical_grouping_unlock()` (via the DAL) and skips the message (returning
`False`, so it's requeued) if a hierarchical-grouping run currently holds the lock, to avoid
racing against a group reshuffle. On a successful match it also fetches all sessions belonging to
the matched group (`get_analysis_data_for_semantic_group`) and forwards them in the output
`SessionGroupMessage`, so `analysis-worker` can run in run-once mode without a second DB lookup. If
no group is close enough, the session is simply dropped from the pipeline (no output message).

## Usage

```bash
# Queue-based mode (long-running worker)
grouping-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_grouping \
  --output-queue new_session_to_analysis \
  --embedding-model azure/text-embedding-3-small

# Run-once mode (Argo Workflows compatible)
grouping-worker-cli \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/grouping-output-message.json

# Test liveness
grouping-worker-cli --test
```

### Configuration

Copy `workers/grouping-worker/.env.template` to `.env`, or pass everything via CLI flags /
environment variables. Neo4j connection settings are resolved by the API layer
(`oxp.dependencies`) from environment variables — the grouping worker has no Neo4j CLI flags.

| Env var | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full RabbitMQ connection URL. Alternative to the split settings below. |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` | _(env only)_ | RabbitMQ host/port when not using `RABBITMQ_URL` |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | _(env only)_ | RabbitMQ credentials required in split mode |
| `RABBITMQ_VHOST` | _(env only)_ | Optional RabbitMQ virtual host |
| `GROUPING_INPUT_QUEUE` | `--input-queue` | Input queue (default `new_session_to_grouping`) |
| `GROUPING_OUTPUT_QUEUE` | `--output-queue` | Output queue(s), comma-separated (default `new_session_to_analysis`) |
| `GROUPING_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `NEO4J_HOST`/`NEO4J_URI`, `NEO4J_PORT`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | _(env only)_ | Neo4j connection, resolved by the API layer |
| `GROUPING_EMBEDDING_MODEL` | `--embedding-model` | Embedding model used to fetch session/group vectors (default `azure/text-embedding-3-small`) |
| `GROUPING_MAX_DISTANCE` | `--max-distance` | Maximum cosine distance for a match (default `0.3`) |
| `GROUPING_MAX_NEIGHBORS` | `--max-neighbors` | Maximum number of neighbours to consider (default `10`) |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | Concurrent in-flight messages per worker process (default `16`, `-1` = auto CPU) |

Also supported: the common worker flags `--max-sessions`, `--debug`, `--test`, `--run-once`,
`--input`, `--output`, shared by all [workers](index.md).

### Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/grouping-worker

# Sync dependencies and run the CLI directly
uv run --directory workers/grouping-worker grouping-worker-cli --test
```

### Development

```bash
uv run --package grouping-worker --extra dev pytest workers/grouping-worker/tests/ -v
```
