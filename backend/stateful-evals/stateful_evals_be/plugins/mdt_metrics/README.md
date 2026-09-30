# MDT Metrics Plugin

`mdt-metrics` is a focused metrics plugin for stateful-evals style scoring.

It provides namespaced metric IDs so users can request MDT metrics explicitly:

- `mdt.Groundedness`
- `mdt.IntentRecognitionAccuracy`
- `mdt.ResponseRelevance`

The plugin registers metric entry points as `Groundedness`, `IntentRecognitionAccuracy`, and `ResponseRelevance`,
so `mdt.<MetricName>` works with MCE's dotted-name metric resolution.

## Installation

```bash
uv pip install ./plugins/mdt_metrics
```

Or, once published:

```bash
pip install mdt-metrics
```

## Usage

### Metric name strings

```json
{
  "metrics": [
    "mdt.Groundedness",
    "mdt.IntentRecognitionAccuracy",
    "mdt.ResponseRelevance"
  ]
}
```

### Python imports

```python
import mdt_metrics as mdt

metrics = [
    mdt.Groundedness,
    mdt.IntentRecognitionAccuracy,
    mdt.ResponseRelevance,
]
```
