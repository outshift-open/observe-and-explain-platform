# Stateful Evals

An in-process library that evaluates a multi-agent trajectory span by span against a policy, returning a binary pass/fail verdict plus diagnostic metrics — a cost-effective alternative to full LLM-as-judge grading of every metric independently.

**Source:** [`stateful-evals`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/stateful-evals)

## Overview

Stateful Evals (package `stateful_evals_be`) builds a `TrajectoryContext` as it reads a session's spans in start-time order: the policy and agent contracts, what the user asked for, what tools returned, what agents claimed, which requirements are still open, and how agents coordinated. Each span is judged against that accumulated state (via an LLM judge), then ingested to update the state, so later spans are judged with full knowledge of everything that came before. After the last span, a final audit produces a `trajectory_score` (fatal/minor failure classification) and, optionally, a set of diagnostic trajectory-level metrics (e.g. `groundedness`, `task_completion`) that never affect that score.

It is a pure library — callers supply spans and model access, and own scheduling/persistence. It runs the [MCE](mce.md) engine in process for metric computation and needs no database, server, or MCE URL of its own. Database sessions are read by the stateful-eval worker through the OXP API (`get_session_trajectory`) and evaluated with `evaluate_trajectory`.

### Modules

| Module | Purpose |
|---|---|
| `evaluation/` | Builds `TrajectoryContext` from spans (`trajectory_context.py`, `span_normalization.py`) and runs the final audit; `trajectory_context_metrics/` holds the pluggable diagnostic metrics and context save/load (`context_io.py`) |
| `policies/` | Built-in domain policy files (`noa.md`, `tau2_airline.md`, `tau2_retail.md`, `tau2_telecom.md`) that define what "correct" behavior looks like for a domain |
| `domain/` | Domain-specific extraction logic (e.g. agent contracts, intents) used while building the context |
| `models/` | Pydantic request/response models (`requests.py` — `TemporalMetricOptions`, etc. — and `spans.py` — `SpanRecord`) |
| `integrations/` | Converters from other span formats into the library's span shape, e.g. `oxp.py` (`oxp_span_to_otel`) for OXP snake_case spans, `files.py` for file-based loading |
| `plugins/mdt_metrics/` | A separate installable package (`mdt-metrics`) providing the built-in trajectory metric implementations |
| `scripts/` | Standalone entry points: `import_trajectories` (import a trajectory dataset into ClickHouse) |
| `data/` | Bundled example trajectory data |

## Public API

Exposed from the top-level package (`stateful_evals_be`, lazily re-exported from `stateful_evals_be.api`):

- `evaluate_spans(spans, session_id=..., llm_config=..., options=...)` — evaluate spans already in memory.
- `TemporalMetricsProcessor.evaluate_trajectory(trajectory)` — evaluate a normalized trajectory (ordered LLM, tool and agent steps with the raw text of their input and output; see `stateful_evals_be.models.trajectory`), with no OTel parsing. The library does no database access: the caller supplies the trajectory. The result carries each step's `transition_id` on its span metrics and `transition_contexts`, the context each step added.
- `evaluate_file(path, ...)` — evaluate a JSON/JSONL file of spans.
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
| `span_pass_threshold` | `0.5` | Span metrics (`Groundedness`, `IntentRecognition`, `Relevancy`) are judged on a 1-5 rubric and normalized to `(score-1)/4` (0, 0.25, 0.5, 0.75, 1). A span metric passes at or above this value and fails below it |
| `use_fatal_mode` | `True` | Fatal/minor audit with a binary trajectory score |
| `fatality_threshold` | `0.69` | Severity at or above which a failure is fatal |
| `batch_size` | `50` | Sessions evaluated concurrently by `EvaluationEngine` |

See `stateful_evals_be/models/requests.py` for the full set.

### Key results (`SessionResult`)

`trajectory_score`/`trajectory_reasoning` (binary verdict and why), `fatal_failures`/`minor_failures`, `span_metric_results` (normalized `score`, the judge's `raw_score` 1-5, and `evaluation_model`/`evaluation_*_tokens`/`evaluation_cost_usd`: the span's judge usage split evenly across the metrics judged for it, so the per-metric values sum to the span's usage), `trajectory_metrics`, `token_usage`/`cost_estimate`, and `error` (set when the run failed).

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

In the pipeline, the [stateful-eval-worker](../workers/stateful-eval-worker.md) reads a session's trajectory from the KG (OXP API `oxp.client.dal.get_session_trajectory`), calls `evaluate_trajectory`, and writes the resulting metrics and per-transition context back onto the Transition nodes.

## Development

```bash
uv pip install --python .venv-evals/bin/python pytest ruff
.venv-evals/bin/python -m pytest stateful-evals/stateful_evals_be/tests
```

Tests use mocked judges and make no paid model calls.
