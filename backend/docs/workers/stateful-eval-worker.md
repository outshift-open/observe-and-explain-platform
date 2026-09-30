# Stateful Eval Worker

In-process stateful evaluation worker — runs temporal metric computation directly as a library, bypassing the HTTP service.

**Source:** [`workers/stateful-eval-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/stateful-eval-worker)

## Overview

The Stateful Eval worker scores agent sessions with the [Stateful Evals](../components/stateful-evals.md)
library. It takes a session ID off a RabbitMQ queue, loads the session's spans from ClickHouse
through the OXP API library (`oxp.client.local.LocalClient`), and evaluates them in-process with
`stateful_evals_be.TemporalMetricsProcessor`. It writes per-span Groundedness, IntentRecognition,
and Relevancy scores and a session `trajectory_score` to the Neo4j knowledge graph, then forwards
the message. Evaluation makes model calls, which can cost money.

`StatefulEvalWorker` (`src/stateful_eval_worker/worker.py`) subclasses the shared
[`worker-base`](../components/worker-base.md) `BaseWorker`.

This repository does not include an upstream worker that routes sessions to this queue. What's
certain from this worker's own source is its queue name:

- **Input queue**: `new_session_to_stateful_eval` (`queues.NEW_SESSION_TO_STATEFUL_EVAL_Q`)
- **Output queue(s)**: none by default — configurable, comma-separated
- **CLI**: `stateful-eval-worker-cli`

### How it works

For each message, `StatefulEvalWorker.handle_message`:

1. Fetches every span of `session_id` with `stateful_evals_be.integrations.oxp.fetch_session_spans`
   (500 per page, oldest first, converted by `oxp_span_to_otel`).
2. Builds a new `TemporalMetricsProcessor` and calls `evaluate_spans(spans, session_id=...)` — the
   same processor `stateful_evals_be.evaluate_spans` uses. No policy override is passed, so the
   policy is whatever system message is found in the spans.
3. Writes the metrics to Neo4j when `PUSH_METRICS` is on and `result.error` is empty.
4. Publishes one output message to each configured output queue.

Fetching, evaluation, and metric writes run in threads; up to `MAX_INFLIGHT_MESSAGES` messages run
at once, sharing one `LocalClient`. If the processor reports an error (e.g. "No spans found for
session"), the worker writes no metrics but still publishes. If fetching or writing raises, it logs
the error, sends an `error` feedback event, and publishes nothing. Either way the message is
acknowledged, not requeued.

### What it writes

The worker only reads ClickHouse; it writes to Neo4j via `LocalClient.write_span_metrics` and
`write_session_metrics`:

| Metric | Attached to | Value |
|---|---|---|
| `mdt.Groundedness`, `mdt.IntentRecognition`, `mdt.Relevancy` | `(:Session {sessionId})-[:hasSpan]->(:Span {spanId})`, created if missing | `0` or `1` per judged `llm` or `tool` span; `tool` spans get no Groundedness |
| `trajectory_score` | An existing `Session` node with that `sessionId`; nothing is written if there is none | `0` or `1`; `reasoning` is `trajectory_reasoning` |

Each metric is a `Metric` node linked by `hasMetric`, with `provider` `stateful_evals`, `source`
`StatefulEval`, `metricId` equal to the name, and `reasoning`. It's matched on `metricName` and
`resourceId`, so a re-run overwrites it. The OXP API's `quality` category reads `trajectory_score`
as a source of `MDT` (`trajectoryQuality`) in [`api/oxp/core/config.py`](../../api/oxp/core/config.py).

## Usage

```bash
# Liveness check: prints "I'm Alive"
uv run --package stateful-eval-worker stateful-eval-worker-cli --test

# Queue mode
uv run --package stateful-eval-worker stateful-eval-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@localhost:5672/ --output-queue <next-queue>

# Run-once mode (Argo Workflows compatible): reads --input, writes --output, no broker connection
echo '{"session_id": "<session-id>"}' > /tmp/stateful-eval-input.json
uv run --package stateful-eval-worker stateful-eval-worker-cli --run-once \
  --rabbitmq-url amqp://<user>:<password>@localhost:5672/ \
  --input /tmp/stateful-eval-input.json --output /tmp/stateful-eval-output.json
```

`--run-once` writes `{"workflow_id": ..., "session_id": ...}` to `--output`, generating a
`workflow_id` if the input has none. `--input` also accepts inline JSON; a JSON array is processed
as a batch and written back as an array. In queue mode, `--max-sessions N` caps the number of
messages processed (`-1`, the default, means no limit). Both modes read spans from ClickHouse —
the worker has no file input for sessions. To evaluate a sample trajectory without a database, use
`stateful_evals_be.evaluate_file` directly, as the
[stateful-evals quickstart](../components/stateful-evals.md#quickstart) does.

### Configuration

Flags override environment variables, except `MAX_INFLIGHT_MESSAGES`, which overrides
`--max-inflight-messages`. From a source checkout, `cli.py` also loads
`workers/stateful-eval-worker/.env` without overriding variables already set.

| Env var | CLI flag | Default | Purpose |
|---|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | none | Broker URL; this or the split variables below are required, even with `--run-once` |
| `RABBITMQ_HOST` / `RABBITMQ_USER` / `RABBITMQ_PASSWORD` / `RABBITMQ_PORT` / `RABBITMQ_VHOST` | _(env only)_ | none / none / none / `5672` / `/` | Alternative to `RABBITMQ_URL`; host, user, and password are required |
| `STATEFUL_EVAL_INPUT_QUEUE` | `--input-queue` | `new_session_to_stateful_eval` | Input queue |
| `STATEFUL_EVAL_OUTPUT_QUEUE` | `--output-queue` (repeatable) | none | Output queue(s), comma-separated |
| `STATEFUL_EVAL_FEEDBACK_QUEUE` | `--feedback-queue` | none | Feedback queue |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | `32` | Concurrent messages / prefetch count; `-1` uses the CPU count |
| `OPENAI_API_KEY` | `--llm-api-key` | empty | Judge model API key |
| `LLM_MODEL_NAME` | `--llm-model-name` | `gpt-4o` | Judge model |
| `LLM_BASE_MODEL_URL_MCE` | `--llm-base-model-url` | `https://api.openai.com/v1` | Judge model endpoint |
| `SAMPLING_STRATEGY`, `SAMPLING_EARLY_RATE`, `SAMPLING_MID_RATE` | _(env only)_ | none / `0.25` / `0.60` | `tail_weighted` judges these shares of spans in the first 40% and next 30%; the rest and anchor spans are always judged |
| `PUSH_METRICS` | _(env only)_ | `true` | `false`/`0`/`no` skips all Neo4j writes |
| `CLICKHOUSE_HOST` / `CLICKHOUSE_PORT` / `CLICKHOUSE_USERNAME` / `CLICKHOUSE_PASSWORD` / `CLICKHOUSE_DATABASE` | _(env only)_ | `localhost` / `8123` / `admin` / `admin` / `default` | Span store (raw OTel traces) |
| `NEO4J_HOST` / `NEO4J_PORT` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | _(env only)_ | `localhost` / `7687` / `neo4j` / empty / `neo4j` | Knowledge graph, used when `PUSH_METRICS` is on; `NEO4J_AUTH=user/password` also sets credentials |

ClickHouse and Neo4j defaults come from `oxp.core.config.settings` in the [`api`](../components/api.md)
package. `LocalClient.from_settings` connects to `bolt://<NEO4J_HOST>:<NEO4J_PORT>` unless
`NEO4J_HOST` is already a URI — a bare host must not include a port. The `worker-base` Neo4j
connector created at startup isn't used by this worker; if it fails to connect, it only logs a
warning.

### Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/stateful-eval-worker

# Run the CLI directly
uv run --package stateful-eval-worker stateful-eval-worker-cli --test
```

### Docker

```bash
docker build -f workers/stateful-eval-worker/deploy/docker/Dockerfile \
  --secret id=ARTIFACTORY_USERNAME,env=UV_INDEX_OUTSHIFT_PYPI_USERNAME \
  --secret id=ARTIFACTORY_PASSWORD,env=UV_INDEX_OUTSHIFT_PYPI_PASSWORD \
  -t stateful-eval-worker .
docker run --rm stateful-eval-worker --test
```

`entrypoint.sh` forwards the container arguments to `stateful-eval-worker-cli` (or the
`INPUT_WORKFLOW` string when none are given) and logs the `--input` file. `docker compose up
stateful-eval` also starts RabbitMQ and Neo4j; ClickHouse isn't a compose service, so
`CLICKHOUSE_HOST` defaults to `host.docker.internal`.

### Development

```bash
uv run --package stateful-eval-worker --extra dev pytest workers/stateful-eval-worker/tests -v
```

The tests mock span fetching, the processor, and the OXP client — no broker, database, or model is
needed.
