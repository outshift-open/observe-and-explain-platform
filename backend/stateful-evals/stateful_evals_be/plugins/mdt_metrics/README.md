# MDT Metrics Plugin

`mdt-metrics` is a focused metrics plugin for stateful-evals style scoring.

It provides the span-level metrics stateful-evals scores on a 1-5 rubric:

- `Groundedness`
- `IntentRecognition`
- `Relevancy`

The plugin registers them as MCE entry points under these names. Results are persisted by the OXP API with the
`StatefulEvals` provider, which tells them apart from MCE metrics of the same name.

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
    "Groundedness",
    "IntentRecognition",
    "Relevancy"
  ]
}
```

### Python imports

```python
import mdt_metrics as mdt

metrics = [
    mdt.Groundedness,
    mdt.IntentRecognition,
    mdt.Relevancy,
]
```
