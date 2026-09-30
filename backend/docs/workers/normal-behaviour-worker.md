# Normal Behaviour Worker

Standalone normal behaviour worker: builds a description of what a *typical* session in a semantic
group looks like — an envelope for each metric, a centroid and representative example for the text
output, and a consensus or medoid execution graph — and writes a `NormalBehaviourReport` per layer.

**Source:** [`workers/normal-behaviour-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/normal-behaviour-worker)

!!! info "Relationship to the analysis worker"
    The default `docker-compose` deployment runs the combined
    [analysis worker](analysis-worker.md), which embeds this same logic alongside anomaly detection
    and consistency. This standalone worker exists for deployments that want to scale or schedule
    normal-behaviour analysis separately (for example as an Argo Workflows step).

Where [anomaly detection](anomaly-detection-worker.md) answers *which sessions are unusual*, this
worker answers *what does usual look like* — a profile you can show a user, or compare a future
session against.

## Input

`NormalBehaviourInputMessage`:

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "group_hash": "abc123",
  "sessions": [
    {
      "session_id": "session-abc",
      "metrics": {"Cost": 1.0},
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

- **Non-empty** — analysed as-is; Neo4j is never read.
- **Empty** — needs a live DB connection. The worker runs
  `analysis_pre_check(group_id, "NormalBehaviourReport", group_hash, session_id)`, loads the group
  with `get_analysis_data_for_semantic_group`, and drops the message if `session_id` is not
  actually a member of the group.

> **Warning:** Two behavioural differences from the other two workers
    - **`--embedding-model` is checked first, before `sessions`.** Anomaly detection and
      consistency only require it on the database path; here a message is dropped without an
      embedding model even when it carries inline sessions and never touches Neo4j.
    - **No hierarchical-grouping lock.** This worker does not call
      `wait_for_hierarchical_grouping_unlock()`, so it can analyse a group while the hierarchical
      grouping worker is rewriting group membership. The `group_hash` check inside
      `analysis_pre_check` is the only protection against a stale group.

## Output

**Queue output: none.** The CLI hardcodes `output_queue=[]`, so this worker is terminal.

**Graph output:** one `NormalBehaviourReport` per layer, linked from the `SemanticGroup` by
`hasNormalBehaviourReport`:

| Property | Value |
|---|---|
| `id` | `sha256(group_id + layer + metric_name)` |
| `dataType` | `text`, `graph`, or `metric` |
| `rawResult` | JSON dump of the full result object for that layer |
| `centroid` | JSON: the mean vector, median value, or consensus graph |
| `representativeSample` | JSON: the real data point closest to the centroid, or `""` |
| `representativeProcessedSample` | For text, the actual output string of that session |
| `aboutMetric` | Set on metric reports only, linking to the `Metric` node |

The distinction between `centroid` and `representativeSample` matters: the centroid is usually
synthetic (an average embedding corresponds to no real session), while the representative sample
is an actual session you can show to a user.

**File output (run-once):** `NormalBehaviourOutputMessage`, echoing the session data it analysed
plus a `normal_behaviour` array:

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "sessions": [{"session_id": "session-abc", "...": "..."}],
  "normal_behaviour": [
    {
      "normal_behaviour": {
        "centroid": 1.2,
        "std": 0.3,
        "lower": 0.6,
        "upper": 1.8,
        "representative_sample": 1.2,
        "statistic": "gaussian"
      },
      "session_ids": ["session-abc", "session-def"],
      "layer": "metric",
      "metadata": {"statistic": "gaussian", "metric": "Cost"}
    }
  ]
}
```

## Position in the pipeline

```text
grouping-worker / hierarchical-grouping-worker
        │
        └──► new_session_to_normal_behaviour ──► normal-behaviour-worker ──► Neo4j
                                                                    (NormalBehaviourReport)
```

| | |
|---|---|
| Input queue | `new_session_to_normal_behaviour` (`NB_INPUT_QUEUE`) |
| Output queue | none |
| CLI | `normal-behaviour-worker-cli` |

> **Warning:** No producer publishes to this queue in the default deployment
    In `docker-compose.yml` the grouping workers publish to `new_session_to_analysis`, which the
    combined [analysis worker](analysis-worker.md) consumes. Running this worker means either
    repointing a producer at `new_session_to_normal_behaviour` or driving it in run-once mode.

## Quick start

```bash
# Liveness check
uv run --directory workers/normal-behaviour-worker normal-behaviour-worker-cli --test
```

Queue mode:

```bash
normal-behaviour-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_normal_behaviour \
  --embedding-model azure/text-embedding-3-small
```

Run-once against a file — note that `--embedding-model` is required even with inline sessions:

```bash
normal-behaviour-worker-cli \
  --run-once \
  --embedding-model azure/text-embedding-3-small \
  --input /tmp/group.json \
  --output /tmp/normal-behaviour.json
```

`--run-once` raises a usage error unless both `--input` and `--output` are given.

Build a wheel:

```bash
uv build workers/normal-behaviour-worker
```

## Configuration

Copy `.env.template` to `.env`, or pass flags.

| Environment variable | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full connection URL |
| `NB_INPUT_QUEUE` | `--input-queue` | Input queue name |
| `NB_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `EMBEDDING_MODEL` | `--embedding-model` | Always required |
| `NB_CONFIG_FILE` | `--config-file` | YAML layer config |
| — | `--max-sessions` | Stop after N messages (`-1` = unlimited) |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DB` | _(API-managed)_ | Read by the API DAL, not by CLI flags |

The YAML config selects which layers run and which statistic each uses. Omitting it is equivalent
to:

```yaml
text:
  statistic: gaussian
graph:
  statistic: consensus
metric:
  statistic: gaussian
```

The graph layer accepts two extra keys:

```yaml
graph:
  statistic: consensus
  majority_threshold: 0.5    # fraction of graphs an edge must appear in
  get_closest_sample: false  # skip the expensive nearest-real-graph search
```

An empty layer entry falls back to that layer's default; a layer left out of the file entirely is
skipped.

## Methodology

Source: [`dem/src/dem/normal_behaviour/`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/dem/src/dem/normal_behaviour).

Every layer produces the same conceptual triple:

```text
   sessions in the group
        │
        ├─ centroid               ──► the middle of the group
        ├─ envelope               ──► the region counted as "normal"
        └─ representative sample  ──► the real session closest to the centroid
```

What differs per layer is the geometry: metrics live on a line, embeddings in a high-dimensional
vector space, graphs in a space with no coordinates at all.

### Metric layer

`MetricNormalBehaviour` (`normal_metric.py`) works on one metric at a time, over the group's
values for it. Three statistics are available.

#### `gaussian` (default)

Assumes the values are roughly normal and takes a `k`-sigma band, with `k = 2.0`:

```text
centroid = mean(values)
std      = standard_deviation(values)
lower    = centroid - 2.0 * std
upper    = centroid + 2.0 * std
```

For a truly normal distribution this covers about 95% of values. It is cheap and interpretable but
it is dragged around by outliers, and metrics like latency or cost are usually right-skewed rather
than normal — which is what the next option is for.

#### `quantiles`

Distribution-free: read the bounds straight off the empirical distribution.

```text
lower    = 5th percentile
upper    = 95th percentile
centroid = median
```

The centroid is the **median** rather than the mean, so a single extreme session cannot move it.
Prefer this for skewed or heavy-tailed metrics.

#### `var_based`

A narrower one-sigma band, with mean, median and variance all reported:

```text
centroid = mean(values)
lower    = centroid - std
upper    = centroid + std
```

In all three cases `representative_sample` is set to the centroid. Because metrics are scalars the
centroid is itself a valid metric value, so no nearest-real-point search is needed. The `statistic`
field on the result is overwritten with the configured name (`gaussian`, `quantiles`,
`var_based`), so the internal detail of which `k` or which quantiles were used does not survive
into the report.

### Text layer

`TextNormalBehaviour` (`normal_textual.py`) works on the matrix of `output_embedding` vectors, of
shape `(n_sessions, embedding_dim)`. Six statistics are available.

`gaussian`, `quantiles` and `var_based` behave exactly as for metrics but are applied
**independently per embedding dimension**, so `upper` and `lower` are vectors describing an
axis-aligned box. This ignores correlation between dimensions, which for embeddings is
substantial — the box is a loose approximation of the true region.

`centroid` computes the mean vector only, with no envelope.

#### `density`

Fits a kernel density estimate over the embeddings and treats the low-density tail as abnormal:

```text
KernelDensity(kernel="gaussian", bandwidth=1.0)
log_dens  = kde.score_samples(embeddings)
threshold = quantile(log_dens, 1 - 0.95)      # the 5th percentile of log-density
```

A session is normal when its log-density is above the threshold, so the "normal" region follows the
actual shape of the data instead of a box — it handles multi-modal groups, where sessions cluster
around two or three distinct kinds of output, which the Gaussian box cannot. The threshold is
stored under `other_info["density_threshold"]`.

The fixed `bandwidth=1.0` is the thing to watch: for high-dimensional normalised embeddings, where
typical distances are small, this heavily over-smooths and the estimate flattens out.

#### `ellipse`

The correlation-aware version of the Gaussian box. It estimates the full covariance matrix and
uses squared Mahalanobis distance with a chi-squared cutoff:

```text
d(x)      = (x - mu)^T * Sigma^-1 * (x - mu)
threshold = chi2.ppf(0.95, df = n_dimensions)
normal    <=>  d(x) <= threshold
```

Under a multivariate normal assumption, `d(x)` follows a chi-squared distribution with `n_dim`
degrees of freedom, so the cutoff is a genuine 95% confidence ellipsoid rather than a per-axis
approximation.

> **Note:** The ellipse parameters are not persisted
    `_calculate_confidence_ellipse` passes `covariance` and `mahalanobis_threshold` into
    `NormalBehaviourResultText`, but neither is a declared field on that model, so Pydantic drops
    them. The report keeps the centroid and the representative sample; the ellipsoid itself cannot
    be reconstructed from what is stored. Use `density`, which stores its threshold in the declared
    `other_info` field, if you need the cutoff persisted.

#### Representative sample

Whatever the statistic, the final step is `_find_closest`, a plain nearest-neighbour search in
Euclidean distance:

```text
index = argmin over i of || embeddings[i] - centroid ||
```

`representative_sample` becomes that session's embedding and `representative_processed_sample` its
actual `output_content` — the real text that best stands in for the group. As on the metric layer,
the `statistic` field is then overwritten with the configured name, so internal labels like
`density_kde_0.95` or `confidence_ellipsoid_0.95` never reach the report.

### Graph layer

`GraphNormalBehaviour` (`normal_graph.py`). Graphs have no coordinates, so neither "mean" nor
"distance to the mean" is available directly. Two strategies are offered.

#### `consensus` (default)

Builds a synthetic graph out of the edges that most sessions agree on:

```text
for each edge e:
    count(e) = number of graphs containing e

keep e  <=>  count(e) > n_graphs * majority_threshold      # default 0.5
nodes   = endpoints of the kept edges
```

The result is the "majority route" through the system: the steps that happen on most runs, with
one-off detours stripped out. Nodes are derived from the surviving edges rather than voted on
separately, so a node that appears in every graph but never on a majority edge does not make it
into the consensus.

Because that consensus graph may not match any real session, `get_closest_sample` (default `True`)
then searches for the actual graph nearest to it by `networkx.graph_edit_distance` and stores it as
the representative sample.

#### `medoid`

Picks the real graph that is most central — the one with the smallest total distance to all others.
It builds the full pairwise edit-distance matrix and takes the row with the minimum sum:

```text
D[i][j] = graph_edit_distance(G_i, G_j)
medoid  = argmin over i of sum over j of D[i][j]
```

Graph edit distance is the minimum number of node and edge insertions, deletions and substitutions
needed to turn one graph into the other. Unlike `consensus`, the answer is always a real execution
graph, so `centroid` and `representative_sample` are the same graph; `other_info` additionally
carries the medoid's index and its distance to every other graph.

> **Warning:** Graph edit distance is expensive
    Computing it is NP-hard; `networkx` searches for an optimal edit path and has no built-in
    timeout. `medoid` needs `n * (n-1) / 2` of these, so it becomes impractical well before groups
    get large, and `consensus` with the default `get_closest_sample: true` still needs `n` of them.
    For large groups set `get_closest_sample: false` — you keep the consensus graph and lose only
    the representative sample.

## Caveats

- **At least two sessions are required.** `process_group` returns an empty list for groups of size
  0 or 1, and the worker still returns `True`, so the message is acked with no reports written.
- **The idempotency pre-check only runs on the database path.** Passing inline `sessions` bypasses
  `analysis_pre_check`, so reports are recomputed and re-MERGEd on every call.
- **Zero reports still counts as success.** When no layer produces a report the worker returns
  `True` without replacing `output_messages`, so run-once mode writes the *input* message back out
  unchanged rather than a `NormalBehaviourOutputMessage`.
- **A layer is skipped silently when its data is missing.** Sessions with no `output_embedding`,
  no `execution_graph` or no `metrics` are excluded from the corresponding layer, and if that
  leaves nothing the layer produces no report at all.
