# Observe and eXplain Platform (OXP)

OXP is a modular platform for observing, analyzing, and explaining the executions of Multi-Agent Systems (MAS) from OpenTelemetry traces. It ingests raw OTel spans, maps them onto a shared MAS ontology, and enriches each session with analysis such as semantic grouping, anomaly detection, consistency checking, and stateful trajectory evaluation — surfaced through a web dashboard.

## How it works

1. A MAS sends OTel spans to an OTel collector, which stores them (ClickHouse by default, swappable for another backend).
2. Once a trace is complete, the OXP ingestion pipeline maps the raw spans onto the [MAS ontology](ontology), producing a structured execution model.
3. The session representation is enriched by the analysis workers (semantic grouping, anomaly detection, consistency checking, stateful evaluation, metrics).
4. The enriched knowledge graph is served through the [API](backend/api) and visualized in the [UI](ui), giving explainability and insight into the MAS's inner workings.

## Repository structure

| Path | Description |
| --- | --- |
| [`backend/`](backend) | Python libraries and workers implementing ingestion, normalization, analysis, and the data API. See [backend/README.md](backend/README.md). |
| [`backend/api`](backend/api) | Unified DB access layer and REST API over the raw OTel spans and the knowledge graph. |
| [`backend/norm`](backend/norm) | Normalizes raw OTel traces into structured MAS execution models. |
| [`backend/mce`](backend/mce) | Metric computation engine for sessions. |
| [`backend/stateful-evals`](backend/stateful-evals) | Cost-effective evaluation of a session's trajectory. |
| [`backend/workers`](backend/workers) | Standalone workers built on top of the backend libraries. |
| [`ui/`](ui) | React/TypeScript web dashboard for browsing applications, sessions, execution graphs, and live topology. See [ui/README.md](ui/README.md). |
| [`ontology/`](ontology) | The MAS telemetry ontology (Turtle/OWL) and the `oxp-ontology` Python package. See [ontology/README.md](ontology/README.md). |
| [`deploy/`](deploy) | Helm charts for deploying OXP (API, UI, workers, and supporting infra) to Kubernetes. |

## Getting started

Each component has its own setup instructions:

- Backend (API, workers, local Docker Compose stack): [backend/README.md](backend/README.md)
- UI (dashboard): [ui/README.md](ui/README.md)
- Ontology (Python package, docs, versioning): [ontology/README.md](ontology/README.md)
- Kubernetes deployment: [deploy/k8s/charts/oxp/README.md](deploy/k8s/charts/oxp/README.md)

For a fully local stack, see the [backend Docker Compose setup](backend/README.md#deployment), which spins up the OTel collector, ClickHouse, Neo4j, and the ingestion pipeline together.

## Documentation

- **Backend architecture & components**: [backend/docs/index.md](backend/docs/index.md) — architecture overview, pipelines, [component docs](backend/docs/components/index.md), and [worker docs](backend/docs/workers/index.md).
- **Ontology**: [ontology/index.md](ontology/index.md), also published at [outshift-open.github.io/observe-and-explain-platform](https://outshift-open.github.io/observe-and-explain-platform/)

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards, and [SECURITY.md](SECURITY.md) for reporting vulnerabilities. Maintainers are listed in [MAINTAINERS.md](MAINTAINERS.md).

## License

Licensed under the terms in [LICENSE](LICENSE).
