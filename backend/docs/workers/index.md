# Workers

All workers share [`worker-base`](../components/worker-base.md) for RabbitMQ message handling and
the DB access layer, and are built/deployed independently (see each worker's
`deploy/docker/Dockerfile`).

See the [pipelines documentation](../architecture/pipelines.md) for the queue topology and message
flow between workers (both the per-session ingestion pipeline and the periodic jobs).

| Worker | Description |
|---|---|
| [analysis-worker](analysis-worker.md) | Runs anomaly detection, consistency and normal behaviour analyses in parallel |
| [anomaly-detection-worker](anomaly-detection-worker.md) | Identifies outlier sessions within a semantic group |
| [consistency-worker](consistency-worker.md) | Consistency analysis |
| [embedding-worker](embedding-worker.md) | Processes telemetry sessions with vector embeddings |
| [grouping-worker](grouping-worker.md) | Quick-grouping of sessions |
| [hierarchical-grouping-worker](hierarchical-grouping-worker.md) | Hierarchical grouping of sessions |
| [intelligence-worker](intelligence-worker.md) | Executes insight templates from the intelligence catalog |
| [mce-worker](mce-worker.md) | Metrics Computation Engine processing |
| [norm-worker](norm-worker.md) | OTel span normalization |
| [normal-behaviour-worker](normal-behaviour-worker.md) | Normal behaviour modeling |
| [stateful-eval-worker](stateful-eval-worker.md) | In-process temporal/stateful metric computation |
