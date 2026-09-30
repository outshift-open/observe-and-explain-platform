# Anomaly Detection Worker

Standalone anomaly detection worker: within one semantic group of sessions, it separates typical
sessions from outliers on three layers (text, execution graph, metrics) and writes an
`AnomalyReport` per layer.

**Source:** [`workers/anomaly-detection-worker`](https://github.com/cisco-eti/oxp-lib/tree/main/workers/anomaly-detection-worker)

!!! info "Relationship to the analysis worker"
    The default `docker-compose` deployment runs the combined
    [analysis worker](analysis-worker.md), which embeds this same logic alongside consistency and
    normal behaviour. This standalone worker exists for deployments that want to scale or schedule
    anomaly detection separately (for example as an Argo Workflows step).

The key idea: anomalies here are **relative to a peer group**, never absolute. A session is an
outlier because it differs from the other sessions doing the same kind of work, so the grouping
stage must run first and the group must contain enough sessions for "typical" to mean anything.

## Input

`AnomalyDetectionInputMessage`:

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "group_hash": "abc123",
  "sessions": [
    {
      "session_id": "session-abc",
      "metrics": {"Cost": 1.0, "Latency": 230},
      "output_content": "...",
      "output_embedding": [0.1, 0.2],
      "execution_graph": {"nodes": [], "edges": []}
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `session_id` | yes | Used for the idempotency pre-check and the group-membership guard |
| `group_id` | yes | The `SemanticGroup` to analyse |
| `group_hash` | no | Defaults to `""`, which disables the hash guard |
| `sessions` | no | Defaults to `[]` |

`sessions` selects the data path:

- **Non-empty** — analysed as-is; Neo4j is never read, and no embedding model is needed.
- **Empty** — needs `--embedding-model` and a live DB connection. The worker waits for the
  hierarchical-grouping lock, runs `analysis_pre_check(group_id, "AnomalyReport", group_hash,
  session_id)`, loads the group with `get_analysis_data_for_semantic_group`, and drops the message
  if `session_id` is not actually a member of the group.

## Output

**Queue output: none.** The CLI hardcodes `output_queue=[]`, so this worker is terminal.

**Graph output:** one `AnomalyReport` per layer, linked from the `SemanticGroup` by
`hasAnomalyReport`:

| Property | Value |
|---|---|
| `id` | `sha256(group_id + layer + metric_name)` |
| `dataType` | `text`, `graph`, or `metric` |
| `inlierSessions` / `outlierSessions` | Session id lists |
| `reason` | Human-readable layer description |
| `scores` | JSON list of per-session model scores |
| `threshold` | Decision threshold |
| `nodeHash` | `group_hash`, or `sha256` of the sorted session ids when `group_hash` is empty |
| `aboutMetric` | Set on metric reports only, linking to the `Metric` node |

The `reason` strings are fixed: `Anomalies detected in text embeddings`,
`Anomalies detected in graph structure`, and `Anomalies detected in metric <name>`.

Ingestion goes through `verify_kg_object`, so a report that violates the SHACL shapes raises
`OntologyValidationError` and is not written.

> **Note:** `scores` and `threshold` are always empty
    The detectors in `dem` build their `AnomalyDetectionResult` from the model's `fit_predict`
    labels only; they never populate `scores` or `threshold`. So `scores` is persisted as `[]` and
    `threshold`, being `None`, is written as `0.0`. Treat the inlier/outlier split as the real
    output and ignore these two fields.

**File output (run-once):** `AnomalyDetectionOutputMessage`, echoing the session data it analysed
plus an `anomalies` array:

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "sessions": [{"session_id": "session-abc", "...": "..."}],
  "anomalies": [
    {
      "inlier_sessions": ["session-abc", "session-def"],
      "outlier_sessions": ["session-ghi"],
      "reason": "Anomalies detected in text embeddings",
      "layer": "text",
      "scores": [],
      "metadata": {"model_name": "isolation_forest"}
    }
  ]
}
```

## Position in the pipeline

```text
grouping-worker / hierarchical-grouping-worker
        │
        └──► new_session_to_anomaly ──► anomaly-detection-worker ──► Neo4j (AnomalyReport)
```

| | |
|---|---|
| Input queue | `new_session_to_anomaly` (`ANOMALY_INPUT_QUEUE`) |
| Output queue | none |
| CLI | `anomaly-detection-worker-cli` |

> **Warning:** No producer publishes to this queue in the default deployment
    In `docker-compose.yml` the grouping workers publish to `new_session_to_analysis`, which the
    combined [analysis worker](analysis-worker.md) consumes. Running this worker means either
    repointing a producer at `new_session_to_anomaly` or driving it in run-once mode.

## Quick start

```bash
# Liveness check
uv run --directory workers/anomaly-detection-worker anomaly-detection-worker-cli --test
```

Queue mode:

```bash
anomaly-detection-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_anomaly \
  --embedding-model azure/text-embedding-3-small
```

Run-once against a file:

```bash
anomaly-detection-worker-cli \
  --run-once \
  --input /tmp/group.json \
  --output /tmp/anomalies.json
```

`--run-once` raises a usage error unless both `--input` and `--output` are given. If the input file
contains inline `sessions`, no database or embedding model is needed.

Build a wheel:

```bash
uv build workers/anomaly-detection-worker
```

## Configuration

Copy `.env.template` to `.env`, or pass flags.

| Environment variable | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full connection URL |
| `ANOMALY_INPUT_QUEUE` | `--input-queue` | Input queue name |
| `ANOMALY_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `EMBEDDING_MODEL` | `--embedding-model` | Needed whenever `sessions` is empty |
| `ANOMALY_CONFIG_FILE` | `--config-file` | YAML layer config |
| — | `--max-sessions` | Stop after N messages (`-1` = unlimited) |
| `NEO4J_HOST`, `NEO4J_PORT`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DB` | _(API-managed)_ | Read by the API DAL, not by CLI flags |

The YAML config selects which layers run and which model each uses. Omitting it is equivalent to:

```yaml
text:
  model_name: isolation_forest
graph:
  model_name: isolation_forest
metric:
  model_name: elliptic_envelop
```

To run only the metric layer with a different model:

```yaml
metric:
  model_name: local_outlier_factor
```

## Methodology

Source: [`dem/src/dem/anomaly/`](https://github.com/cisco-eti/oxp-lib/tree/main/dem/src/dem/anomaly).

Each layer turns its sessions into a numeric feature matrix, hands it to a scikit-learn outlier
model, and reads the `+1 / -1` labels back:

```text
   sessions in the group
        │
        ├─ 1. featurise    ──► matrix X of shape (n_sessions, n_features)
        │
        ├─ 2. fit_predict  ──► label per session: +1 inlier, -1 outlier
        │
        └─ 3. map labels back to session ids
```

`fit_predict` is used rather than `fit` then `predict`, meaning **the model is fitted on the very
data it judges**. There is no training phase and no persisted model; each group is scored in
isolation.

### The models

`AnomalyDetector` (`base.py`) exposes three, keyed by the `model_name` config value. No extra
keyword arguments are forwarded, so scikit-learn's defaults apply throughout.

#### `isolation_forest` — default for text and graph

Builds 100 random trees. Each tree recursively splits the data by picking a random feature and a
random split value between that feature's min and max, until points are isolated. A point's
anomaly score is derived from `E[h(x)]`, its average isolation depth across the forest, normalised
against `c(n)`, the expected depth in a binary search tree of the same size:

```text
s(x) = 2 ^ ( - E[h(x)] / c(n) )
```

Shallow depth gives a score near 1, so points that get isolated after only a few splits sit in
sparse regions and score high. With
`contamination="auto"` the decision offset is fixed at `-0.5`, which corresponds to `s(x) ≈ 0.5` —
the score of a point at the expected average depth. The number of outliers is therefore not fixed
in advance. `max_samples="auto"` caps each tree's training subsample at 256 points.

Isolation Forest is the default for the two high-dimensional layers because its cost grows linearly
with dimensionality and it makes no distributional assumption.

#### `elliptic_envelop` — default for metrics

Fits a robust Gaussian by Minimum Covariance Determinant: it searches for the subset of points
whose covariance matrix has the smallest determinant (the tightest ellipsoid), and estimates the
mean and covariance from that subset only, so a few extreme values cannot drag the fit. Points are
then scored by squared Mahalanobis distance:

```text
d(x) = (x - mu)^T * Sigma^-1 * (x - mu)
```

The cutoff comes from `contamination`, which defaults to `0.1` in scikit-learn.

> **Warning:** Elliptic Envelope flags roughly 10% of sessions by construction
    Because `contamination` defaults to `0.1` and no override is passed, this model marks about a
    tenth of each group as outliers for every metric, whether or not any session is genuinely
    unusual. Its own documentation also notes it is "not expected to yield meaningful results when
    `n_samples > n_features ^ 2`", and the metric layer has exactly one feature. Small groups with
    a genuinely tight metric spread are the worst case here; the explicit guards below catch the
    degenerate ones, but not this general bias.

#### `local_outlier_factor` — opt-in

Compares the local density around a point to the density around its 20 nearest neighbours:

```text
LOF(x) = mean over neighbours m of ( local_density(m) / local_density(x) )
```

`LOF ≈ 1` means the point is as tightly packed as its neighbourhood; substantially greater than 1
means it sits in a comparatively sparse pocket. Unlike the other two this is a local criterion, so
it can flag a point that is unusual for its own cluster even when a group contains several distinct
clusters.

### Text layer

`TextualAnomalyDetector` (`textual_detector.py`). The feature matrix is simply each session's
`output_embedding` stacked into an `(n_sessions, embedding_dim)` array — no dimensionality
reduction or rescaling. Sessions whose generated output is semantically unlike the rest of the
group come out as outliers.

Guards: if every embedding is identical, the model is skipped and all sessions are inliers.

### Graph layer

`GraphAnomalyDetector` (`graph_detector.py`). Execution graphs are not numeric, so they are turned
into a **bag of execution paths**.

**Step 1 — enumerate paths.** `_extract_path_ngrams` runs a depth-first walk from every node,
emitting the label sequence at every step, up to `max_path_length = 10` nodes. Labels come from
each node's `agent_id` (spaces replaced by `_`, missing values become `unknown`) and are joined
with `__`:

```text
graph:  A -> B -> C
paths:  "A", "A__B", "A__B__C", "B", "B__C", "C"
```

All of a session's paths are then joined by spaces into one document string.

**Step 2 — vectorise.** `CountVectorizer` with `token_pattern=r"(?u)\b\w[\w-]*\b"` builds a
vocabulary of every path observed anywhere in the group and counts occurrences per session. The
custom token pattern keeps hyphenated agent identifiers intact instead of splitting them; `__` is
made of word characters, so a whole path stays a single token.

**Step 3 — score.** The resulting count matrix goes into the model exactly like any other feature
matrix.

The consequence of using paths rather than edges: a session is anomalous when it contains a
*sequence* of steps nobody else took. Sharing every individual edge with the rest of the group but
chaining them in a novel order is still enough to be flagged.

Guards: an empty vocabulary (all graphs empty) means all sessions are inliers; a single graph is
reported as an inlier without fitting; identical count vectors across the group also short-circuit
to all inliers.

> **Warning:** Cyclic execution graphs are expensive
    The walk keeps no visited set, so it does not stop at cycles — it is bounded only by
    `max_path_length`. A graph with a loop generates every repetition of that loop up to depth 10,
    and a densely connected graph generates a combinatorial number of paths. Sessions whose
    execution graphs contain retry loops are where this layer gets slow.

### Metric layer

`MetricAnomalyDetector` (`metric_detector.py`). Each metric name is handled independently, as a
one-dimensional problem: values are collected across the group, reshaped to `(n_sessions, 1)`, and
scored.

Before fitting, values that are non-numeric, `NaN` or infinite are dropped while their original
positions are remembered, so the surviving labels still map back to the right sessions.

Three explicit guards return "everything is an inlier" rather than a model result:

| Condition | Why |
|---|---|
| Fewer than 2 valid values | Nothing to compare against |
| All values identical (`n_unique == 1`) | Zero variance, so there is no notion of distance |
| Model raises "covariance matrix of the support data is equal to 0" or "Found array with 0 sample(s)" | Degenerate MCD fit on near-constant data |

The same covariance-zero fallback is implemented in the text detector.

## Caveats

- **No minimum group size.** Unlike [consistency](consistency-worker.md) and
  [normal behaviour](normal-behaviour-worker.md), this worker does not skip small groups. A group
  of one produces a report listing that single session as an inlier.
- **Results are not stable across runs.** Isolation Forest seeds its trees randomly and no
  `random_state` is set, so re-analysing the same group can shift the inlier/outlier split.
- **The idempotency pre-check only runs on the database path.** Passing inline `sessions` bypasses
  `analysis_pre_check`, so reports are recomputed and re-MERGEd on every call.
- **Zero reports still counts as success.** When no layer produces a report the worker returns
  `True` without replacing `output_messages`, so run-once mode writes the *input* message back out
  unchanged rather than an `AnomalyDetectionOutputMessage`.
