# Hierarchical Grouping Worker

Periodic worker that (re)computes the hierarchical semantic-group structure over all of a MAS
application's sessions, and flags which groups need (re-)analysis downstream.

**Source:** [`workers/hierarchical-grouping-worker`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/workers/hierarchical-grouping-worker)

## Overview

Unlike the per-session [grouping-worker](grouping-worker.md), which assigns one freshly-ingested
session to an existing group as part of the ingestion pipeline, the hierarchical grouping worker
runs periodically over *all* sessions of an application to build and maintain the semantic-group
**hierarchy** itself — creating new groups, merging/splitting existing ones, and re-arranging the
tree as new sessions accumulate (see the [architecture overview](../architecture/overview.md)).
Both workers share the same clustering logic, `dem.grouping.SemanticGrouper`/`Hierarchy` (see the
[analysis component](../components/analysis.md)); the hierarchical worker additionally uses an
[LLM](../components/analysis.md) to name and summarize groups.

It is a **self-triggering** worker (see the [pipelines documentation](../architecture/pipelines.md)):
`HierarchicalGroupingWorker.run()` (`src/hierarchical_grouping_worker/worker.py`) starts a
background `_periodic_self_trigger()` task alongside the normal RabbitMQ consume loop. That task
sleeps for `periodic_trigger_interval_seconds` (default 600s), then publishes one
`BaseTriggerMessage` per known MAS application ID back onto its own input queue — there is no
external scheduler. The output message TTL is automatically set to 1.5x the trigger interval.

- **Self-trigger / input queue**: `new_session_to_periodic_grouping`
- **Output queue**: `new_session_to_analysis`
- **CLI**: `hierarchical-grouping-worker-cli`

On each trigger, `HierarchicalGroupingWorker.handle_message()` calls
`HierarchicalGroupingWrapper.compute_semantic_groups(application_id)` to recompute the hierarchy,
then merges that result with `get_semantic_groups_needing_analysis()` (groups whose hierarchy
changed but haven't been re-analyzed yet) and emits one `SessionGroupMessage` per group — this is
what feeds `analysis-worker` for anomaly detection, consistency, and normal-behaviour analysis.
`HierarchicalGroupingWorker` subclasses the shared [`worker-base`](../components/worker-base.md)
`BaseWorker`.

## Usage

```bash
cp .env.template .env
# edit .env with your Neo4j and LLM settings

# RabbitMQ mode (long-running, self-triggering worker)
hierarchical-grouping-worker-cli \
  --input-queue new_session_to_periodic_grouping \
  --output-queue new_session_to_analysis \
  --embedding-model azure/text-embedding-3-small

# Test liveness
hierarchical-grouping-worker-cli --test
```

### Configuration

Neo4j connection settings are resolved by the API layer (`oxp.dependencies`) from environment
variables; the worker does not expose Neo4j CLI flags.

| Env var | CLI flag | Default | Description |
|---|---|---|---|
| `RABBITMQ_URL` | `--rabbitmq-url` | unset | Full RabbitMQ connection URL |
| `HIERARCHICAL_GROUPING_INPUT_QUEUE` | `--input-queue` | `new_session_to_periodic_grouping` | Self-trigger/input queue |
| `HIERARCHICAL_GROUPING_OUTPUT_QUEUE` | `--output-queue` | `new_session_to_analysis` | Output queue(s), comma-separated |
| `HIERARCHICAL_GROUPING_FEEDBACK_QUEUE` | `--feedback-queue` | unset | Optional feedback queue |
| `PERIODIC_TRIGGER_INTERVAL_SECONDS` | `--periodic-trigger-interval-seconds` | `600` | How often the worker self-triggers a recompute; also sets output message TTL (1.5x) |
| `HIERARCHICAL_GROUPING_EMBEDDING_MODEL` | `--embedding-model` | `azure/text-embedding-3-small` | Embedding model used for clustering |
| `HIERARCHICAL_GROUPING_MAX_NEIGHBORS` | `--max-neighbors` | `10` | Max neighbours considered per session |
| `HIERARCHICAL_GROUPING_MIN_SAMPLES` | `--min-samples` | `20` | Min samples required to form a cluster |
| `HIERARCHICAL_GROUPING_MAX_DISTANCE` | `--max-distance` | `0.15` | Max cosine distance for grouping |
| `LLM_BASE_MODEL_URL_MCE` | `--llm-base-url` | unset | LLM base URL, used to name/summarize groups |
| `LLM_MODEL_NAME` | `--llm-model-name` | `gpt-4o` | LLM model identifier |
| `OPENAI_API_KEY` | `--llm-api-key` | unset | LLM API key |
| `MAX_INFLIGHT_MESSAGES` | `--max-inflight-messages` | `1` | Max app jobs processed concurrently in one worker process |

Also supported: the common worker flags `--run-once`, `--input`, `--output`, `--test`, `--debug`,
shared by all [workers](index.md).

### Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/hierarchical-grouping-worker

# Sync dependencies and run the CLI directly
uv run --directory workers/hierarchical-grouping-worker hierarchical-grouping-worker-cli --test
```

### Development

```bash
uv run --package hierarchical-grouping-worker --extra dev pytest workers/hierarchical-grouping-worker/tests/ -v
```
