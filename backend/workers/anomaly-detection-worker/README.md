# Anomaly Detection Worker

Standalone worker that detects anomalies (outlier sessions) within a semantic group.

## Usage

### Run-once mode (Argo Workflows compatible)
```bash
anomaly-detection-worker-cli \
  --run-once \
  --config-file /tmp/anomaly-detection-config.yaml \
  --input /tmp/input-message.json \
  --output /tmp/anomaly-detection-output-message.json
```

### Queue mode
```bash
anomaly-detection-worker-cli \
  --embedding-model azure/text-embedding-3-small \
  --config-file /tmp/anomaly-detection-config.yaml
```

## Config file format

```yaml
text:
  model_name: "isolation_forest"
graph:
  model_name: "isolation_forest"
metric:
  model_name: "elliptic_envelop"
```

## Input message

```json
{
  "session_id": "...",
  "group_id": "...",
  "group_hash": "...",
  "sessions": [...]
}
```

## Output message

```json
{
  "session_id": "...",
  "group_id": "...",
  "sessions": [...],
  "anomalies": [
    {
      "layer": "text",
      "reason": "...",
      "inlier_sessions": [...],
      "outlier_sessions": [...],
      "scores": [...],
      "threshold": 0.5,
      "metadata": {}
    }
  ]
}
```

## Build & Run

```bash
# Build a wheel (run from the monorepo root)
uv build workers/anomaly-detection-worker

# Run the CLI (syncs dependencies automatically)
uv run --directory workers/anomaly-detection-worker anomaly-detection-worker-cli --test
```
