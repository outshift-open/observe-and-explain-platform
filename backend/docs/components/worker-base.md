# Worker Base

Shared RabbitMQ worker framework: every standalone worker in [`workers/`](../workers/index.md) subclasses its `BaseWorker`.

**Source:** [`worker-base`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/worker-base)

## Overview

`worker-base` is not a worker itself — it's the runtime every worker in the ingestion and
periodic pipelines (see the [pipelines documentation](../architecture/pipelines.md)) is built on
top of: async RabbitMQ consume/produce via `aio_pika`, Pydantic message schemas, feedback-queue
events, and an alternate single-message "Argo" mode for local testing or an Argo Workflows step.
All 11 workers under `backend/workers/` (`analysis-worker`, `anomaly-detection-worker`,
`consistency-worker`, `embedding-worker`, `grouping-worker`, `hierarchical-grouping-worker`,
`intelligence-worker`, `mce-worker`, `norm-worker`, `normal-behaviour-worker`,
`stateful-eval-worker`) subclass `BaseWorker` and only implement `handle_message()` plus their own
CLI.

`worker-base` itself ships no CLI or argparse/click layer — the common flags every worker exposes
(`--run-once`, `--input`, `--output`, `--test`, `--debug`, `--max-sessions`,
`--max-inflight-messages`, `--rabbitmq-url`) are a convention each worker's own CLI module
implements (see e.g. `workers/norm-worker/src/norm_worker/cli.py`), built on top of the helper
functions `worker-base` provides in `worker_base.utils` (below).

## Public API

### `BaseWorker` (`worker_base.base_worker`)

Constructor (verified against `base_worker.py`):

```python
BaseWorker(
    rabbitmq_url: str,
    input_queue: str,
    output_queue: list[str] = [],
    feedback_queue: str | None = None,
    message_limit: int = -1,              # -1 = unlimited
    max_inflight_messages: int = 1,
    output_message_ttl_seconds: float | None = None,
)
```

On construction it also tries to obtain a Neo4j connector via
`oxp.dependencies.get_neo4j_connector()` and wraps it in an `OXPApiDALAdapter` as
`self.db_handler`; if that fails (e.g. no DB configured), `db_handler` is left `None` and a
warning is logged instead of raising.

Key methods/attributes a subclass uses:

- `self.name` — worker name used in logs and feedback messages.
- `self.input_message_class` — the `BaseMessage` subclass (see below) used to deserialize incoming
  messages.
- `async handle_message(msg) -> bool | None` — **must be overridden**; the base implementation
  raises `NotImplementedError`. Return `True` to propagate `self.output_messages` to the output
  queue(s), `False` for a successful no-op (nothing propagated), `None` to signal an error (a
  `error` feedback event is emitted).
- `self.emit_output_message(message)` / `self.output_messages` — append to (or set) the message(s)
  to propagate; output messages are stored per-`asyncio` task (via `contextvars`) so concurrent
  in-flight messages don't clobber each other's output.
- `async run()` — starts the long-running RabbitMQ consumer (`run_worker()`): declares
  `input_queue`, sets QoS/prefetch from `max_inflight_messages`, and processes messages
  concurrently up to that limit, sending `start`/`complete`/`error` events to `feedback_queue` (if
  set) around each `handle_message()` call.
- `async run_argo_message(raw_input, output_path)` — single-message (or batch-of-messages, if
  `raw_input` is a JSON array) mode with no RabbitMQ involved: validates the input against
  `input_message_class`, calls `handle_message()`, and writes the serialized output message(s) to
  `output_path`. This is what every worker's `--run-once --input ... --output ...` CLI flags drive.
- `async propagate_message()` / `send_message_to_all()` / `send_message_to_queue()` — fan the
  current `output_messages` out to `self.output_queue` (or a specific queue).

### Messages (`worker_base.queue_message`)

Pydantic models, all subclassing `BaseMessage` (`job_id`, `workflow_id`, `local_file`, all
optional) with `write_message()` (publish to a channel/queue, persistent delivery, optional
`ttl_seconds`), `from_body()` (deserialize) and `dump_message()`:

| Class | Adds |
|---|---|
| `BaseQueueMessage` | `session_id` (required) — the common input/output message for most workers |
| `BaseTriggerMessage` | `application_id` (required) — used by self-triggered periodic workers |
| `MasMetricTriggerMessage` | `metric_name`, `mas_name` (optional) |
| `ImpactAssessmentTrainingMessage` | `end_to_end_mode`, `is_training_step` |
| `MultiSessionQueueMessage` | `session_ids` (list), `group_id` |
| `SessionDetailMessage` / `SessionDetail` | metrics, input/output content and embeddings, execution graph |
| `SessionGroupMessage` | `group_id`, `group_hash`, `sessions` |

`FeedbackMessage` (a plain class, not a Pydantic model) carries `session_id`, `event`
(`start`/`complete`/`error`), `workflow`, `workflow_id`, `queue_name` and is what `BaseWorker`
publishes to `feedback_queue` around each `handle_message()` call.

### DAL adapter (`worker_base.dal_adapter.OXPApiDALAdapter`)

A compatibility adapter that exposes the knowledge-graph operations workers need
(`ingest_anomaly_report`, `ingest_consistency_report`, `ingest_normal_behaviour_report`,
`ingest_insights`, `get_analysis_data_for_semantic_group`, `get_semantic_group_hierarchy`,
`get_session_io_embeddings`, `get_mas_name`, `get_all_application_ids`,
`generate_insights_from_query`, `wait_for_hierarchical_grouping_unlock`, `analysis_pre_check`),
delegating to the stateless functions in `oxp.client.dal` (from the [`api`](api.md) library)
against an injected `Connector`. Accessed as `self.db_handler` on a worker instance.

### Utilities (`worker_base.utils`)

Helpers shared by every worker's CLI:

- `resolve_rabbitmq_url(explicit_url=None)` — resolves `--rabbitmq-url` in order: explicit value →
  `RABBITMQ_URL` env var → split `RABBITMQ_HOST`/`RABBITMQ_PORT`/`RABBITMQ_USER`/
  `RABBITMQ_PASSWORD`/`RABBITMQ_VHOST` env vars. Raises if nothing is configured.
- `resolve_max_inflight_messages(cli_value, *, error_subject)` — `-1` resolves to the available
  CPU count (`get_available_cpus()`); also readable from the `MAX_INFLIGHT_MESSAGES` env var.
- `resolve_neo4j_auth(...)` — resolves Neo4j credentials from `NEO4J_AUTH` (`user/password`) or the
  split `NEO4J_USERNAME`/`NEO4J_PASSWORD` env vars.
- `configure_worker_logging(*, debug=False)` — installs a colored `StreamHandler` formatter on the
  root logger and quiets `neo4j.notifications`.
- `mask_url_password(url)` — redacts the password in a connection URL for safe logging.

## Development

```bash
cd worker-base
uv sync
uv run pytest tests/ -v
```

Tests live in `worker-base/tests/` (`test_base_worker.py`, `test_queue_message.py`).
