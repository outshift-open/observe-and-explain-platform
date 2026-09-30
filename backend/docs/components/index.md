# Components

The core libraries and services that make up the OXP backend. Each one can be used as a
standalone Python library; some also expose a service on top (e.g. the API's REST server, or the
standalone [workers](../workers/index.md) built on `worker-base`).

| Component | Description |
|---|---|
| [api](api.md) | Unified DB access layer across raw OTel spans and the knowledge graph, with an optional REST API |
| [analysis](analysis.md) | Anomaly detection, consistency checking, embeddings, and semantic grouping toolkit |
| [mce](mce.md) | Metrics Computation Engine — computes quantitative and LLM-judged metrics for MAS sessions |
| [norm](norm.md) | OTel → Knowledge Graph normalization |
| [worker-base](worker-base.md) | Shared RabbitMQ worker framework used by all [workers](../workers/index.md) |
| [intelligence-catalog](intelligence-catalog.md) | Insight template catalog |
| [stateful-evals](stateful-evals.md) | Cost-effective stateful evaluation of a session's trajectory |
