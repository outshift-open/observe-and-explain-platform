# Stateful Evals

Stateful Evals evaluates multi-agent trajectories span by span. It builds a
`TrajectoryContext` as the spans are read, judges each span against that state,
and returns a `SessionResult` with a trajectory score, per-span results, token
usage, and optional trajectory-level metrics. It is a Python library: callers
supply spans and model access, and own scheduling and persistence.

**Related pages**

- [Trajectory Context](stateful_evals_be/evaluation/README.md): the state recorded for each trajectory
- [Defining Evaluation Metrics](stateful_evals_be/evaluation/trajectory_context_metrics/README.md): how to write and register a trajectory metric
- [Quickstart](quickstart/README.md): a small example on a bundled NOA trip planner trajectory

## Install

The library supports Python 3.11+ (the full OXP workspace needs 3.13+). From the
repository root:

```bash
uv venv .venv-evals --python 3.13
uv pip install --python .venv-evals/bin/python \
  ./stateful-evals/stateful_evals_be/plugins/mdt_metrics \
  ./stateful-evals
```

The `import` extra adds ClickHouse support for the optional trajectory importer.
Evaluation runs the Metrics Computation Engine in process; it needs no database,
server, or MCE URL.

## Quick start

```python
import json
import os
from pathlib import Path

from stateful_evals_be import (
    LLMJudgeConfig,
    TemporalMetricOptions,
    evaluate_spans,
    session_result_payload,
)

spans = [json.loads(line) for line in Path("spans.jsonl").read_text().splitlines() if line.strip()]
result = evaluate_spans(
    spans,
    session_id="example-session",
    llm_config=LLMJudgeConfig(
        LLM_MODEL_NAME=os.environ["LLM_MODEL_NAME"],
        LLM_BASE_MODEL_URL=os.environ["LLM_BASE_MODEL_URL"],
        LLM_API_KEY=os.environ["LLM_API_KEY"],
    ),
    options=TemporalMetricOptions(trajectory_metrics=["groundedness", "task_completion"]),
)
if result.error:
    raise RuntimeError(result.error)
Path("evaluation.json").write_text(json.dumps(session_result_payload(result), indent=2))
```

Keep API keys in the environment, not in source files. Model calls cost money.

## Input spans

`evaluate_spans` takes one session's spans as PascalCase OTel export records:
`SpanId`, `TraceId`, `ParentSpanId`, `Timestamp`, `SpanName`, `ServiceName`,
`SpanAttributes`, `StatusCode`, and `Duration` (nanoseconds). `Links` arrays are
kept. Use unique span IDs and sortable timestamps. Inputs are copied, not changed.

Other formats need converting first, for example OXP snake_case spans with
`integrations.oxp.oxp_span_to_otel`. The library has no built-in converter for
other trace formats; write one that produces the record shape above.

## Entry points

| Call | Use it for |
| --- | --- |
| `evaluate_spans(spans, ...)` | Spans already in memory |
| `evaluate_file(path, ...)` | A JSON file with a `spans` array, a JSON array of spans, or span JSONL |
| `evaluate_session(session_id, ...)` | A session stored in the OXP database, read through the API library |
| `EvaluationEngine(llm_config=..., options=...)` | Reusing one configuration across many trajectories |
| `available_metrics()` | Listing the registered trajectory metrics |

```python
from stateful_evals_be import EvaluationEngine, TemporalMetricOptions

engine = EvaluationEngine(llm_config=llm_config, options=TemporalMetricOptions(batch_size=4))
result = engine.evaluate_spans(spans, session_id="example-session")
summary = engine.evaluate_sessions(sessions.keys(), span_loader=sessions.__getitem__)
```

Each trajectory gets fresh state, so runs never share context or token counts.
`evaluate_session` needs the repository's API package (`./api`, Python 3.13+) and
its `CLICKHOUSE_*` settings.

## Options

`TemporalMetricOptions` fields most callers set:

| Field | Default | Meaning |
| --- | --- | --- |
| `trajectory_metrics` | `None` | Metric codes to evaluate over the trajectory context, or `["all"]`. Diagnostic only; never changes `trajectory_score` |
| `high_level_metric_suite` | `"legacy_v1"` | Metric suite used by the final audit: `legacy_v1`, `paper_v1`, or `paper_v2` |
| `use_fatal_mode` | `True` | Fatal/minor audit with a binary trajectory score |
| `fatality_threshold` | `0.69` | Severity at or above which a failure is fatal |
| `reasoning_effort` | `"low"` | Reasoning effort requested from compatible models |
| `batch_size` | `50` | Sessions evaluated concurrently by `EvaluationEngine` |
| `sampling` | `None` | Span sampling (`tail_weighted`); `None` judges every span |

See `stateful_evals_be/models/requests.py` for the rest.

## Results

`SessionResult` fields you will read most:

| Field | Contents |
| --- | --- |
| `trajectory_score`, `trajectory_reasoning` | Binary trajectory verdict and why |
| `fatal_failures`, `minor_failures` | Failures found by the audit, with span index and evidence |
| `span_metric_results` | Per-span judgments |
| `trajectory_metrics` | Results of the metrics named in `trajectory_metrics` (`status` is `pass`, `fail`, `not_applicable`, or `unknown`) |
| `token_usage`, `cost_estimate` | Model usage for the run |
| `error` | Set when the run failed; check it first |

`session_result_payload(result)` returns the JSON-ready form.

## Re-running metrics on a saved context

A saved `trajectory_context.json` can be scored again without re-judging spans:

```python
from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.trajectory_metrics import (
    evaluate_trajectory_metrics_batched,
)

context, metadata = load_trajectory_context_artifact("trajectory_context.json")
results = evaluate_trajectory_metrics_batched(context, ["all"])
```

Without a `judge` argument the metric judge reads `LLM_MODEL_NAME`,
`LLM_BASE_MODEL_URL`, and `LLM_API_KEY` from the environment.
`trajectory_context_to_payload` in the same `context_io` module writes the file.
[Trajectory Context](stateful_evals_be/evaluation/README.md#saving-and-loading)
describes the format.

## Scripts and services

- `python -m stateful_evals_be.scripts.run_session_eval` evaluates a database session (`SESSION_ID=...`)
- The [Stateful Eval worker](../workers/stateful-eval-worker/README.md) fetches spans, calls `evaluate_spans`, and persists its metrics

The standalone FastAPI server is retired. Callers that used
`POST /compute_temporal_metrics` should fetch spans themselves and call
`evaluate_spans`; `GET /metrics` becomes `available_metrics()`.

## Tests

```bash
uv pip install --python .venv-evals/bin/python pytest ruff
.venv-evals/bin/python -m pytest stateful-evals/stateful_evals_be/tests
```

Tests use mocked judges and make no paid model calls.
