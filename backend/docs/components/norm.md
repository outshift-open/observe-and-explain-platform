# Norm

OTel (`ioa_observe`) span → knowledge-graph normalization for the MAS platform: converts raw
telemetry into validated KG documents (`{"nodes": [...], "edges": [...]}`) that conform to
[oxp-ontology](https://outshift-open.github.io/oxp-ontology/) (namespace
`https://outshift-open.github.io/oxp-ontology/mas#`).

**Source:** [`norm`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/norm)

## Overview

Each raw OTel span (a ClickHouse `otel_traces`-shaped dict: `SpanId`, `ParentSpanId`, `SpanName`,
`SpanAttributes`, `Timestamp`, `Duration`, ...) is dispatched straight to a handler by its
`SpanName`, and every value a handler needs is read directly off that span's own `SpanAttributes`
— there is no intermediate span shape, no per-span field-inference layer, and no
placeholder/"unknown" node fabricated for data a span doesn't carry. A span whose name matches
nothing is silently skipped.

A small set of best-effort, idempotent post-processing passes then bridge or share trajectory
state across agent handoffs, sibling capability calls within one agent invocation, and container
(`MASCall`/`Session`) boundaries.

`norm` is the normalization layer run by [norm-worker](../workers/norm-worker.md) at the start of
the [ingestion pipeline](../architecture/pipelines.md).

### Code structure

`norm` is split into an OTel/`ioa_observe`-specific layer and a format-agnostic core, all under the
single installable package `src/norm` (a second, empty `src/normalization` directory in the repo is
unused legacy scaffolding — not part of the built package).

**`norm.ioa_observe` (OTel span → KG):**

| Module | Role |
|---|---|
| `otel_io.py` | `load_otel_export` (ClickHouse JSONL) and `infer_run_id` — operate on raw span dicts directly |
| `fields.py` | Span field derivation (`attrs`, `get_session_id`, `get_agent_id`, `get_start_time`, `get_duration_ms`, ...) read straight off `SpanAttributes` |
| `registry.py` | Generic `(type, id)`-keyed node/edge store (`add`, `upsert`, `add_if_not_exists`, `add_edge`, `find`, `edge_target`, `edge_source`, `edges_from`, `all_of`) — no domain knowledge of its own |
| `trajectory.py` | `add_state_pair_transition` (fresh State pair + Transition for one ExecutionElement), `bridge_states_if_mismatched` (synthesize a `ProcessingCall` bridge between two States only if their content differs), `adopt_boundary_states` (share an existing State directly, for pure containers) |
| `build.py` | `build_kg(spans)` — dispatches each span to a handler by `SpanName`, then runs the post-processing heuristics |
| `handlers/` | One handler per `SpanName` shape |
| `heuristics/` | Best-effort post-processing passes that need the full span/KG picture |

**Format-agnostic core:**

| Module | Role |
|---|---|
| `normalizer.py` | `normalize()`, `Normalizer` (thin file-loading wrapper), `dump_jsonld()` |
| `ontology.py` | Resolves ontology TTL/SHACL shape paths from the installed `oxp-ontology` package — no vendored TTL copies |
| `verifier.py` | Structural checks (`check_unknown_node_types`, `check_unknown_edge_types`, `check_edge_domain_range`, `check_orphaned_edges`), SHACL (`run_shacl_validation`), `nodes_edges_to_jsonld`, `verify_kg()` |
| `compare.py` | KG structural regression diff (`compare_kg`, `read_kg_json`/`write_kg_json`) — a standalone comparison utility, not currently wired into norm-worker |

## Public API

| Function / class | Purpose |
|---|---|
| `load_otel_export(path)` | ClickHouse JSONL → raw span dicts |
| `infer_run_id(spans)` | Session id for use as `run_id` |
| `normalize(spans)` | **Main entry** → `(nodes, edges)` |
| `verify_kg(nodes, edges, run_id)` | Structural + SHACL validation |
| `compare_kg(candidate, reference)` | Structural regression diff between two KGs |
| `dump_jsonld(nodes, edges, path)` | JSON-LD export |
| `Normalizer` | Thin file-loading wrapper around `normalize()` |

## Usage

```bash
# Install (from norm/)
uv pip install -e ".[all]"
```

```python
from pathlib import Path

from norm import dump_jsonld, infer_run_id, load_otel_export, normalize, verify_kg

trace = Path(__file__).resolve().parent / "data" / "otel_traces_export.jsonl"
spans = load_otel_export(trace)
run_id = infer_run_id(spans)

nodes, edges = normalize(spans)
report = verify_kg(nodes, edges, run_id)

dump_jsonld(nodes, edges, Path("out/kg.jsonld"))
print(f"nodes={len(nodes)} edges={len(edges)} ok={report['ok']}")
```

Or generate a KG straight from the CLI (file output, or a direct Neo4j push):

```bash
python scripts/generate_kg.py data/otel_traces_export.jsonl \
    --nodes-out /tmp/nodes.json --edges-out /tmp/edges.json
```

### Running it in the pipeline

`norm` is normally not invoked directly — it's run by the standalone
[`norm-worker`](../workers/norm-worker.md), which depends on `norm[graph]` and calls
`normalize()` on spans it fetches from [oxp-api](api.md). Adapting oxp-api's
`SpanMetadataItem` rows to the raw span-dict shape `normalize()` expects is norm-worker's own job
(a straight field rename — both are sourced from the same ClickHouse `otel_traces` columns).

## Conformance to oxp-ontology

- **Pydantic node/edge models** (`oxp_ontology.models.*`) are generated from ontology TTL by
  `oxp-ontology`'s own model generator; `norm` only consumes them (`oxp-ontology` is a base
  dependency, not vendored).
- **`KGBase` uses `extra="forbid"`** — constructing a node/edge with a field the ontology doesn't
  declare raises `pydantic.ValidationError` immediately; this is a deliberate boundary, not just
  validation strictness.
- The **verifier** (`norm.verifier`) checks node/edge vocabulary, `rdfs:domain`/`range`, orphaned
  edges, and runs SHACL against `mas-ontology.ttl` + `mas-shapes.ttl` + `mas-shapes-custom.ttl`.
- **No OTel span nodes** in the output. `CapabilityCall` nodes (`ToolCall`/`LLMCall`/
  `ProcessingCall`) and every other `ExecutionElement` carry an optional `spanId`/`parentSpanId`,
  but there is no separate span provenance model.

## Development

```bash
cd norm
uv sync --extra dev
pytest -q
ruff check src tests
ruff format --check src tests
```

See also: [user guide](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/norm/docs/user-guide.md),
[normalization pipeline](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/norm/docs/normalization.md) (dispatch table, post-processing passes), and
[developer guide](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/norm/docs/developer-guide.md) (adding a handler or heuristic).
