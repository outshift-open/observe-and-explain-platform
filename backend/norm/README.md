# norm

OTel span -> ontology-backed knowledge graph normalization for the MAS
platform.

`norm` converts telemetry from the observe-sdk (`ioa_observe`) into validated
KG documents (`{"nodes": [...], "edges": [...]}`) that conform to
[oxp-ontology](https://outshift-open.github.io/observe-and-explain-platform/) (namespace
`https://outshift-open.github.io/oxp-ontology/mas#`). It is the normalization
layer used by **norm-worker**.

## Design

Each raw OTel span (a ClickHouse `otel_traces`-shaped dict: `SpanId`,
`ParentSpanId`, `SpanName`, `SpanAttributes`, `Timestamp`, `Duration`, ...) is
dispatched straight to a handler by its `SpanName`, and every value a
handler needs is read directly off that span's own `SpanAttributes` — there
is no intermediate span shape, no per-span field-inference layer, and no
placeholder/"unknown" node fabricated for data a span doesn't carry. A span
whose name matches nothing is silently skipped.

A small set of best-effort, idempotent post-processing passes then bridge or
share trajectory state across agent handoffs, sibling capability calls
within one agent invocation, and container (`MASCall`/`Session`) boundaries
— see [docs/normalization.md](docs/normalization.md).

## Quick start

Install (from `norm/`):

```bash
uv pip install -e ".[all]"
```

Validate the bundled reference trace:

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

Run the pytest equivalent:

```bash
pytest tests/test_validate_trace.py -q
```

Or generate a KG straight from the CLI (file output, or a direct Neo4j push):

```bash
python scripts/generate_kg.py data/otel_traces_export.jsonl \
    --nodes-out /tmp/nodes.json --edges-out /tmp/edges.json
```

## Public API

| Function / class | Purpose |
|------------------|---------|
| `load_otel_export(path)` | ClickHouse JSONL -> raw span dicts |
| `infer_run_id(spans)` | Session id for use as `run_id` |
| `normalize(spans)` | **Main entry** -> `(nodes, edges)` |
| `verify_kg(nodes, edges, run_id)` | Structural + SHACL validation |
| `compare_kg(candidate, reference)` | Structural regression diff between two KGs |
| `dump_jsonld(nodes, edges, path)` | JSON-LD export |
| `Normalizer` | Thin file-loading wrapper around `normalize()` |

## Conformance to oxp-ontology

- **Pydantic node/edge models** (`oxp_ontology.models.*`) are generated from
  ontology TTL by `oxp-ontology`'s own `scripts/generate_models.py`; norm
  only consumes them (`oxp-ontology` is a base dependency, not vendored).
- **`KGBase` uses `extra="forbid"`** — constructing a node/edge with a field
  the ontology doesn't declare raises `pydantic.ValidationError`
  immediately; this is a deliberate boundary, not just validation
  strictness.
- **Verifier** (`norm.verifier`) checks node/edge vocabulary, rdfs:domain/
  range, orphaned edges, and runs SHACL against `mas-ontology.ttl` +
  `mas-shapes.ttl` + `mas-shapes-custom.ttl`.
- **No OTel span nodes** in the output. `CapabilityCall` nodes
  (`ToolCall`/`LLMCall`/`ProcessingCall`) and every other `ExecutionElement`
  carry an optional `spanId`/`parentSpanId`, but there is no separate span
  provenance model.

## Documentation

- [User guide](docs/user-guide.md) — inputs, `normalize()`, validation
- [Normalization pipeline](docs/normalization.md) — dispatch table, post-processing passes
- [Code structure](docs/code-structure.md) — module map
- [Developer guide](docs/developer-guide.md) — adding a handler or heuristic

## Development

```bash
cd norm
uv sync --extra dev
pytest -q
ruff check src tests
ruff format --check src tests
```
