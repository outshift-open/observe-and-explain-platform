# Code structure

`norm` is split into the OTel/`ioa_observe`-specific layer and a format-agnostic
core.

## `norm.ioa_observe` (OTel span -> KG)

| Module | Role |
|--------|------|
| `otel_io.py` | `load_otel_export` (ClickHouse JSONL) and `infer_run_id` — both operate on raw span dicts directly, no intermediate shape |
| `fields.py` | Span field derivation (`attrs`, `get_session_id`, `get_agent_id`, `get_start_time`, `get_duration_ms`, ...) — every value is read straight off a span's own `SpanAttributes` |
| `registry.py` | Generic `(type, id)`-keyed node/edge store (`add`, `upsert`, `add_if_not_exists`, `add_edge`, `find`, `edge_target`, `edge_source`, `edges_from`, `all_of`) — no domain knowledge of its own |
| `trajectory.py` | `add_state_pair_transition` (fresh State pair + Transition for one ExecutionElement), `bridge_states_if_mismatched` (synthesize a `ProcessingCall` bridge between two States only if their content differs), `adopt_boundary_states` (share an existing State directly, for pure containers) |
| `build.py` | `build_kg(spans)` — dispatches each span to a handler by `SpanName`, then runs the post-processing heuristics |
| `handlers/` | One handler per `SpanName` shape (see [normalization.md](normalization.md)) |
| `heuristics/` | Best-effort post-processing passes that need the full span/KG picture (see [normalization.md](normalization.md)) |

## Format-agnostic core

| Module | Role |
|--------|------|
| `normalizer.py` | `normalize()`, `Normalizer` (thin file-loading wrapper), `dump_jsonld()` |
| `ontology.py` | Resolves ontology TTL/SHACL shape paths from the installed `oxp-ontology` package — no vendored TTL copies |
| `verifier.py` | Structural checks (`check_unknown_node_types`, `check_unknown_edge_types`, `check_edge_domain_range`, `check_orphaned_edges`), SHACL (`run_shacl_validation`), `nodes_edges_to_jsonld`, `verify_kg()` |
| `compare.py` | KG structural regression diff (`compare_kg`, `read_kg_json`/`write_kg_json`) — not currently wired into norm-worker or any other caller; a standalone utility for comparing two KG documents |

Ontology node/edge models (`oxp_ontology.models.nodes`/`.edges`) live in the
external `oxp-ontology` package, generated from its own TTL files — norm only
imports and consumes them. `oxp_ontology.models.base.KGBase` uses
`extra="forbid"`, so constructing a node/edge with an undeclared field raises
`pydantic.ValidationError` immediately.

## Worker integration

`workers/norm-worker` depends on `norm[graph]` and calls:

```python
from norm import normalize

nodes, edges = normalize(raw_span_dicts)
```

Fetching spans from oxp-api and adapting oxp-api's `SpanMetadataItem` rows to
the raw span-dict shape `normalize()` expects is norm-worker's own job (see
`norm_worker.wrapper.norm_wrapper._to_otel_span_dict`), not something norm
provides — oxp-api's `SpanMetadataItem` is itself sourced from the same
ClickHouse `otel_traces` columns as `load_otel_export`, so the mapping is a
straight field rename with no reformatting.
