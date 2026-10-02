# Metrics Computation Engine (MCE)

The Metrics Computation Engine (MCE) — a pluggable framework that computes quantitative and
LLM-judged metrics for MAS (Multi-Agent System) sessions and persists the results back to the
knowledge graph.

**Source:** [`mce`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/mce)

## Overview

MCE evaluates a session (or a batch of sessions) against a configurable set of **metrics** —
things like `Duration`, `Cost`, `AnswerRelevancy`, `Groundedness`, `ToolUtilizationAccuracy`,
`IntentRecognitionAccuracy`, `TaskCompletion`, `WorkflowEfficiency`, `CyclesCount`,
`ToolErrorRate`, and more (see `mce/mce-core/src/mce/core/specs/` for the full catalog). Metrics
can target any level of the MAS ontology (`Session`, `AgentCall`, `LLMCall`, `ToolCall`,
`TaskCall`, `MASCall`), and some are *virtual/aggregate* metrics derived from lower-level results.

In the ingestion pipeline (see the [architecture overview](../architecture/overview.md)), MCE
runs right after the normalization worker has written a session into the knowledge graph: it
fetches the session's context, computes the configured metrics, and writes the results back to
Neo4j so they can be queried alongside the rest of the session's data.

### Where it sits in OXP

```
mce-core     pure computation: metric specs, provider contracts, the scheduling/execution engine
             (no I/O)
    ↑
oxp-api      knowledge-graph provider / connector ownership
    ↑
mce-client   data-access layer: config, Neo4j wiring (via oxp-api), the CLI, an optional REST API
    ↑
mce-worker   the standalone RabbitMQ worker (see the worker doc below) that runs MCE in the
             ingestion pipeline
```

### Sub-packages

MCE is a `uv` workspace of independently versioned packages, all sharing the `mce` namespace
(so `import mce.core`, `import mce.client`, etc. all resolve regardless of which sub-packages are
installed):

