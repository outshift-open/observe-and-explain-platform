# Stateful Evals quick start

This folder shows the path from an instrumented agentic app to an evaluation
result. It uses one NOA trip planner trajectory, bundled in `data/`, so every
command runs from a fresh clone.

| File | What it does |
| --- | --- |
| [`inspect_trajectory.py`](inspect_trajectory.py) | Builds the `TrajectoryContext` for one trajectory and prints a summary. No model calls |
| [`evaluate_trajectories.py`](evaluate_trajectories.py) | Runs `evaluate_file` on trajectory files and saves each result. Paid model calls, except with `--dry-run` |
| [`data/trajectory_e7f32992.json`](data/trajectory_e7f32992.json) | The sample trajectory (Step 2) |

## Prerequisites

Install the library as described in [Stateful Evals](../README.md#install). The
commands below run from the repository root with `.venv-evals/bin/python`.
Evaluation also needs a judge model: `evaluate_trajectories.py` reads three
environment variables and passes them to `evaluate_file` as an `LLMJudgeConfig`.

| Variable | Meaning |
| --- | --- |
| `LLM_MODEL_NAME` | Judge model name |
| `LLM_BASE_MODEL_URL` | Base URL of an OpenAI-compatible endpoint (calls go through LiteLLM) |
| `LLM_API_KEY` | API key for that endpoint |

## Step 1: Instrument your agentic app with the observe SDK

The [observe SDK](https://github.com/agntcy/observe) (`pip install
ioa_observe_sdk`, module `ioa_observe`) records OpenTelemetry spans for your
agents and tools. This sketch follows the SDK's README and
[GETTING-STARTED.md](https://github.com/agntcy/observe/blob/main/GETTING-STARTED.md).
It was not run for this guide: Stateful Evals does not depend on the SDK.

```python
from ioa_observe.sdk import Observe
from ioa_observe.sdk.decorators import agent, tool
from ioa_observe.sdk.tracing import session_start

Observe.init("noa-trip-planner", api_endpoint="http://localhost:4318")

@tool(name="read_document")
def read_document(file_path: str) -> str: ...

@agent(name="schedule_agent", description="Answers timetable questions")
def schedule_agent(state: dict) -> dict:
    timetable = read_document("timetables/trains.txt")
    return {"messages": [...]}  # call your model with the timetable here

with session_start():
    schedule_agent({"messages": [{"role": "user", "content": "Trains to Luminos?"}]})
```

The SDK also has `workflow`, `graph`, and `task` decorators. `session_start()`
creates the session ID `<app_name>_<uuid4>` and sets it as `session.id` on the
spans that follow. Stateful Evals takes a span's kind from its name suffix
(`.agent`, `.tool`, `.chat`, ...) or `ioa_observe.span.kind`, and its name, input,
and output from `ioa_observe.entity.*` ([`span_normalization.py`](../stateful_evals_be/evaluation/span_normalization.py)).

How spans reach Stateful Evals: the SDK exports them over OTLP to `api_endpoint`.
The SDK's [collector config](https://github.com/agntcy/observe/blob/main/deploy/otel-collector-config.yaml)
receives OTLP on ports 4317 and 4318 and writes to ClickHouse. The OXP API reads
the `otel_traces` table ([schema](../../api/data/clickhouse/otel_traces.sql)), and
`evaluate_session` and the [Stateful Eval worker](../../workers/stateful-eval-worker/README.md)
fetch a session's spans in process through the API package. Without a database,
export the spans to a file and call `evaluate_file`, as `evaluate_trajectories.py` does.

## Step 2: The sample trajectory

[`data/trajectory_e7f32992.json`](data/trajectory_e7f32992.json) is one sampled trajectory.

| Property | Value |
| --- | --- |
| Format | JSON envelope (`id`, `task_id`, `reward`, ...) with a `spans` array of exported entity spans (`span_id`, `entity_type`, `input_payload`, `output_payload`, `raw_span_data`, ...) |
| Session ID | `noa-trip-planner-mas_e7f32992-5222-41eb-b9dc-72f6e21fc2d4` |
| Spans | 26, recorded with the observe SDK from a LangGraph app |
| What happens | The user asks "What's Luminos famous for?". `moderator` routes the request to `schedule_agent`, which calls `list_documents` and `read_document`; `moderator` answers |
| `reward` | 1. This is the dataset's label; `load_trajectory_file` does not pass it to the evaluator |

## Step 3: Run the scripts

```text
$ .venv-evals/bin/python stateful-evals/quickstart/inspect_trajectory.py
file:     trajectory_e7f32992.json
session:  noa-trip-planner-mas_e7f32992-5222-41eb-b9dc-72f6e21fc2d4
spans:    26 read, 24 after de-duplication
types:    other=12, llm=5, agent=4, tool=2, workflow=1
evidence: user_statement=4, tool_output=2
claims:   assertion=5, tool_result=2
coordination events: assignment=2, synthesis=1
intents:
  intent:0  fulfilled    Primary request
  intent:1  fulfilled    delegated_agent
  intent:2  fulfilled    Primary request 2
  intent:3  fulfilled    Primary request 3
final answer: Luminos is famous for its vibrant attractions centered around light and color. Here are some of the highlights:
```

`inspect_trajectory.py` loads the file with `load_trajectory_file`, as
`evaluate_file` does, and builds the context the way `evaluate_spans` does,
without judge calls or a policy override. `types` uses the library's span classes
(`task` and `graph` spans count as `other`). Only `llm` and `tool` spans are
judged, but every span updates the context. [Trajectory Context](../stateful_evals_be/evaluation/README.md)
explains evidence, claims, and intents.

`evaluate_trajectories.py` evaluates the first `-n` files in `--trajectory-dir`,
smallest first. It loads every selected file before it makes any model call.

| Option | Default | Meaning |
| --- | --- | --- |
| `--trajectory-dir` | `data/` in this folder | Folder of `trajectory_*.json` files |
| `-n`, `--limit` | `1` | Number of files to evaluate |
| `--metrics` | `groundedness,task_completion` | Trajectory metric codes (see `available_metrics()`), or `all` |
| `--policy-file` | [`noa.md`](../stateful_evals_be/policies/noa.md) | Policy text, passed as `policy_override` |
| `--output-dir` | `output/` in this folder (ignored by git) | Where each `session_result_payload` is written |
| `--dry-run` | off | Load and check the files and metric codes, then stop. No model calls |

```text
$ .venv-evals/bin/python stateful-evals/quickstart/evaluate_trajectories.py --dry-run
metrics=groundedness,task_completion policy=noa.md
would evaluate trajectory_e7f32992.json: noa-trip-planner-mas_e7f32992-5222-41eb-b9dc-72f6e21fc2d4 (26 spans)
```

Without `--dry-run`, the judge scores each judged span, audits the trajectory, and
runs the selected metrics. These are paid model calls. Each file prints its
session ID, `trajectory_score` (1 or 0; `None` with an `error`), each metric's
status (`pass`, `fail`, `not_applicable`, `unknown`), and total tokens. The full
result goes to `output/<file stem>.result.json`. To run it, set the variables in
[Prerequisites](#prerequisites) and leave out `--dry-run`.

Next: [Stateful Evals](../README.md) covers entry points, options, and results;
[Defining Evaluation Metrics](../stateful_evals_be/evaluation/trajectory_context_metrics/README.md)
shows how to write a trajectory metric.
