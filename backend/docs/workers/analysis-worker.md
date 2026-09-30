# Analysis Worker

Runs anomaly detection, consistency analysis and normal-behaviour analysis for one semantic
session group, with the three tracks executing in parallel.

**Source:** [`workers/analysis-worker`](https://github.com/cisco-eti/oxp-lib/tree/main/workers/analysis-worker)

This is the analysis worker that runs in the default deployment.
It bundles the three single-purpose workers
([anomaly detection](anomaly-detection-worker.md), [consistency](consistency-worker.md),
[normal behaviour](normal-behaviour-worker.md)) into one process so a group is analysed once
instead of being fetched three times.

## Input

`SessionGroupMessage` from
[`worker-base`](https://github.com/cisco-eti/oxp-lib/tree/main/worker-base/src/worker_base/queue_message.py):

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "group_hash": "abc123",
  "sessions": [
    {
      "session_id": "session-abc",
      "metrics": {"Cost": 1.0},
      "input_content": "...",
      "input_embedding": [0.1, 0.2],
      "output_content": "...",
      "output_embedding": [0.3, 0.4],
      "execution_graph": {"nodes": [], "edges": []}
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `session_id` | yes | May be `""` (hierarchical grouping sends group-only messages) |
| `group_id` | yes | The `SemanticGroup` to analyse |
| `group_hash` | yes | Guards against the group changing mid-analysis. Unlike the three single-purpose workers, this one has no default — a message without it fails validation |
| `sessions` | no | Defaults to `[]`; `null` is coerced to `[]` |

**`sessions` is the switch between the two data paths:**

- **Non-empty** — the payload is analysed directly. No Neo4j read.
- **Empty** — the worker waits for the hierarchical-grouping lock
  (`wait_for_hierarchical_grouping_unlock()`), then loads the group with
  `get_analysis_data_for_semantic_group(group_id, group_hash, embedding_model)`. This path needs
  both a DB connection and `--embedding-model`; without either the message is dropped.

## Output

Reports are written to Neo4j in all modes. Each track MERGEs a report node and links it to the
`SemanticGroup`:

| Track | Node | Edge |
|---|---|---|
| Anomaly | `AnomalyReport` | `hasAnomalyReport` |
| Consistency | `ConsistencyReport` | `hasConsistencyReport` |
| Normal behaviour | `NormalBehaviourReport` | `hasNormalBehaviourReport` |

In file-based run-once mode an `AnalysisOutputMessage` is also written to `--output`:

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "batch_index": 1,
  "batch_session_count": 12,
  "sessions": [],
  "anomalies": [{"layer": "text", "inlier_sessions": ["..."], "outlier_sessions": ["..."], "reason": "...", "scores": [], "metadata": {}}],
  "consistency": [{"layer": "text", "consistency_result": {"mean": 0.94, "...": "..."}, "session_ids": ["..."], "metadata": {}}],
  "normal_behaviour": [{"layer": "text", "normal_behaviour": {"centroid": [], "...": "..."}, "session_ids": ["..."], "metadata": {}}]
}
```

> **Note:** `sessions` is always empty and `batch_index` is always 1
    `_analyze_message` sets `sessions=[]` deliberately — the input payload is not echoed back, so
    output files stay small. The three single-purpose workers do echo their input sessions.
    `batch_index` is hardcoded to `1` and `batch_session_count` holds the number of sessions
    actually analysed; neither reflects any real batching today.

A single input object produces a single output object (or `{}` if the message produced nothing);
a JSON array of input messages produces an array, with messages that produced nothing omitted.

## Position in the pipeline

```text
grouping-worker                 (per session, inline sessions[] attached)
hierarchical-grouping-worker    (periodic, per group, no inline sessions)
        │
        └──► new_session_to_analysis ──► analysis-worker ──► Neo4j
                                                             AnomalyReport
                                                             ConsistencyReport
                                                             NormalBehaviourReport
```

| | |
|---|---|
| Input queue | `new_session_to_analysis` (`ANALYSIS_INPUT_QUEUE`) |
| Output queue | none — the CLI passes `output_queue=[]` |
| CLI | `analysis-worker-cli` |
| Terminal? | Yes. Results are read back out of the graph by the API and UI, not forwarded to another queue. |

The message producing workers are the [grouping worker](grouping-worker.md) (one message per newly grouped session,
carrying the group's sessions inline) and the
[hierarchical grouping worker](hierarchical-grouping-worker.md) (one message per group that is new
or needs re-analysis, with no inline sessions).

## Quick start

```bash
# Liveness check — prints "I'm Alive" and exits
uv run --directory workers/analysis-worker analysis-worker-cli --test
```

Queue mode:

```bash
analysis-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_analysis \
  --embedding-model azure/text-embedding-3-small \
  --max-inflight-messages 4
```

Run-once against a file (Argo-compatible, accepts one object or an array):

```bash
analysis-worker-cli \
  --run-once \
  --embedding-model azure/text-embedding-3-small \
  --input /tmp/grouping-output.json \
  --output /tmp/analysis-output.json
```

Run-once against the queue — consumes exactly one message and exits:

```bash
analysis-worker-cli --run-once --embedding-model azure/text-embedding-3-small
```

Build a wheel:

```bash
uv build workers/analysis-worker
```

## Configuration

Copy `.env.template` to `.env`, or pass flags. Neo4j settings are resolved by the API layer
(`oxp.dependencies`) from the environment — this worker exposes no Neo4j flags.

| Environment variable | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full connection URL |
| `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_VHOST` | _(env only)_ | Split alternative to `RABBITMQ_URL`; user and password are required in this mode |
| `ANALYSIS_INPUT_QUEUE` | `--input-queue` | Input queue name |
| `ANALYSIS_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `EMBEDDING_MODEL` | `--embedding-model` | Needed whenever `sessions` is empty |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | Concurrency; `-1` = `max(1, cpu_count // 3)` |
| — | `--max-sessions` | Stop after N messages (`-1` = unlimited) |
| — | `--batch_size` | Accepted for memory tuning; see the note below |
| `ANOMALY_CONFIG_FILE` | `--anomaly-config-file` | YAML layer config for anomaly detection |
| `CONSISTENCY_CONFIG_FILE` | `--consistency-config-file` | YAML layer config for consistency |
| `NORMAL_BEHAVIOUR_CONFIG_FILE` | `--normal-behaviour-config-file` | YAML layer config for normal behaviour |
| `NEO4J_HOST`/`NEO4J_URI`, `NEO4J_PORT`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | _(API-managed)_ | Used by the API DAL |

Each config file is the same YAML the corresponding single-purpose worker takes. When a file is
omitted the track uses its defaults:

```yaml
# --anomaly-config-file
text:   { model_name: isolation_forest }
graph:  { model_name: isolation_forest }
metric: { model_name: elliptic_envelop }

# --consistency-config-file
text:   { statistic: dispersion }
graph:  { statistic: average_pairwise_wl_distance }
metric: { statistic: std }

# --normal-behaviour-config-file
text:   { statistic: gaussian }
graph:  { statistic: consensus }
metric: { statistic: gaussian }
```

## Concurrency model

Two independent levels of parallelism:

1. **Process pool.** `--max-inflight-messages N` does not set a per-process prefetch. The CLI
   computes `processes = N * 3` and starts that many independent worker processes, each with
   prefetch 1. The multiplier exists so the pool can keep `N` messages' worth of 3-track work busy
   while side-stepping the GIL for CPU-bound analysis. With `N = 4` you get **12 processes and up
   to 12 concurrent queue messages**, not 4.
2. **Tracks within a message.** The three analyses run concurrently under
   `asyncio.gather` with an `asyncio.Semaphore(3)`, each in a thread via `asyncio.to_thread`.

Run-once mode forces `max_inflight_messages=1` and `message_limit=1`, keeping `n_workers` at 3 so
the tracks still overlap.

> **Warning:** `--batch_size` is currently inert
    `--batch_size` is parsed, logged and passed into `AnalysisWorker`, and the class carries a
    `spawn`-based batch-subprocess path with halving retry on failure
    (`_run_batch_analysis_subprocess_sync`). The live handler `_analyze_message` does not call it,
    so the flag has no effect on how a message is processed today.

## Per-track behaviour

Before persisting, each track independently calls
`analysis_pre_check(group_id, report_type, group_hash, session_id)` for its own report type and
skips when the group hash no longer matches or a report of that type already exists. A track that
is skipped or finds no data returns an empty list; the other two still run.

The methodology for each track is documented with its single-purpose worker:

- **[Anomaly detection](anomaly-detection-worker.md#Methodology)** — scikit-learn outlier models over
  embeddings, execution-graph path n-grams, and per-metric values.
- **[Consistency](consistency-worker.md#Methodology)** — bootstrapped dispersion statistics turned
  into a 0–1 "how alike is this group" score with a confidence indicator.
- **[Normal behaviour](normal-behaviour-worker.md#Methodology)** — centroids, Gaussian/quantile
  envelopes, and consensus or medoid graphs describing what a typical session looks like.

