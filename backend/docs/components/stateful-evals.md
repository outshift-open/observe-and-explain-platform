# Stateful Evals

An in-process library that evaluates a multi-agent trajectory span by span against a policy, returning a binary pass/fail verdict plus diagnostic metrics — a cost-effective alternative to full LLM-as-judge grading of every metric independently.

**Source:** [`stateful-evals`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/stateful-evals)

## Overview

Stateful Evals (package `stateful_evals_be`) builds a `TrajectoryContext` as it reads a session's spans in start-time order: the policy and agent contracts, what the user asked for, what tools returned, what agents claimed, which requirements are still open, and how agents coordinated. Each span is judged against that accumulated state (via an LLM judge), then ingested to update the state, so later spans are judged with full knowledge of everything that came before. After the last span, a final audit produces a `trajectory_score` (fatal/minor failure classification) and, optionally, a set of diagnostic trajectory-level metrics (e.g. `groundedness`, `task_completion`) that never affect that score.

It is a pure library — callers supply spans and model access, and own scheduling/persistence. It runs the [MCE](mce.md) engine in process for metric computation and needs no database, server, or MCE URL of its own (only `evaluate_session` needs the [`api`](api.md) package, to fetch spans from ClickHouse).

### Modules

| Module | Purpose |
|---|---|
| `evaluation/` | Builds `TrajectoryContext` from spans (`trajectory_context.py`, `span_normalization.py`) and runs the final audit; `trajectory_context_metrics/` holds the pluggable diagnostic metrics and context save/load (`context_io.py`) |
| `policies/` | Built-in domain policy files (`noa.md`, `tau2_airline.md`, `tau2_retail.md`, `tau2_telecom.md`) that define what "correct" behavior looks like for a domain |
| `domain/` | Domain-specific extraction logic (e.g. agent contracts, intents) used while building the context |
| `models/` | Pydantic request/response models (`requests.py` — `TemporalMetricOptions`, etc. — and `spans.py` — `SpanRecord`) |
| `integrations/` | Converters from other span formats into the library's span shape, e.g. `oxp.py` (`oxp_span_to_otel`) for OXP snake_case spans, `files.py` for file-based loading |
| `plugins/mdt_metrics/` | A separate installable package (`mdt-metrics`) providing the built-in trajectory metric implementations |
| `scripts/` | Standalone entry points: `run_session_eval` (evaluate a DB session), `import_trajectories` (import a trajectory dataset into ClickHouse) |
| `data/` | Bundled example trajectory data |

## Public API

Exposed from the top-level package (`stateful_evals_be`, lazily re-exported from `stateful_evals_be.api`):

- `evaluate_spans(spans, session_id=..., llm_config=..., options=...)` — evaluate spans already in memory.
- `evaluate_file(path, ...)` — evaluate a JSON/JSONL file of spans.
- `evaluate_session(session_id, ...)` — evaluate a session stored in the OXP database, read through the `api` package.
- `EvaluationEngine(llm_config=..., options=...)` — reuse one configuration across many trajectories; exposes `evaluate_spans()` and batch `evaluate_sessions()`.
- `available_metrics()` — list the registered trajectory metrics.
- `session_result_payload(result)` — convert a `SessionResult` into its JSON-ready form.
- `LLMJudgeConfig`, `TemporalMetricOptions`, `SpanRecord`, `TemporalMetricsProcessor` — supporting config/model types.

Each trajectory gets fresh state — runs never share context or token counts.

### Key options (`TemporalMetricOptions`)

| Field | Default | Meaning |
|---|---|---|
| `trajectory_metrics` | `None` | Metric codes to compute (or `["all"]`); diagnostic only, never changes `trajectory_score` |
| `high_level_metric_suite` | `"legacy_v1"` | Metric suite used by the final audit (`legacy_v1`, `paper_v1`, `paper_v2`) |
| `use_fatal_mode` | `True` | Fatal/minor audit with a binary trajectory score |
| `fatality_threshold` | `0.69` | Severity at or above which a failure is fatal |
| `batch_size` | `50` | Sessions evaluated concurrently by `EvaluationEngine` |

See `stateful_evals_be/models/requests.py` for the full set.

### Key results (`SessionResult`)

`trajectory_score`/`trajectory_reasoning` (binary verdict and why), `fatal_failures`/`minor_failures`, `span_metric_results`, `trajectory_metrics`, `token_usage`/`cost_estimate`, and `error` (set when the run failed).

## Usage

```python
from stateful_evals_be import LLMJudgeConfig, TemporalMetricOptions, evaluate_spans, session_result_payload

result = evaluate_spans(
    spans,
    session_id="example-session",
    llm_config=LLMJudgeConfig(LLM_MODEL_NAME=..., LLM_BASE_MODEL_URL=..., LLM_API_KEY=...),
    options=TemporalMetricOptions(trajectory_metrics=["groundedness", "task_completion"]),
)
```

Install from the repo root:

```bash
uv venv .venv-evals --python 3.13
uv pip install --python .venv-evals/bin/python \
  ./stateful-evals/stateful_evals_be/plugins/mdt_metrics \
  ./stateful-evals
```

A judge model is configured via `LLM_MODEL_NAME`, `LLM_BASE_MODEL_URL` (an OpenAI-compatible endpoint, called through LiteLLM), and `LLM_API_KEY`.

See the [quickstart](../../stateful-evals/quickstart/README.md) for a full walkthrough — inspecting a `TrajectoryContext` with no model calls, then running `evaluate_file` on a bundled NOA trip planner trajectory — and [Trajectory Context](../../stateful-evals/stateful_evals_be/evaluation/README.md) / [Defining Evaluation Metrics](../../stateful-evals/stateful_evals_be/evaluation/trajectory_context_metrics/README.md) for the state model and how to register a new metric.

In the pipeline, spans are read through the [stateful-eval-worker](../workers/stateful-eval-worker.md), which fetches a session's spans, calls `evaluate_spans`, and persists the resulting metrics.

## Development

```bash
uv pip install --python .venv-evals/bin/python pytest ruff
.venv-evals/bin/python -m pytest stateful-evals/stateful_evals_be/tests
```

Tests use mocked judges and make no paid model calls.
