# Consistency Worker

Standalone consistency analysis worker: measures how alike the sessions inside one semantic group
are, on three layers (text, execution graph, metrics), and writes a `ConsistencyReport` per layer.

**Source:** [`workers/consistency-worker`](https://github.com/cisco-eti/oxp-lib/tree/main/workers/consistency-worker)

!!! info "Relationship to the analysis worker"
    The default `docker-compose` deployment runs the combined
    [analysis worker](analysis-worker.md), which embeds this same logic alongside anomaly detection
    and normal behaviour. This standalone worker exists for deployments that want to scale or
    schedule consistency separately (for example as an Argo Workflows step).

## Input

`ConsistencyInputMessage`:

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
| `session_id` | yes | Used for the idempotency pre-check and for the group-membership guard |
| `group_id` | yes | The `SemanticGroup` to analyse |
| `group_hash` | no | Defaults to `""`, which disables the hash guard |
| `sessions` | no | Defaults to `[]` |

`sessions` selects the data path:

- **Non-empty** — analysed as-is; Neo4j is never read.
- **Empty** — needs `--embedding-model` and a live DB connection. The worker waits for the
  hierarchical-grouping lock, runs `analysis_pre_check(group_id, "ConsistencyReport", group_hash,
  session_id)`, loads the group with `get_analysis_data_for_semantic_group`, and drops the message
  if `session_id` is not actually a member of the group.

## Output

**Queue output: none.** The CLI hardcodes `output_queue=[]`, so this worker is terminal. It still
returns `True`, which means feedback events are emitted normally and nothing is forwarded.

**Graph output:** one `ConsistencyReport` per layer, linked from the `SemanticGroup` by
`hasConsistencyReport`:

| Property | Value |
|---|---|
| `id` | `sha256(group_id + layer + metric_name)` |
| `dataType` | `text`, `graph`, or `metric` |
| `mean` | Consistency score, 0–1 |
| `confidenceInterval` | JSON `[low, high]` |
| `confidenceIndicator` | `High`, `Medium`, or `Low` |
| `metadata` | JSON, includes `statistic` and (for metric reports) `metric_name` |
| `nodeHash` | The `group_hash` |
| `aboutMetric` | Set on metric reports only, linking to the `Metric` node |

Ingestion goes through `verify_kg_object`, so a report that violates the SHACL shapes raises
`OntologyValidationError` and is not written.

**File output (run-once):** `ConsistencyOutputMessage`, which echoes the full session data it
analysed and adds a `consistency` array:

```json
{
  "session_id": "session-abc",
  "group_id": "group-xyz",
  "sessions": [{"session_id": "session-abc", "...": "..."}],
  "consistency": [
    {
      "consistency_result": {
        "min": 0,
        "max": 1,
        "mean": 0.93,
        "confidence_interval": [0.89, 0.97],
        "confidence_indicator": "High",
        "statistic": "dispersion"
      },
      "session_ids": ["session-abc", "session-def"],
      "metadata": {"statistic": "dispersion"},
      "layer": "text"
    }
  ]
}
```

## Position in the pipeline

```text
grouping-worker / hierarchical-grouping-worker
        │
        └──► new_session_to_consistency ──► consistency-worker ──► Neo4j (ConsistencyReport)
```

| | |
|---|---|
| Input queue | `new_session_to_consistency` (`CONSISTENCY_INPUT_QUEUE`) |
| Output queue | none |
| CLI | `consistency-worker-cli` |

> **Warning:** No producer publishes to this queue in the default deployment
    In `docker-compose.yml` the grouping workers publish to `new_session_to_analysis`, which the
    combined [analysis worker](analysis-worker.md) consumes. Running this worker means either
    repointing a producer at `new_session_to_consistency` or driving it in run-once mode.

Downstream, the API reads these reports back: `oxp/query_builders/ui.py` folds the per-layer means
into the group's `overallReliability` as `(sum of consistency means + completionRate) /
(number of consistency entries + 1)`, and maps `dataType` to the UI fields `TextConsistency`,
`GraphConsistency` and `MetricConsistency`.

## Quick start

```bash
# Liveness check
uv run --directory workers/consistency-worker consistency-worker-cli --test
```

Queue mode:

```bash
consistency-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_consistency \
  --embedding-model azure/text-embedding-3-small
```

Run-once against a file:

```bash
consistency-worker-cli \
  --run-once \
  --input /tmp/group.json \
  --output /tmp/consistency.json
```

`--run-once` raises a usage error unless both `--input` and `--output` are given. If the input file
contains inline `sessions`, no database or embedding model is needed.

Build a wheel:

```bash
uv build workers/consistency-worker
```

## Configuration

Copy `.env.template` to `.env`, or pass flags.

| Environment variable | CLI flag | Description |
|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | Full connection URL |
| `CONSISTENCY_INPUT_QUEUE` | `--input-queue` | Input queue name |
| `CONSISTENCY_FEEDBACK_QUEUE` | `--feedback-queue` | Optional feedback queue |
| `EMBEDDING_MODEL` | `--embedding-model` | Needed whenever `sessions` is empty |
| `CONSISTENCY_CONFIG_FILE` | `--config-file` | YAML layer config |
| — | `--max-sessions` | Stop after N messages (`-1` = unlimited) |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DB` | _(API-managed)_ | Read by the API DAL, not by CLI flags |

The YAML config selects which layers run and which statistic each uses. Omitting it is equivalent
to:

```yaml
text:
  statistic: dispersion
graph:
  statistic: average_pairwise_wl_distance
metric:
  statistic: std
```

These are also the only supported values: `graph` and `metric` each accept exactly one statistic,
and `text` also accepts `entropy` — which is [currently broken](#text-layer-entropy-alternative).
An unrecognised value raises `ValueError`. A layer left out of the file entirely is skipped.

Every layer also accepts the bootstrap parameters below:

```yaml
text:
  statistic: dispersion
  confidence_level: 95
  sample_size: 10
  N_bootstrap_samples: 2000
  N_nearest_neighbors: 100
```

## Methodology

Source: [`dem/src/dem/consistency/`](https://github.com/cisco-eti/oxp-lib/tree/main/dem/src/dem/consistency).

Every layer follows the same three-stage shape. Only the middle stage — the dispersion statistic —
differs between text, graph and metric.

```text
   group data
        │
        ├─ 1. bootstrap resampling  ──► 2000 subsamples of size 10
        │
        ├─ 2. dispersion statistic  ──► one "badness" number per subsample
        │                               (high = sessions disagree)
        │
        └─ 3. invert + normalise    ──► consistency score in [0, 1]
                                        + percentile CI + confidence indicator
```

### Stage 1 — bootstrap resampling

`Consistency._generate_bootstrap_samples` (`base.py`). Defaults:
`confidence_level=95`, `sample_size=10`, `N_bootstrap_samples=2000`, `N_nearest_neighbors=100`.

For `n` sessions, it draws counts from a uniform multinomial and expands them back into indices:

```text
counts_b ~ Multinomial(m = max(sample_size, n), p = [1/n, ..., 1/n])   for b = 1..2000
indices_b = repeat([0, 1, ..., n-1], counts_b)[:sample_size]
sample_b  = data[indices_b]
```

Graph data is kept as a Python list rather than a NumPy array, so `networkx` objects survive
resampling intact.

> **Warning:** Sampling bias when a group has more than 10 sessions
    `np.repeat` emits indices in ascending order, and the result is then truncated to the first
    `sample_size` entries. When `n <= 10` the truncation removes nothing and you get a proper
    multinomial resample. When `n > 10` it keeps only the lowest-numbered indices, so sessions late
    in the group list never enter any bootstrap sample. The statistics themselves are
    order-invariant, but the resample is not uniform over the group.

### Stage 2 — the dispersion statistic

Each stage-2 statistic returns a *badness* value: larger means the sessions in the subsample are
more different from each other.

#### Text layer — `dispersion` (default)

`TextualConsistency` (`textual_consistency.py`) operates on the sessions' `output_embedding`
vectors. It normalises each to unit length, averages them, and measures how far that mean vector
falls short of the unit sphere:

```text
u_i        = v_i / ||v_i||
mean_vec   = (1/n) * sum(u_i)
dispersion = 1 - ||mean_vec||
```

Perfectly aligned embeddings give `||mean_vec|| = 1` and dispersion `0`. Embeddings spread evenly
in all directions cancel out, giving dispersion near `1`. This is the circular-variance measure
from directional statistics; unlike pairwise cosine distance it costs `O(n)` instead of `O(n^2)`.
`max_score = 1.0`.

#### Text layer — `entropy` (alternative)

Clustering happens **once over the whole group**, not per bootstrap sample:
`SemanticGrouper(max_radius=0.15, min_cluster_size=2).cluster_embeddings_with_radius` assigns every
session to a semantic equivalence class, with sessions landing in `Unassigned` each getting a class
of their own. Each bootstrap subsample is then scored by the Shannon entropy of the class counts it
happens to contain:

```text
p_k     = count of class k in the subsample / sample_size
entropy = - sum over k of p_k * log(p_k)
```

One class gives entropy `0`; every session in its own class gives `log(sample_size)`, which is the
`max_score` used for normalisation. Unlike `dispersion`, this measures *how many distinct answers*
the group produced rather than how far apart they are, so it is insensitive to how different those
answers happen to be.

!!! danger "`entropy` does not currently work"
    `SemanticGrouper` in `dem/src/dem/grouping/grouping.py` defines only `__init__`,
    `get_cluster_hierarchy` and `compute_semantic_hierarchy` — there is no
    `cluster_embeddings_with_radius` method, so selecting `statistic: entropy` raises
    `AttributeError` at analysis time. Only `dispersion` is usable on the text layer today.

#### Graph layer — `average_pairwise_wl_distance`

`GraphConsistency` (`graph_consistency.py`) converts each session's execution graph into a
`networkx.DiGraph` (`execution_graph_to_nx_graph`) and compares them with a Weisfeiler–Lehman
kernel.

**Step 1 — WL relabelling.** Start with each node's `agent_id` as its label. Repeat 4 times: give
every node a new label formed by hashing its own label together with its sorted neighbour labels
(successors, since these graphs are directed).

```text
label_{t+1}(n) = sha256( label_t(n) + "-" + concat(sorted(label_t(m) for m in neighbours(n))) )
```

Sorting makes the label independent of neighbour ordering, so isomorphic graphs produce identical
labels. Each iteration widens the structural neighbourhood a node "knows about" by one hop, so 4
iterations capture patterns up to 4 hops out.

**Step 2 — bag of labels.** Collect the multiset of all labels — the original `agent_id` labels
plus those produced by each of the 4 iterations — into a count vector per graph. Because all five
rounds contribute, the comparison weighs both raw agent composition and multi-hop structure.

**Step 3 — distance.** Compare two graphs by cosine similarity over the union of their labels:

```text
wl_distance(G1, G2) = 1 - (c1 · c2) / (||c1|| * ||c2||)
```

Identical structures share every label and score `0`; graphs with no label in common score `1`.

**Step 4 — aggregate.** Average over all unordered pairs in the subsample:

```text
statistic = (2 / (k * (k-1))) * sum over i<j of wl_distance(G_i, G_j)
```

`max_score = 1.0`. Because a pairwise comparison needs at least two graphs, this layer shrinks
`sample_size` to the number of available graphs and returns an empty result when fewer than two
graphs exist.

#### Metric layer — `std`

`MetricConsistency` (`metric_consistency.py`) is the plain standard deviation of the metric's
values across the subsample. It is the only statistic whose scale is data-dependent, so its
`max_score` is derived from the data:

```text
statistic = std(subsample)                 # per bootstrap sample
max_score = max(values) - min(values)      # observed range over the whole group
```

If every session reports the same value the range is `0`, which would make normalisation divide by
zero; the code sets `max_score = 1.0` in that case, yielding a consistency of exactly `1.0`.

Because the normaliser is the group's own range, a metric that varies only slightly still scores
well only if its spread is small *relative to that range* — the score says nothing about the
absolute size of the variation.

### Stage 3 — inversion, confidence interval and indicator

`Consistency._format_consistency_result` (`base.py`) turns the 2000 bootstrap statistics into
the final report.

**Percentile confidence interval.** With `confidence_level = 95`:

```text
ci_low  = percentile(statistics, 2.5)
ci_high = percentile(statistics, 97.5)
mean    = average(statistics)
```

**Badness to goodness.** Everything is subtracted from `max_score`, which also reverses the
interval's endpoints:

```text
consistency_mean = max_score - mean
consistency_ci   = [max_score - ci_high, max_score - ci_low]
```

**Normalisation.** When `normalize` is on and `max_score > 0`, the mean and both endpoints are
divided by `max_score` so every layer reports on the same 0–1 scale, with `max` set to `1`. This
is what makes a text dispersion score and a metric standard deviation comparable in the UI.

**Confidence indicator.** Derived from how wide the interval is relative to the score's full range,
*before* normalisation:

```text
relative_width = (ci_high - ci_low) / max_score

relative_width < 0.05  ->  "High"
relative_width < 0.15  ->  "Medium"
otherwise              ->  "Low"
```

This reflects how stable the estimate is under resampling, not how consistent the sessions are. A
group can be very inconsistent (low `mean`) yet reliably so (`High` indicator).

## Caveats

- **At least two sessions are required.** `process_group` returns an empty list for groups of size
  0 or 1, and the worker still returns `True`, so the message is acked with no reports written.
- **Metric values are used as-is.** This worker passes whatever
  `get_analysis_data_for_semantic_group` returns straight into NumPy. The copy of the wrapper
  inside the combined [analysis worker](analysis-worker.md) additionally unwraps `{"value": ...}`
  dicts and stringified JSON via `_extract_metric_value`. If your metrics are not plain numbers,
  prefer the combined worker.
- **The idempotency pre-check only runs on the database path.** Passing inline `sessions` bypasses
  `analysis_pre_check`, so reports are recomputed and re-MERGEd on every call.
- **Zero reports still counts as success.** When no layer produces a report the worker returns
  `True` without replacing `output_messages`, so run-once mode writes the *input* message back out
  unchanged rather than a `ConsistencyOutputMessage`.
- **Ingestion failures are not fatal.** If some reports fail to attach to the group, the worker
  logs and continues; the message is still acked.
