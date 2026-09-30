# OXP pipelines

OXP runs two pipelines on top of the same knowledge graph: an **ingestion pipeline**, triggered once per completed MAS session, and a set of **periodic operations**, triggered on independent schedules. See the [architecture overview](overview.md) for how they fit into the platform as a whole.

Both pipelines are built from [workers](../workers/index.md): standalone, independently deployable Python packages that share the [`worker-base`](../components/worker-base.md) framework. This is what makes the pipelines modular — a worker only needs to agree on the RabbitMQ queue(s) it reads from and writes to (or the knowledge graph state it reads/writes for periodic jobs). Nothing else in the pipeline needs to know it exists.

## Why the pipelines are modular

Every worker is:

- **A separate package** — its own `pyproject.toml`, CLI entry point, and `Dockerfile`. It's built and deployed on its own (`uv build workers/<worker-name>`), so shipping or rolling back one worker never touches the others.
- **A queue consumer/producer, not a caller** — a worker only knows the name of the queue(s) it reads from and the queue(s) it writes to. It has no reference to the workers upstream or downstream of it.
- **Runnable two ways** — long-running RabbitMQ queue mode in production, or `--run-once` single-message mode for local testing and Argo Workflows steps.

The practical consequence: adding a new pipeline stage means writing a new worker that subscribes to an existing output queue (or a new knowledge-graph trigger) and publishes its own results — no existing worker is modified.

## Ingestion pipeline

Runs once per completed session, driven end-to-end by chained RabbitMQ queues — each worker's output queue is the next worker's input queue.

```
new_session_in
      │
      ▼
  norm-worker ──────┬────────────────┐
                     │                │
    new_session_to_mce      new_session_to_embedding
                     │                │
                     ▼                ▼
              mce-worker      embedding-worker
                     │                │
                     └───────┬────────┘
                              ▼
                   new_session_to_grouping
                              │
                              ▼
                      grouping-worker
                              │
                              ▼
                   new_session_to_analysis
                              │
                              ▼
                      analysis-worker
              (anomaly detection ‖ consistency ‖ normal behaviour)
```

| Worker | Input queue | Output queue(s) |
|---|---|---|
| [norm-worker](../workers/norm-worker.md) | `new_session_in` | `new_session_to_mce`, `new_session_to_embedding` |
| [mce-worker](../workers/mce-worker.md) | `new_session_to_mce` | `new_session_to_grouping` |
| [embedding-worker](../workers/embedding-worker.md) | `new_session_to_embedding` | `new_session_to_grouping` |
| [grouping-worker](../workers/grouping-worker.md) | `new_session_to_grouping` | `new_session_to_analysis` |
| [analysis-worker](../workers/analysis-worker.md) | `new_session_to_analysis` | — (persists reports to the knowledge graph) |

`analysis-worker` is itself a bundle of three independent analyses — [anomaly-detection](../workers/anomaly-detection-worker.md), [consistency](../workers/consistency-worker.md), and [normal-behaviour](../workers/normal-behaviour-worker.md) — run together for each semantic group. Each analysis is a separate library module; the worker fans the same grouped-session input out to all three and persists whatever reports come back. A session only reaches this stage if `grouping-worker` could assign it to a semantic group.


## Periodic operations

Unlike the ingestion pipeline, periodic workers aren't chained to each other by queues — each one is triggered independently, on its own schedule, and connects to the rest of the platform only through the knowledge graph state it reads and writes. This decoupling is the same modularity principle applied to time instead of events: a new periodic job is just a new worker with its own timer and its own queue, with no dependency on any other periodic worker.

Two workers trigger themselves internally, publishing a trigger message to their own input queue every `periodic_trigger_interval_seconds` (default 600s, configurable per worker):

| Worker | Self-trigger queue | Reads | Writes |
|---|---|---|---|
| [hierarchical-grouping-worker](../workers/hierarchical-grouping-worker.md) | `new_session_to_periodic_grouping` | session input embeddings | updated semantic-group hierarchy; re-emits changed groups to `new_session_to_analysis` |
| [intelligence-worker](../workers/intelligence-worker.md) | `new_session_to_intelligence` | `SemanticGroup`, `AnomalyReport`, `NormalBehaviourReport`, `Metric` nodes | `Insight` nodes, via templates from the [intelligence catalog](../components/intelligence-catalog.md) |


## Adding a new worker

To extend either pipeline:

- **Ingestion stage**: subscribe to an existing output queue (e.g. `new_session_to_analysis`), publish reports or nodes to the knowledge graph (and, optionally, a new output queue for a further downstream worker).
- **Periodic job**: add a worker with its own timer (or its own externally-triggered queue) that reads whatever knowledge-graph state it needs and writes its own results back.

In both cases, no change is required to any other worker — that's the modularity the two pipelines are designed around.
