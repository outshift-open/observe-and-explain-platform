# Normal Behaviour Worker

Standalone worker that performs normal behaviour analysis for session groups in Neo4j.
Reads `SessionGroupMessage` events from the `new_session_to_normal_behaviour` queue,
computes text/graph/metric normal behaviour reports, and persists results back to Neo4j.

## Usage

### Queue mode (long-running)
```bash
normal-behaviour-worker-cli \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password <password> \
  --embedding-model azure/text-embedding-3-small \
  --config-file /tmp/normal-behaviour-config.yaml
```

### Run-once mode (Argo Workflows compatible, single message)
```bash
normal-behaviour-worker-cli \
  --run-once \
  --input /tmp/input-message.json \
  --output /tmp/output-message.json \
  --config-file /tmp/normal-behaviour-config.yaml
```

### Health check
```bash
normal-behaviour-worker-cli --test
# Output: I'm Alive
```

## Config file format (YAML)

```yaml
text:
  statistic: gaussian
graph:
  statistic: consensus
  majority_threshold: 0.5
  get_closest_sample: false
metric:
  statistic: gaussian
```

## Configuration

All options can be provided via CLI flags or environment variables. See `.env.template` for the full list.

## Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/normal-behaviour-worker

# Run the CLI (syncs dependencies automatically)
uv run --directory workers/normal-behaviour-worker normal-behaviour-worker-cli --test
```
