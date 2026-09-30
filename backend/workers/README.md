# Workers

Standalone worker packages for the OXP telemetry pipeline. Each worker is an independently deployable Python package with a CLI entry point, RabbitMQ queue mode, and Argo Workflows single-message mode.

All workers are built on the shared [`worker-base`](../worker-base/README.md) framework.

## Pipeline Overview

Sessions flow through the pipeline in stages:

```
                        ┌──────────────┐
                        │  norm-worker │  Normalise raw traces → KG
                        └──────┬───────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
       ┌──────────────┐  ┌──────────┐  (other outputs)
       │  mce-worker  │  │embedding │  Compute metrics / embeddings
       └──────┬───────┘  │ -worker  │
              │          └────┬─────┘
              │               │
              └───────┬───────┘
                      ▼
             ┌─────────────────┐
             │ grouping-worker │  Assign session to semantic group
             └────────┬────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
              ┌───────────────────────┐
              │    analysis-worker    │  Combined anomaly + consistency +
              │                       │  normal-behaviour analysis
              └───────────────────────┘

  ┌────────────────────────────┐
  │ hierarchical-grouping      │  (periodic, runs independently)
  │ -worker                    │
  └────────────────────────────┘
```

## Workers

### [norm-worker](norm-worker/README.md)
Normalises raw telemetry traces from the data lake and ingests them into the knowledge graph.

- **Input queue**: `new_session_in`
- **Output queues**: `new_session_to_mce`, `new_session_to_embedding`
- **CLI**: `norm-worker-cli`
- **Config**: via env vars / CLI flags (no config file)

```bash
norm-worker-cli --run-once --input /tmp/input.json --output /tmp/output.json
```

---

### [mce-worker](mce-worker/README.md)
Metrics Computation Engine — evaluates LLM agent sessions using configurable metric providers.

- **Input queue**: `new_session_to_mce`
- **Output queue**: `new_session_to_grouping`
- **CLI**: `mce-worker-cli`
- **Config**: `mce_config.yaml` (`--config-file`)

```bash
mce-worker-cli --run-once --config-file /tmp/mce-config.yaml \
  --input /tmp/input.json --output /tmp/mce-output.json
```

---

### [embedding-worker](embedding-worker/README.md)
Generates vector embeddings for session input/output content using a configurable embedding model.

- **Input queue**: `new_session_to_embedding`
- **Output queue**: `new_session_to_grouping`
- **CLI**: `embedding-worker-cli`
- **Config**: `--embedding-model` flag or `EMBEDDING_MODEL` env var

```bash
embedding-worker-cli --run-once --embedding-model azure/text-embedding-3-small \
  --input /tmp/input.json --output /tmp/embedding-output.json
```

---

### [grouping-worker](grouping-worker/README.md)
Assigns a session to a semantic group based on embedding similarity, then fetches all group sessions inline for downstream workers.

- **Input queue**: `new_session_to_grouping`
- **Output queue**: `new_session_to_analysis`
- **CLI**: `grouping-worker-cli`
- **Config**: `--embedding-model`, `--grouping-max-distance`

```bash
grouping-worker-cli --run-once \
  --embedding-model azure/text-embedding-3-small \
  --grouping-max-distance 0.3 \
  --input /tmp/embedding-output.json --output /tmp/grouping-output.json
```

---

### [hierarchical-grouping-worker](hierarchical-grouping-worker/README.md)
Runs periodic hierarchical grouping over existing semantic groups to build a topic tree.

- **Input queue**: `new_hierarchical_grouping_trigger`
- **Output queue**: `new_session_to_analysis`
- **CLI**: `hierarchical-grouping-worker-cli`
- **Config**: `--embedding-model`, `--max-distance`

```bash
hierarchical-grouping-worker-cli --embedding-model azure/text-embedding-3-small
```

---

### [analysis-worker](analysis-worker/README.md)
Runs anomaly detection, consistency, and normal-behaviour analysis together for each semantic session group.

- **Input queue**: `new_session_to_analysis`
- **CLI**: `analysis-worker-cli`
- **Config**: optional YAML configs via `--anomaly-config-file`, `--consistency-config-file`, `--normal-behaviour-config-file`

```bash
analysis-worker-cli --run-once \
  --embedding-model azure/text-embedding-3-small \
  --anomaly-config-file /tmp/anomaly-detection-config.yaml \
  --consistency-config-file /tmp/consistency-config.yaml \
  --normal-behaviour-config-file /tmp/normal-behaviour-config.yaml \
  --input /tmp/grouping-output.json --output /tmp/analysis-output.json
```

---

## Common CLI Flags

All workers share these flags:

| Flag | Description |
|------|-------------|
| `--run-once` | Single-message mode (no RabbitMQ required) |
| `--input` | Input JSON file path (run-once mode) |
| `--output` | Output JSON file path (run-once mode) |
| `--test` | Print `I'm Alive` and exit (liveness probe) |
| `--debug` | Enable debug logging |
| `--rabbitmq-url` | RabbitMQ connection URL |
| `--neo4j-uri` | Neo4j Bolt URI |
| `--neo4j-user` | Neo4j username |
| `--neo4j-password` | Neo4j password |
| `--neo4j-database` | Neo4j database name |
| `--max-sessions` | Max messages to process (`-1` = unlimited) |

## Build & Run with uv

All workers are standalone Python packages. Use [`uv`](https://docs.astral.sh/uv/) to build and run them from the monorepo root.

### Build a worker

```bash
# Build a wheel for a specific worker (run from monorepo root)
uv build workers/<worker-name>

# Example
uv build workers/norm-worker
```

The built wheel is placed in `workers/<worker-name>/dist/`.

### Install & run a worker

```bash
# Sync dependencies and run the CLI directly (no explicit install needed)
uv run --directory workers/<worker-name> <worker-cli> [flags]

# Examples
uv run --directory workers/norm-worker norm-worker-cli --test
uv run --directory workers/mce-worker mce-worker-cli --test
uv run --directory workers/embedding-worker embedding-worker-cli --test
uv run --directory workers/grouping-worker grouping-worker-cli --test
uv run --directory workers/hierarchical-grouping-worker hierarchical-grouping-worker-cli --test
uv run --directory workers/consistency-worker consistency-worker-cli --test
uv run --directory workers/anomaly-detection-worker anomaly-detection-worker-cli --test
uv run --directory workers/normal-behaviour-worker normal-behaviour-worker-cli --test
```

### Install a worker into an existing environment

```bash
uv pip install workers/<worker-name>
# or directly from source
uv pip install -e workers/<worker-name>
```


## Development

```bash
# Run tests for a specific worker
uv run --package <worker-name> --extra dev pytest workers/<worker>/tests/ -v

# Run tests for all workers
for w in workers/*/; do
  uv run --package "$(basename $w)" --extra dev pytest "$w/tests/" -v
done
```
