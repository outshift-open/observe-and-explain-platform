# Analysis

Advanced analytics toolkit (package name: `dem`) — anomaly detection, consistency checking, embeddings, semantic grouping, and lightweight LLM integration, operating on metric, textual, and graph representations of MAS executions.

**Source:** [`dem`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/dem)

## Overview

`dem` is a pure-computation library: it has no knowledge-graph or RabbitMQ wiring of its own.
Each submodule exposes a small set of detectors/utilities that the corresponding
[worker](../workers/index.md) imports, feeds with data fetched from the knowledge graph, and
persists the results back:

- **anomaly** and **consistency** — three parallel strategies each (metric, textual, graph),
  consumed by [analysis-worker](../workers/analysis-worker.md)
  ([anomaly-detection](../workers/anomaly-detection-worker.md) /
  [consistency](../workers/consistency-worker.md) analyses).
- **normal_behaviour** — the baseline/"expected" counterpart to anomaly detection, also consumed
  by [analysis-worker](../workers/analysis-worker.md)
  ([normal-behaviour](../workers/normal-behaviour-worker.md) analysis).
- **embedding** — turns session states/text into vectors, consumed by
  [embedding-worker](../workers/embedding-worker.md).
- **grouping** — clusters sessions by embedding similarity, consumed by
  [grouping-worker](../workers/grouping-worker.md) and
  [hierarchical-grouping-worker](../workers/hierarchical-grouping-worker.md).
- **intelligence** — loads and validates insight templates from disk, consumed by
  [intelligence-worker](../workers/intelligence-worker.md) together with the
  [intelligence catalog](intelligence-catalog.md).
- **llm** — a thin async OpenAI-compatible client shared by the grouping/intelligence code paths
  (e.g. naming a semantic group from its member queries).

## Submodules

| Submodule | Path | Purpose |
|---|---|---|
| `anomaly` | `src/dem/anomaly/` | Outlier detection over metric, textual, and graph data |
| `consistency` | `src/dem/consistency/` | Consistency scoring over metric, textual, and graph data |
| `normal_behaviour` | `src/dem/normal_behaviour/` | Models of "normal"/expected behaviour, over metric, textual, and graph data |
| `embedding` | `src/dem/embedding/` | Text/session embedding models and an embedding cache |
| `grouping` | `src/dem/grouping/` | Semantic clustering of sessions/queries from embeddings |
| `intelligence` | `src/dem/intelligence/` | Insight-template loading/validation (Pydantic model + disk loader) |
| `llm` | `src/dem/llm/` | Minimal async LLM client used by grouping (and available to other submodules) |
| `utils` | `src/dem/utils/` | Shared logging, graph (networkx) conversions, and data-store helpers |

Optional dependency extras (`dem/pyproject.toml`) gate the heavier submodules:
`dem[grouping]` (hdbscan, scikit-learn), `dem[llm]` (openai), `dem[embedding]` (sentence-transformers,
transformers, torch, gensim, openai, google-genai), `dem[analysis]` (scikit-learn, scipy), or
`dem[all]` for everything.

## Public API

### Anomaly detection (`dem.anomaly`)

All detectors subclass `AnomalyDetector` and return an `AnomalyDetectionResult`
(`inliers_indices`/`inliers_values`/`outliers_indices`/`outliers_values`), backed by a choice of
scikit-learn models (`elliptic_envelop`, `isolation_forest` — the default, `local_outlier_factor`):

```python
from dem.anomaly import MetricAnomalyDetector

detector = MetricAnomalyDetector()  # defaults to the elliptic_envelop model
result = detector.detect_outliers([1, 1.1, 0.9, 1.11, 1, 1.1, 0.9, 1.11, 10, 11])
print(result.outliers_values, result.outliers_indices)
```

- `MetricAnomalyDetector` — outliers over a `List[float]`.
- `TextualAnomalyDetector` — outliers over textual data.
- `GraphAnomalyDetector` — outliers over `networkx` graphs.

