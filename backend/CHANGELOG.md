# Changelog

All notable changes to the OXP backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-30

### Added

Initial open-source release of the OXP backend.

- **[api](docs/components/api.md)** — unified DB access layer across raw OTel spans
  (ClickHouse/SQLite/PostgreSQL) and the knowledge graph (Neo4j), with an optional FastAPI REST
  server on top.
- **[dem](docs/components/analysis.md)** ("analysis") — anomaly detection, consistency checking,
  embeddings, semantic grouping, and lightweight LLM integration over metric, textual, and graph
  representations of MAS executions.
- **[norm](docs/components/norm.md)** — normalizes raw OTel traces into structured MAS execution
  models following the [MAS ontology](../ontology).
- **[mce](docs/components/mce.md)** — Metrics Computation Engine: a pluggable framework computing
  quantitative and LLM-judged metrics for MAS sessions (`Duration`, `Cost`, `AnswerRelevancy`,
  `Groundedness`, and more).
- **[stateful-evals](docs/components/stateful-evals.md)** — cost-effective stateful evaluation of
  a session's trajectory.
- **[intelligence-catalog](docs/components/intelligence-catalog.md)** — catalog of insight
  templates rendered into `Insight` knowledge-graph nodes.
- **[worker-base](docs/components/worker-base.md)** — shared RabbitMQ worker framework
  (`BaseWorker`) used by every standalone worker.
- 11 standalone, independently deployable [workers](docs/workers/index.md) built on
  `worker-base`, covering the ingestion pipeline (`norm-worker` → `mce-worker` /
  `embedding-worker` → `grouping-worker` → `analysis-worker`) and periodic jobs
  (`hierarchical-grouping-worker`, `intelligence-worker`) — see the
  [pipelines documentation](docs/architecture/pipelines.md).
- Local deployment via Docker Compose ([`docker-compose.yml`](docker-compose.yml)), bringing up
  the OTel collector, ClickHouse, Neo4j, RabbitMQ, and the full ingestion pipeline.
- Kubernetes deployment via the Helm charts under [`deploy/k8s`](../deploy/k8s).