| Package | Path | Purpose |
|---|---|---|
| `mce-core` | `mce/mce-core/` | Metric/provider contracts, the metric spec registry, and `MetricEngine` — the dependency-aware scheduler and execution engine. No I/O of its own. |
| `mce-client` | `mce/mce-client/` | The data-access layer: `MCEClient`, `MCEWorkerService`, Neo4j wiring, the `mce` CLI, and an optional FastAPI app. |
| `mce-helper` | `mce/mce-helper/` | Minimal interfaces for third parties authoring new metric providers without depending on the full core. |
| `mce-legacy` | `mce/mce-legacy/` | Backward-compatibility facade/CLI/adapters for the pre-v2 (telemetry-hub era) MCE API. Only loaded if installed. |
| `mce-meta` | `mce/mce-meta/` | Metapackage (no code) that depends on every other sub-package; this is what gets published as `pip install mce`. |
| `mce-provider-native` | `mce/mce-provider-native/` | Built-in metric implementations (quality metrics, session-level metrics, LLM-as-judge prompts). |
| `mce-provider-sdk` | `mce/mce-provider-sdk/` | SDK-backed metrics. |
| `mce-provider-deepeval` | `mce/mce-provider-deepeval/` | Metrics backed by the [DeepEval](https://github.com/confident-ai/deepeval) library. |
| `mce-provider-opik` | `mce/mce-provider-opik/` | Metrics backed by [Opik](https://github.com/comet-ml/opik). |
| `mce-provider-ragas` | `mce/mce-provider-ragas/` | Metrics backed by [Ragas](https://github.com/explodinggradients/ragas). |

Each provider is installable as an optional extra of `mce-core`, e.g. `pip install
mce-core[deepeval]`, `[opik]`, `[ragas]`, `[llm]` (native provider), or `[all]`.

### Public API

- `mce.engine.engine.MetricEngine` — the orchestration engine: `register_metric()`,
  `set_data_provider()`, `set_cache_manager()`, `compute_session(session_id, recursive=...)`,
  `compute_sessions_batch(session_ids)`. Supports several execution strategies (`thread`,
  `process`, `hybrid`, `asyncio`, see `mce/mce-core/src/mce/engine/strategies.py`), a
  `TopologicalScheduler` for ordering metrics by dependency, and a pluggable cache manager.
- `mce.core.metric.Metric` — the ABC every metric plugin implements: `compute(resource_id,
  context) -> MetricResult`, optional `compute_batch()`, and a `metadata: MetricMetadata`
  describing its layer/nature/scope/requirements.
- `mce.core.provider.DataProvider` — the `Protocol` a data backend implements
  (`retrieve()`/`fetch()`/`fetch_batch()`).
- `mce.core.specs.SpecRegistry` — pure-data descriptors of each metric's ontological identity,
  auto-discovered from `mce/core/specs/*.py` (used by `mce metric list --abstract`).
- `mce.core.registry` — plugin discovery (`discover_all_metrics()`, `get_default_metrics()`,
  `load_metrics_from_config()`), via both package scanning and the
  `metrics_computation_engine.plugins` entry-points group.
- `mce.client.client.MCEClient` — the high-level façade:

  ```python
  from mce.client.client import MCEClient

  client = MCEClient()
  results = client.get_metrics(
      "76bc0800-...", metric_ids=["Duration", "Cost", "AnswerRelevancy"]
  )
  ```

- `mce.client.worker.MCEWorkerService` / `WorkerConfig` — the declarative-config worker used by
  both `mce compute` and the standalone `mce-worker`. Loads and validates `mce_config.yaml`
  (schema at `mce/mce-client/src/mce/client/schema/worker_config.schema.yaml`), and exposes
  `process_session(session_id)` / `process_batch(session_ids)` (one bulk KG flush per batch).
- `mce.client.config.MCEClientConfig` — config dataclass, see `.from_env()` in the
  [Configuration](#configuration) section below.

## Usage

### As a library

```python
from mce.client.client import MCEClient

with MCEClient() as client:
    results = client.get_metrics("<session_id>", recursive=True)
    client.compute_and_store("<session_id>")
```

### CLI

`mce-client` installs an `mce` console script:

```bash
mce metric list [--provider native] [--all] [--abstract] [--json]
mce metric show AnswerRelevancy
mce provider list
mce kg metric get <session_id> [--recursive]
mce compute <session_id> [--worker-config /path/to/mce_config.yaml]
```

Global flags: `--debug/--no-debug`, `-v`/`-vv` (verbose logging), `--env-file <path>`.

### Configuration

Which metrics get computed, at which ontology scope, is declared in `mce_config.yaml` (repo root
`/mce_config.yaml`, mounted into the worker container):

```yaml
engine:
  max_workers: 4
  execution_strategy: hybrid

cache:
  path: null
  read: true
  write: true

metrics:
  Session:
    - Duration
    - Cost
    - AnswerRelevancy
    - IntentRecognitionAccuracy
    # - Groundedness
    # - ToolUtilizationAccuracy
    # - TaskCompletion
    # - WorkflowEfficiency
    # - CyclesCount
    # - ToolErrorRate
```

`MCEClientConfig.from_env()` reads the connection/tuning settings:

| Env var | Purpose |
|---|---|
| `NEO4J_URI` / `KG_DB_HOST` | Neo4j Bolt URI |
| `NEO4J_USERNAME` / `KG_DB_USER` | Neo4j username |
| `NEO4J_PASSWORD` / `KG_DB_PASSWORD` | Neo4j password |
| `NEO4J_DATABASE` / `KG_DB_NAME` | Neo4j database name |
| `MCE_METRIC_CACHE` | Enable/disable the metric result cache |
| `MCE_ENGINE_MAX_WORKERS` | Engine worker pool size |
| `MCE_ENGINE_STRATEGY` | Execution strategy (`thread`, `process`, `hybrid`, `asyncio`) |
| `MCE_WORKAROUNDS_FIRST` | Ordering flag for compatibility workarounds |

LLM-as-judge metrics (e.g. `AnswerRelevancy`) additionally need `OPENAI_API_KEY`,
`LLM_MODEL_NAME`, and optionally `LLM_BASE_MODEL_URL_MCE`.

### Running it in the pipeline

MCE is normally not invoked directly — it's run by the standalone
[`mce-worker`](../workers/mce-worker.md), which consumes the `new_session_to_mce` RabbitMQ queue.

### Development

```bash
cd mce
uv sync
uv run pytest tests/ -v
```

### Release

MCE is versioned and released independently of the rest of the monorepo: pushing a `mce-v*` tag
triggers `.github/workflows/publish-mce.yml`, which builds the `mce` metapackage with `uv build`
and publishes it to GitHub Releases (`pip install mce==<version>`).
