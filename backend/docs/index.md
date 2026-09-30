# OXP — Observe and eXplain Platform

The Observe and eXplain Platform (OXP) is a modular platform for analyzing and visualizing Multi-Agent System (MAS) executions from OpenTelemetry traces. It relies on a multi-layers knowledge graph, which holds representations of the different sessions (runs) of a given MAS that were observed previously.

The lifecycle of one MAS session within OXP is the following:
1. The MAS sends OTel spans to an OTel collector, which, in turn, sends these spans to a storage place (currently using ClickHouse DB, but it can be replaced by another one quite easily).
2. When the trace is complete, the OXP ingestion pipeline is triggered and the Otel spans are mapped to an ontology modeling MAS execution.
3. The representation of the session is then enriched via the different analysis modules.
4. Through the enrichment of each session of a MAS, OXP is able to provide explainability and insights about the inner workings of the MAS.

The rest of this documentation provides a detailed view of the different pieces of OXP.

## Where to start

- **[Architecture overview](architecture/overview.md)** — how the pieces fit together.
- **[Components](components/index.md)** — the core libraries and services (API, Analysis, MCE, norm, ...).
- **[Workers](workers/index.md)** — the standalone RabbitMQ-driven analysis workers.

## Repo layout

| Area | What it is |
|---|---|
| [`api/`](components/api.md) | Unified DB access layer / REST API |
| [`dem/`](components/analysis.md) | Anomaly detection, consistency, embeddings, clustering toolkit |
| [`mce/`](components/mce.md) | Metrics Computation Engine and providers |
| [`norm/`](components/norm.md) | OTel → Knowledge Graph normalization |
| [`worker-base/`](components/worker-base.md) | Shared RabbitMQ worker framework |
| [`workers/`](workers/index.md) | 11 standalone analysis workers |
| [`intelligence-catalog/`](components/intelligence-catalog.md) | Insight template catalog |
| [`stateful-evals/`](components/stateful-evals.md) | stateful evaluation library |
