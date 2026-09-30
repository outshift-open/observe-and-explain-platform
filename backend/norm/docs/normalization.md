# Normalization pipeline

**Entry point:** `norm.normalize(spans)` (alias for `norm.ioa_observe.build_kg`)
&rarr; `(nodes, edges)`.

Every span is a raw dict shaped like a ClickHouse `otel_traces` row (`SpanId`,
`ParentSpanId`, `SpanName`, `SpanAttributes`, `Timestamp`, `Duration`, ...).
There is no intermediate span shape and no per-span field-inference layer:
each span is dispatched straight to a handler by its `SpanName`, and every
value a handler needs is read directly off that span's own `SpanAttributes`
(see `norm.ioa_observe.fields`). A span whose name doesn't match a known
shape is silently skipped — the pipeline never tries to account for every
row in a trace, only the ones whose shape it recognizes.

## 1. Dispatch (`build_kg`, one pass over the spans)

| `SpanName` | Handler | Produces |
|------------|---------|----------|
| `session.start` | `handle_session_start` | `Session`, `MAS` (if `application_id` present) |
| `session.end` | `handle_session_end` | Updates the existing `Session`'s `endTime`/`duration` |
| `*.graph` | `handle_graph` | Declared `MAS`/`Agent` nodes (from `gen_ai.ioa.graph`'s node list) — the one authoritative source of "declared" structural data; overwrites any undeclared placeholder another handler created for the same id |
| `*.agent` | `handle_agent` | `Agent` (undeclared placeholder if not already declared), `AgentCall`, lazily-created `Session`/`MASCall` if none exist yet, its own initial/final `State` + `Transition` (from `ioa_observe.entity.input`/`.output`) |
| `*.chat` | `handle_chat` | `LLM`, `LLMCall` (token counts, temperature, finish reason, response id), `hasLLMCall` to the owning `AgentCall` (resolved via `ioa_observe.agent.span_id`), its own State pair |
| `*.tool` | `handle_tool` | `Tool`, `ToolCall`, `hasToolCall` to the owning `AgentCall`, its own State pair |
| anything else | *(no handler)* | nothing |

A `.chat` span with neither `gen_ai.provider.name` nor `gen_ai.request.model`
produces no `LLMCall` at all (returns early) — there is no placeholder/unknown
LLM fabricated for an untraceable call. Same for `.tool` without
`ioa_observe.entity.name`.

## 2. Post-processing (`build_kg`, after every span is dispatched)

Three best-effort passes, run in this order, each over the full `Registry`
built so far:

1. **`link_agent_handoffs`** (`heuristics/handoff.py`) — for each `*.agent`
   span carrying `ioa_observe.handoff.source.span_ids` (a JSON list — one
   predecessor id normally, several on a fork/merge), resolves each named
   predecessor `AgentCall` by its `spanId` and bridges its final State
   against the successor `AgentCall`'s initial State.
2. **`chain_capability_calls`** (`heuristics/capability_chain.py`) — no SDK
   signal orders sibling `LLMCall`/`ToolCall`s within one `AgentCall` (span
   ids aren't time-ordered, `ParentSpanId` only groups a whole tool-loop
   under one container span, `gen_ai.task.parent.id` groups at
   whole-invocation granularity), so this sorts them by `startTime` as a
   deliberate, documented fallback and bridges consecutive siblings whose
   content doesn't already line up. Also bridges the owning `AgentCall`'s
   own initial/final State against its first/last child's.
3. **`assign_container_boundary_states`** (`heuristics/container_boundary_states.py`)
   — `MASCall` and `Session` have no content of their own (they're pure
   containers), so they *adopt* — reuse the same State node, not bridge with
   a synthetic one — their earliest/latest child's initial/final State. This
   is also what the ontology's `SessionInitialStateSharedShape`/
   `SessionFinalStateSharedShape` SHACL rules require.

All three share one primitive, `trajectory.bridge_states_if_mismatched`: if
two State's `content` already match, nothing is asserted; if they differ, a
synthetic `ProcessingCall` is inserted between them, reusing both existing
State nodes (never duplicating or merging them). Every call is idempotent
(a deterministic hashed id no-ops a pair that's already bridged), so running
this pipeline again over a superset of the same spans never creates
duplicates.

## Known gap

Every `ExecutionElement` is required (`ExecutionElementShape`) to carry a
generic `executes` edge alongside its specific `executesAgent`/`executesLLM`/
`executesTool`/`executesProcessing`/`executesMAS`/`executesSession` edge
(they're all `rdfs:subPropertyOf :executes` in the ontology). `build_kg` only
ever constructs the specific sub-property, so `verify_kg()`'s SHACL pass will
report `Less than 1 values on ... mas:executes` for every call/session node.
This is a deliberate, deferred scope decision, not an oversight.

## Output shape

`(nodes, edges)` are plain dicts:

- nodes: `node_type` plus the node's ontology fields (`id`, `name`,
  `sessionId`, `startTime`, `endTime`, `duration`, `spanId`, ..., depending on
  class) plus denormalized `hierarchyLevel`/`layer` (ontology `ClassVar`s,
  not Pydantic fields, so `build_kg` reads them off the class and adds them
  to the output JSON manually)
- edges: `edge_type`, `from_id`, `to_id`

`dump_jsonld()` projects these into a compact JSON-LD document using the same
MAS IRI mapping `verify_kg()`'s SHACL pass validates against
(`norm.verifier.nodes_edges_to_jsonld`).