### Consistency (`dem.consistency`)

Mirrors the anomaly module's shape: `Consistency` is the ABC, each concrete class returns a
`ConsistencyResult`.

```python
from dem.consistency import MetricConsistency

result = MetricConsistency().calculate_consistency([1, 1.1, 0.9, 1.11, 1, 1.1, 0.9, 1.11])
```

- `MetricConsistency` — consistency of a `List[float]`.
- `TextualConsistency` — consistency of textual data.
- `GraphConsistency` — consistency of `networkx` graphs, via Weisfeiler-Lehman graph
  distance (`get_wl_labels()` / `wl_distance()`).

### Normal behaviour (`dem.normal_behaviour`)

Same three-way split (`MetricNormalBehaviour`, `TextNormalBehaviour`, `GraphNormalBehaviour`, all
subclassing `NormalBehaviour`), returning one of
`NormalBehaviourResultMetric` / `NormalBehaviourResultText` / `NormalBehaviourResultGraph`
(subclasses of `NormalBehaviourResult`).

### Embedding (`dem.embedding`)

`EmbeddingModel` is the common base; concrete embedders wrap different backends:

```python
from dem.embedding import SentenceTransformerEmbedder

embedder = SentenceTransformerEmbedder(model_id="all-mpnet-base-v2")
vectors = embedder.encode(["Hello, world!"])
```

- `SentenceTransformerEmbedder` — local SBERT models.
- `GensimEmbedder` — Gensim-backed embeddings.
- `OpenAIEmbedder` / `GoogleEmbedder` / `Qwen3Embedder` — hosted embedding APIs.
- `CacheManager` — caches computed embeddings to avoid recomputation.

### Grouping (`dem.grouping`)

```python
from dem.embedding import GoogleEmbedder
from dem.grouping import SemanticGrouper

embeddings = GoogleEmbedder(model_id="gemini-embedding-001").encode([
    "The cat chased the mouse.",
    "The mouse was chased by the cat.",
])
groups = SemanticGrouper().cluster_embeddings_with_radius(embeddings)
```

- `SemanticGrouper` — clusters embeddings (HDBSCAN-based); also exposes
  `get_cluster_hierarchy()` and `compute_semantic_hierarchy()` for the hierarchical grouping used
  by [hierarchical-grouping-worker](../workers/hierarchical-grouping-worker.md).
- `SemanticGroup` / `Hierarchy` — Pydantic models describing a cluster and a cluster hierarchy.

### Intelligence (`dem.intelligence`)

```python
from pathlib import Path
from dem.intelligence import load_templates_from_disk

templates = load_templates_from_disk(Path("intelligence-catalog"))
```

- `load_templates_from_disk(catalog_root)` — parses every `*.json` file under
  `<catalog_root>/insight-templates/` into validated `InsightTemplateModel` instances, skipping
  (and logging) any template that fails validation. See the
  [intelligence catalog](intelligence-catalog.md) for the template format.
- `InsightTemplateModel` — the Pydantic schema (`nameTemplate`, `descriptionTemplate`, `kgQuery`,
  `labels`, `scope`, `priority`, `targetNodeId`).

### LLM (`dem.llm`)

```python
from dem.llm import LLM

llm = LLM(llm_model_name="gpt-4o", llm_api_key="...")
display_name, summary = await llm.generate_group_name(["a query", "another query"])
```

- `LLM` — thin async wrapper (`openai.AsyncOpenAI`) with a bounded concurrency semaphore and
  retry handling; `generate_group_name()` asks the model to summarize a set of queries into a
  short display name, used when naming semantic groups.
- `LLM_GENERATION_ERROR` — sentinel string returned on generation failure.

## Development

```bash
cd dem
uv sync --extra all
uv run pytest -v   # testpaths = src/dem/tests
```
