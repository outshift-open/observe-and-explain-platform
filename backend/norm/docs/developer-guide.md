# norm developer guide

How to extend and maintain the reactive normalizer.

## Design goals

1. **Nothing more, nothing less** — a handler builds only the nodes/edges its
   span shape directly implies. No inference, no placeholder/"unknown"
   fabrication, no reconstructing information the span doesn't carry.
2. **Ontology-first output** — Pydantic models generated from `oxp-ontology`
   TTL, validated with `extra="forbid"` so an undeclared field is a hard
   error, not a silently-dropped one.
3. **Best-effort post-processing stays separate and idempotent** — anything
   that needs signals the SDK doesn't yet provide (call ordering, agent
   handoffs) lives in `heuristics/`, runs after every handler, and must be
   safe to re-run over a superset of the same spans without creating
   duplicates.

## Architecture

```text
spans (raw ClickHouse-shaped dicts)
  -> build_kg: dispatch each span to a handler by SpanName
  -> link_agent_handoffs / chain_capability_calls / assign_container_boundary_states
  -> (nodes, edges) as plain dicts
```

See [normalization.md](normalization.md) for the full dispatch table.

## Adding a span handler

1. Add `handlers/my_shape.py` with `handle_my_shape(span, span_attrs, registry)`.
2. Read every value straight off `span_attrs` (already `attrs(span)`) or the
   raw `span` dict (`SpanId`/`ParentSpanId`/`Timestamp`/`Duration`) — see
   `fields.py` for the shared derivations (`get_session_id`, `get_agent_id`,
   `get_start_time`, `get_duration_ms`, ...).
3. Build ontology nodes/edges via `registry.add`/`add_if_not_exists`/
   `upsert`/`add_edge` — never construct a node with a field the ontology
   doesn't declare (`extra="forbid"` will raise `pydantic.ValidationError`
   immediately if you do).
4. If the span carries its own input/output content, call
   `trajectory.add_state_pair_transition` to give it an initial/final `State`
   + `Transition` — every `ExecutionElement` needs one.
5. Wire it into `build.py`'s dispatch (`_HANDLERS` dict for an exact
   `SpanName`, or an `elif span_name.endswith(...)` branch for a suffix).
6. If a required attribute is missing, return early and build nothing — do
   not guess or fabricate a placeholder.
7. Add a test.

## Adding a post-processing heuristic

Only add one when there's a genuine signal gap the SDK doesn't cover yet
(e.g. no way to order sibling calls). Before writing one:

1. Confirm no real signal already exists — check span attributes and
   ordering fields empirically against a real trace first (see
   `capability_chain.py`'s docstring for the kind of investigation that
   ruled out `SpanId`/`ParentSpanId`/`gen_ai.task.parent.id` ordering before
   falling back to `startTime`).
2. Prefer reusing `trajectory.bridge_states_if_mismatched` (bridge two
   existing States with a synthetic `ProcessingCall` if their content
   differs) or `trajectory.adopt_boundary_states` (share an existing State
   directly, for a pure container with no content of its own) over inventing
   a new synthesis primitive.
3. Make it idempotent — running it again over the same (or a superset of
   the same) registry state must not create duplicates or reassign existing
   edges. `bridge_states_if_mismatched`'s deterministic hashed ids give you
   this for free if you build on it.
4. Never remove or reassign an existing node's own edges to "fix" a mismatch
   — bridge with a new synthetic node between them instead. Replacing an
   existing State's ownership silently discards information a future signal
   might need.
5. Wire it into `build.py`, after every handler has run, in its real
   dependency order (e.g. `assign_container_boundary_states` must run last,
   since it reads AgentCalls' own boundary State edges in their final,
   possibly-bridged form).
6. Add a test against real fixture data, not just synthetic spans — check
   the actual node/edge counts and identities, not just that something
   didn't crash.

## Picking up new ontology classes

Model generation lives in `oxp-ontology` itself
(`scripts/generate_models.py` there), not in norm. When `oxp-ontology`
releases new classes:

```bash
uv pip install -U oxp-ontology
pytest
```

Handlers wire new ontology classes explicitly; `verifier.py`'s
`_OntologyIndex` picks up new node/edge types and domain/range declarations
automatically since it derives everything from the ontology TTL at import
time.

## Testing

| Test | Purpose |
|------|---------|
| `test_validate_trace.py` | End-to-end: load -> normalize -> verify (mirrors the README quickstart), against `data/otel_traces_export.jsonl` |
| `test_normalizer.py` | `normalize()`/`Normalizer` orchestration |
| `test_pipeline_functional.py` | Full-pipeline regression guard against `tests/fixtures/noa_trip_planner.otel_export.jsonl` |
| `test_otel_io.py` | `load_otel_export`/`infer_run_id` |
| `test_compare.py` | KG regression diff (`compare_kg`) |
| `test_verifier.py` | Structural invariant checks, one per `check_*` function |
| `test_api_boundaries.py` | Guards that deleted internal modules (e.g. `norm.completeness`) stay gone |

Prefer fixture-based tests over synthetic-span mocks where the assertion
depends on real trace shape (span-name mix, timing, real attribute
combinations) — a hand-built span can accidentally assert something that's
only true because the test author, not `ioa_observe`, shaped it that way.

## Local setup

```bash
uv sync --extra dev
pytest -q
ruff check src tests
ruff format --check src tests
```

## Related docs

- [README.md](../README.md)
- [user-guide.md](user-guide.md)
- [normalization.md](normalization.md)
- [code-structure.md](code-structure.md)
