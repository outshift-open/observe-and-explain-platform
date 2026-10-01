# norm user guide

`norm` turns `ioa_observe`/observe-sdk OTel spans into ontology-backed KG
documents and validates them against
[oxp-ontology](https://outshift-open.github.io/observe-and-explain-platform/) (namespace
`https://outshift-open.github.io/oxp-ontology/mas#`).

## Install

```bash
cd norm
uv pip install -e ".[all]"
```

Requires Python >= 3.10. `oxp-ontology` (which provides the generated
`oxp_ontology.models.*` Pydantic classes) is a base dependency — always
installed, not optional. The `[graph]` extra adds `rdflib`/`pyshacl`, needed
for `verify_kg()`'s SHACL pass; `[dev]`/`[all]` install those plus the
test/lint tooling.

## Minimal pipeline

```python
from norm import infer_run_id, load_otel_export, normalize, verify_kg

spans = load_otel_export("trace.jsonl")
run_id = infer_run_id(spans)

nodes, edges = normalize(spans)
report = verify_kg(nodes, edges, run_id)
```

`load_otel_export` reads a ClickHouse `otel_traces` JSONL export (one raw
span dict per line — `SpanId`, `ParentSpanId`, `SpanName`, `SpanAttributes`,
`Timestamp`, `Duration`, ...). `normalize` takes that same raw-dict shape
directly — there's no adapter step. See `tests/test_validate_trace.py` for a
runnable version against the bundled `data/otel_traces_export.jsonl` fixture.

Every derived value (`application_id`, `session_id`, `agent_id`, ...) is read
straight off each span's own `SpanAttributes` — there's no `run_id`/
`app_name` override to pass in; a session with no `application_id` on any
span just gets no `MAS` node.

## Where spans come from

`load_otel_export(path)` covers offline traces/CI fixtures. A live caller
(e.g. norm-worker, fetching from oxp-api) is responsible for adapting its own
span representation into the same raw-dict shape — see
`norm_worker.wrapper.norm_wrapper._to_otel_span_dict` for the reference
mapping from oxp-api's `SpanMetadataItem` (itself sourced from the same
ClickHouse columns, so it's a straight field rename, no reformatting).

## What `normalize()` builds

See [normalization.md](normalization.md) for the full dispatch table and
post-processing passes. In short: each span is dispatched to a handler by its
`SpanName` suffix (`*.agent`/`*.chat`/`*.tool`/`*.graph`) or exact name
(`session.start`/`session.end`); a span whose name matches nothing is
silently skipped. Three best-effort heuristics then bridge/share trajectory
State across agent handoffs, sibling capability calls, and container
(`MASCall`/`Session`) boundaries.

## Validation report

`verify_kg(nodes, edges, run_id)` returns:

```python
{
    "ok": True,
    "structural_checks": {
        "check_unknown_node_types": {"ok": True, "violations": []},
        "check_unknown_edge_types": {"ok": True, "violations": []},
        "check_edge_domain_range": {"ok": True, "violations": []},
        "check_orphaned_edges": {"ok": True, "violations": []},
    },
    "shacl": {"skipped": False, "ok": True, "violations": [], "warnings": []},
}
```

SHACL validation runs `mas-ontology.ttl` + `mas-shapes.ttl` +
`mas-shapes-custom.ttl` (resolved from the installed `oxp-ontology` package)
against a JSON-LD projection of the KG via `pyshacl`. It's reported as
`{"skipped": True, "reason": ...}` (never a silent pass) when `rdflib`/
`pyshacl` aren't installed. Pass `strict=True` to treat SHACL warnings as
failures too.

A known, deliberate gap: SHACL currently reports `Less than 1 values on ...
mas:executes` for every call/session node — see
[normalization.md](normalization.md#known-gap).

## Regression comparison

`norm.compare` provides a standalone structural diff between two KG
documents (not currently called from norm-worker or anywhere else in this
repo — a utility for eval/CI tooling to use directly):

```python
from norm import compare_kg, read_kg_json

ref = read_kg_json("baseline/kg.json")
cand = {"nodes": nodes, "edges": edges}
result = compare_kg(cand, ref)
assert result.passed
```

Checks agent coverage, node/edge type distribution, call nesting depth, tool
coverage, cross-agent delegation topology (via `executesAgent` — always empty
under the flat `MASCall -> AgentCall` hierarchy, since an `AgentCall` cannot
directly contain another `AgentCall`), and, in `strict` mode, an exact
element-level diff.

## Further reading

- [normalization.md](normalization.md) — dispatch table and post-processing passes
- [code-structure.md](code-structure.md) — module layout
- [developer-guide.md](developer-guide.md) — adding a handler or heuristic
