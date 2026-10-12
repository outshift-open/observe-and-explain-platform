# Stateful Eval Worker

In-process stateful evaluation worker — runs temporal metric computation directly as a library, bypassing the HTTP service.

**Source:** [`workers/stateful-eval-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/stateful-eval-worker)

## Overview

The Stateful Eval worker scores agent sessions with the [Stateful Evals](../components/stateful-evals.md)
library. It takes a session ID off a RabbitMQ queue, reads the session's normalized trajectory (the
LLM, tool, and agent calls, with their `Transition` and `State` nodes) from the Neo4j
knowledge graph, and evaluates it in-process with `stateful_evals_be.TemporalMetricsProcessor`. It
writes per-step Groundedness, IntentRecognition, and Relevancy scores, the trajectory context each
step contributed, and a session `TrajectoryScore` back to the knowledge graph, then forwards the
message. No OTel store is read. Evaluation makes model calls, which can cost money.

`StatefulEvalWorker` (`src/stateful_eval_worker/worker.py`) subclasses the shared
[`worker-base`](../components/worker-base.md) `BaseWorker`.

This repository does not include an upstream worker that routes sessions to this queue. What's
certain from this worker's own source is its queue name:

- **Input queue**: `new_session_to_stateful_eval` (`queues.NEW_SESSION_TO_STATEFUL_EVAL_Q`)
- **Output queue(s)**: none by default — configurable, comma-separated
- **CLI**: `stateful-eval-worker-cli`

### How it works

For each message, `StatefulEvalWorker.handle_message`:

1. Builds a new `TemporalMetricsProcessor` and calls `evaluate_trajectory(trajectory)`
   on the trajectory read by the OXP API library's `oxp.client.dal.get_session_trajectory`: every
   `LLMCall`, `ToolCall`, and `AgentCall` of the session, in start-time order, with the `Transition` it
   corresponds to and the text of its initial and final `State`, in one query. Steps are
   identified by their KG ids; there is no span id or de-duplication. The policy is the
   first LLM call's system prompt, the request is its first user message, and each agent's own system prompt is recorded as its contract. No
   policy override is passed.
2. Judges each LLM and tool step against the context built from the steps before it, then runs the
   final trajectory audit.
3. Writes the results to Neo4j when `PUSH_METRICS` is on and `result.error` is empty.
4. Publishes one output message to each configured output queue.

Reading, evaluation, and writes run in threads; up to `MAX_INFLIGHT_MESSAGES` messages run at once,
sharing the base worker's Neo4j connector. If the processor reports an error (e.g. "No trajectory
steps found for session"), the worker writes nothing but still publishes. If reading or writing
raises, it logs the error, sends an `error` feedback event, and publishes nothing. Either way the
message is acknowledged, not requeued.

### What it writes

The worker reads and writes Neo4j only, through the shared connector
(`oxp.dependencies.get_neo4j_connector()`):

| Written | Attached to | Value |
|---|---|---|
| `mdt.Groundedness`, `mdt.IntentRecognition`, `mdt.Relevancy` | `(:Transition {id, sessionId})-[:hasMetric]->(:Metric)`; the transition must exist | `0` or `1` per judged LLM or tool step; tool steps get no Groundedness |
| `TrajectoryContext` node | `(:Transition)-[:hasContext]->(:TrajectoryContext {id, evidence, claims, ...})`, one per step (`PUSH_TRANSITION_CONTEXT`) | one JSON property per constituent: what the step added to the trajectory context (see below) |
| `TrajectoryScore` | An existing `Session` node with that `sessionId`; nothing is written if there is none | `0` or `1`; `reasoning` is `trajectory_reasoning` |

Each metric is a `Metric` node linked by `hasMetric`, with `provider` `stateful_evals`, `source`
`StatefulEval`, `metricId` equal to the name, and `reasoning`. It's matched on `metricName` and
`resourceId` (the transition id), so a re-run overwrites it. `Span` nodes are no longer written.
The OXP API's `quality` category reads `TrajectoryScore` as a source of `MDT`
(`trajectoryQuality`) in [`api/oxp/core/config.py`](../../api/oxp/core/config.py).

A `TrajectoryContext` node (a semantic-ontology class) has one JSON property per
constituent, present only when the step contributed it: `evidence`,
`claims`, `coordinationEvents`, `provenanceLinks` and
`flags` (new items with their absolute `index`), `intents` and
`workUnits` (new or changed items, keyed by `index`), and
`finalAnswer` (the answer text). Context that exists before the first step (policy, root
request, agent contracts) is part of the first transition's node, and the context finalized after
the last step part of the last one. The node's id is derived from its transition's and its
properties are replaced, so a re-run overwrites it. Applying the nodes in step order rebuilds the
context at any step.

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
messages processed (`-1`, the default, means no limit). Both modes read the trajectory from Neo4j —
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
| `PUSH_METRICS` | _(env only)_ | `true` | `false`/`0`/`no` skips all Neo4j writes (the trajectory is still read) |
| `PUSH_TRANSITION_CONTEXT` | _(env only)_ | `true` | `false`/`0`/`no` skips writing `TrajectoryContext` nodes |
| `NEO4J_HOST` / `NEO4J_PORT` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | _(env only)_ | `localhost` / `7687` / `neo4j` / empty / `neo4j` | Knowledge graph, read and written; `NEO4J_AUTH=user/password` also sets credentials |

The connector is `oxp.dependencies.get_neo4j_connector()`, the one `BaseWorker` creates at startup
and every other worker uses, so this worker does not close it. It reads `NEO4J_URI` first, else
`NEO4J_HOST`, which may be a bare host, `host:port`, or a URI, and uses `NEO4J_PORT` when the host
has no port.

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
  -t stateful-eval-worker .
docker run --rm stateful-eval-worker --test
```

`entrypoint.sh` forwards the container arguments to `stateful-eval-worker-cli` (or the
`INPUT_WORKFLOW` string when none are given) and logs the `--input` file. `docker compose up
stateful-eval` also starts RabbitMQ and Neo4j.

### Development

```bash
uv run --package stateful-eval-worker --extra dev pytest workers/stateful-eval-worker/tests -v
```

The tests mock span fetching, the processor, and the OXP client — no broker, database, or model is
needed.
