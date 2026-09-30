# Intelligence Worker

Standalone periodic worker that executes intelligence catalog templates against the knowledge graph and ingests the resulting `Insight` nodes.

**Source:** [`workers/intelligence-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/intelligence-worker)

## Overview

`IntelligenceWorker` (`workers/intelligence-worker/src/intelligence_worker/worker.py`) subclasses the shared [`worker-base`](../components/worker-base.md) `BaseWorker`. Unlike the ingestion-pipeline workers, it isn't chained to an upstream queue — it self-triggers: an internal `asyncio` task sleeps for `periodic_trigger_interval_seconds` (default 600s), then looks up every known application (MAS) id via `db_handler.get_all_application_ids()` and publishes one `BaseTriggerMessage` per application id back onto its own input queue.

Each trigger is handled by `IntelligenceWrapper.generate_insights()` (`workers/intelligence-worker/src/intelligence_worker/wrapper/intelligence_wrapper.py`), which wraps `dem.intelligence`:

1. On startup, `load_templates_from_disk(catalog_root)` (from the [intelligence catalog](../components/intelligence-catalog.md) library) loads every `InsightTemplateModel` — each one a `nameTemplate`/`descriptionTemplate`, a `kgQuery`, and optional `labels`/`scope`/`priority`/`targetNodeId` — from the catalog directory.
2. For the triggered application, every template's `kgQuery` is run against the knowledge graph (`db_handler.generate_insights_from_query`), one row per match.
3. Each row's variables are substituted into the template's `$variable` placeholders to build an `Insight` node (id = sha256 of template id + target node id + rendered name, for de-duplication).
4. The unique resulting `Insight` nodes are ingested into the knowledge graph (`db_handler.ingest_insights`).

This is how `SemanticGroup`, `AnomalyReport`, `NormalBehaviourReport`, and `Metric` nodes (written earlier in the pipeline by [grouping](grouping-worker.md), [analysis](analysis-worker.md), and [mce](mce-worker.md) workers) get surfaced as rendered, human-readable insights — see the [periodic operations](../architecture/pipelines.md#periodic-operations) section of the pipelines doc.

- **Self-trigger queue**: `new_session_to_intelligence`
- **Output queue**: none — results are persisted directly to the knowledge graph
- **CLI**: `intelligence-worker-cli`
- **Config**: `--catalog-root` (path to the [intelligence catalog](../components/intelligence-catalog.md))

## Usage

```bash
# Queue-based mode (long-running worker)
intelligence-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_intelligence \
  --catalog-root intelligence-catalog

# Run-once mode (Argo Workflows compatible)
intelligence-worker-cli \
  --run-once \
  --input /tmp/input.json \
  --output /tmp/output.json \
  --catalog-root intelligence-catalog

# Test liveness
intelligence-worker-cli --test
```

### Configuration

| Env var | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full RabbitMQ connection URL |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` | _(env only)_ | Split RabbitMQ connection settings, alternative to `RABBITMQ_URL` |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | _(env only)_ | Required in split mode |
| `RABBITMQ_VHOST` | _(env only)_ | Optional RabbitMQ virtual host |
| `INTELLIGENCE_INPUT_QUEUE` | `--input-queue` | Self-trigger/input queue name (default `new_session_to_intelligence`) |
| `INTELLIGENCE_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `INTELLIGENCE_CATALOG_ROOT` | `--catalog-root` | Root directory containing intelligence catalog templates (default `.`) |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | Max application jobs processed concurrently per worker process (default `1`, `-1` = auto CPU) |
| `PERIODIC_TRIGGER_INTERVAL_SECONDS` | `--periodic-trigger-interval-seconds` | How often the worker self-triggers (default `600`); also sizes the published message TTL (1.5x interval) |
| _(none)_ | `--template-max-concurrency` | Max insight templates executed concurrently per trigger (default `8`) |

Also supported: the common worker flags `--run-once`, `--input`, `--output`, `--test`, `--debug`, and `--max-sessions`, shared by all [workers](index.md).

### Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/intelligence-worker

# Sync dependencies and run the CLI directly
uv run --directory workers/intelligence-worker intelligence-worker-cli --test
```

### Development

```bash
uv run --package intelligence-worker --extra dev pytest workers/intelligence-worker/tests/ -v
```
