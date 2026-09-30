# OXP API — Manual Testing Guide

This guide covers all endpoints added in PR #33 (`feat/provider-interfaces`).
Run the commands below to validate the implementation end-to-end.

## Prerequisites

### Start the API

```bash
cd oxp-api
uvicorn oxp.api:app --host 0.0.0.0 --port 8001 --log-level info
```

> **Neo4j** is required for `GET /metrics/sessions/{id}`, `POST /kg/query`, and `POST /kg/neighbors`.
> Most other endpoints work without it (catalog, compute, timeseries read from MCE registry + SQLite).

### Base URL

```
http://localhost:8001/api/v1
```

### Test session ID

The examples below use a real session ingested into the local dev Neo4j instance:

```
SESSION_ID=76bc0800-8f02-416a-9ff3-f172e0ad68c2
```

---

## 1. Health check

```bash
curl -s http://localhost:8001/api/v1/healthz | python3 -m json.tool
```

**Expected response** (`200 OK`):

```json
{
  "status": "ok"
}
```

---

## 2. Metrics catalog

### 2.1 Full catalog

```bash
curl -s http://localhost:8001/api/v1/metrics/catalog | python3 -m json.tool
```

**Expected response** (`200 OK`):

```json
{
  "total": 43,
  "metrics": [
    {
      "metric_id": "ResponseCompleteness",
      "provider": "Native",
      "scope": "Session",
      "target_types": ["mas:Session"],
      "description": "Evaluates how complete the responses are in addressing user queries."
    },
    {
      "metric_id": "CyclesCount",
      "provider": "Native",
      "scope": "Session",
      "target_types": ["mas:Session"],
      "description": "..."
    }
    // ... 41 more
  ]
}
```

> The catalog is built at startup from the MCE metric registry (`mce-core`).
> It currently lists **43 metrics** across 5 providers:
> `Native`, `DeepEval`, `Ragas`, `Opik`, `SDK`.

### 2.2 Catalog filtered by scope

Available scopes: `Session`, `ExecutionElement` (case-sensitive).

```bash
curl -s "http://localhost:8001/api/v1/metrics/catalog/Session" | python3 -m json.tool
```

**Expected response** (`200 OK`):

```json
{
  "total": 23,
  "metrics": [
    { "metric_id": "ResponseCompleteness", "provider": "Native", "scope": "Session", "target_types": ["mas:Session"], "description": "..." },
    { "metric_id": "CyclesCount", "provider": "Native", "scope": "Session", "target_types": ["mas:Session"], "description": "..." }
    // ...
  ]
}
```

```bash
curl -s "http://localhost:8001/api/v1/metrics/catalog/ExecutionElement" | python3 -m json.tool
```

**Expected response**: `{"total": 20, "metrics": [...]}`

> ⚠️ The scope filter is **case-sensitive** — `session` (lowercase) returns `{"total": 0}`.

---

## 3. Metrics info

```bash
curl -s http://localhost:8001/api/v1/metrics/info | python3 -m json.tool
```

**Expected response** (`200 OK`) after a fresh server start:

```json
{
  "subsystem": "metrics",
  "total_metrics": 43,
  "scopes": ["ExecutionElement", "Session"],
  "providers": ["DeepEval", "Native", "Opik", "Ragas", "SDK"],
  "metrics": [
    { "metric_id": "ResponseCompleteness", "scope": "Session", "provider": "Native" },
    { "metric_id": "CyclesCount", "scope": "Session", "provider": "Native" }
    // ...
  ]
}
```

> If the server was started before this PR was deployed, this endpoint may return the legacy stub
> `"Hello! This is the METRICS endpoint."` — restart the server to pick up the new code.

---

## 4. Compute metrics

Compute one or more metrics for a batch of sessions.
Results are returned inline; Neo4j is **not** required.

### 4.1 Single metric

```bash
curl -s -X POST http://localhost:8001/api/v1/metrics/compute \
  -H "Content-Type: application/json" \
  -d '{
    "session_ids": ["76bc0800-8f02-416a-9ff3-f172e0ad68c2"],
    "metric_ids": ["CyclesCount"]
  }' | python3 -m json.tool
```

**Expected response** (`200 OK`):

```json
{
  "total_sessions": 1,
  "computed": 1,
  "failed": 0,
  "errors": [],
  "results": [
    {
      "session_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "metric_id": "CyclesCount",
      "value": 0,
      "resource_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "error": null,
      "reasoning": "Count of contiguous cycles in agent and tool interactions"
    }
  ]
}
```

### 4.2 Multiple metrics

```bash
curl -s -X POST http://localhost:8001/api/v1/metrics/compute \
  -H "Content-Type: application/json" \
  -d '{
    "session_ids": ["76bc0800-8f02-416a-9ff3-f172e0ad68c2"],
    "metric_ids": ["CyclesCount", "AgentToToolInteractions", "AgentToAgentInteractions"]
  }' | python3 -m json.tool
```

**Expected response**:

```json
{
  "total_sessions": 1,
  "computed": 1,
  "failed": 0,
  "errors": [],
  "results": [
    {
      "session_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "metric_id": "AgentToAgentInteractions",
      "value": 0,
      "resource_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "error": null,
      "reasoning": ""
    },
    {
      "session_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "metric_id": "CyclesCount",
      "value": 0,
      "resource_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "error": null,
      "reasoning": "Count of contiguous cycles in agent and tool interactions"
    },
    {
      "session_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "metric_id": "AgentToToolInteractions",
      "value": 0,
      "resource_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
      "error": null,
      "reasoning": ""
    }
  ]
}
```

### 4.3 All metrics (no `metric_ids` filter)

```bash
curl -s -X POST http://localhost:8001/api/v1/metrics/compute \
  -H "Content-Type: application/json" \
  -d '{"session_ids": ["76bc0800-8f02-416a-9ff3-f172e0ad68c2"]}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'computed={d[\"computed\"]} metrics for {d[\"total_sessions\"]} sessions, {len(d[\"results\"])} result rows')"
```

**Expected output**: `computed=1 metrics for 1 sessions, 43 result rows`

> `computed` counts sessions, not individual results. One session + 43 metrics = 43 rows.

### 4.4 Request schema

| Field | Type | Required | Description |
|---|---|---|---|
| `session_ids` | `list[str]` | ✅ | One or more session UUIDs |
| `metric_ids` | `list[str]` | ❌ | If omitted, all 43 metrics are computed |
| `persist` | `bool` | ❌ | If `true`, writes results to Neo4j (requires DB) |

---

## 5. Metrics time-series

Returns aggregated metric values bucketed by time. Reads from SQLite/Neo4j — points will be empty until metrics are persisted.

### 5.1 Duration window (relative to now)

```bash
curl -s "http://localhost:8001/api/v1/metrics/timeseries?metric_id=CyclesCount&duration=7d&bucket=day" \
  | python3 -m json.tool
```

**Expected response** (`200 OK`):

```json
{
  "metric_id": "CyclesCount",
  "bucket_size": "day",
  "start": "2026-03-13T11:12:15.901038+00:00",
  "end": null,
  "points": []
}
```

### 5.2 Explicit ISO-8601 range

```bash
curl -s "http://localhost:8001/api/v1/metrics/timeseries?metric_id=Duration&start=2025-01-12T00:00:00Z&end=2025-01-13T00:00:00Z&bucket=hour" \
  | python3 -m json.tool
```

**Expected response**:

```json
{
  "metric_id": "Duration",
  "bucket_size": "hour",
  "start": "2025-01-12T00:00:00+00:00",
  "end": "2025-01-13T00:00:00+00:00",
  "points": []
}
```

### 5.3 Unix epoch range (compatible with `/applications/{id}/charts`)

```bash
curl -s "http://localhost:8001/api/v1/metrics/timeseries?metric_id=Groundedness&start_time=1736640000&end_time=1736726400&bucket=hour" \
  | python3 -m json.tool
```

### 5.4 Query parameters

| Parameter | Type | Description |
|---|---|---|
| `metric_id` | `str` | **Required.** Must be a valid MCE metric ID (see `/catalog`). |
| `bucket` | `minute\|hour\|day` | Aggregation granularity (default: `hour`). |
| `duration` | `str` | Human-readable window: `7d`, `2w`, `24h`, `1w3d6h`. |
| `start_time` | `int` | Unix epoch start (mutually exclusive with `start`/`duration`). |
| `end_time` | `int` | Unix epoch end. |
| `start` | `datetime` | ISO-8601 start (mutually exclusive with `start_time`/`duration`). |
| `end` | `datetime` | ISO-8601 end. |
| `app_name` | `str` | Filter by application name. |
| `agent_id` | `str` | Filter by agent ID. |

> **Point schema** (when data is present):  
> `{"bucket": "2026-03-19T00:00:00Z", "value": 1.23, "count": 5}`

---

## 6. Session metrics (read / write)

Requires Neo4j to be running on `localhost:7687`.

### 6.1 Read session metrics

```bash
curl -s "http://localhost:8001/api/v1/metrics/sessions/${SESSION_ID}" | python3 -m json.tool
```

**Expected response** (`200 OK`):

```json
{
  "session_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
  "metrics": [],
  "subgraph": null
}
```

> `metrics` is empty because no metrics have been persisted via `POST /metrics/compute {persist: true}` yet.

### 6.2 With subgraph expansion (hops)

```bash
curl -s "http://localhost:8001/api/v1/metrics/sessions/${SESSION_ID}?hops=2" | python3 -m json.tool
```

### 6.3 Write metrics to a session

```bash
curl -s -X POST "http://localhost:8001/api/v1/metrics/sessions/${SESSION_ID}" \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      {"name": "CyclesCount", "value": 3, "reasoning": "manual test"},
      {"name": "AgentToToolInteractions", "value": 7}
    ]
  }' | python3 -m json.tool
```

**Expected response** (`200 OK`):

```json
{
  "written": 2,
  "errors": []
}
```

---

## 7. KG node query

> **Requires Neo4j** running on `localhost:7687`. Without it, returns `503` with connection error.

```bash
curl -s -X POST http://localhost:8001/api/v1/kg/query \
  -H "Content-Type: application/json" \
  -d '{"entity_type": "Session", "limit": 5}' | python3 -m json.tool
```

**Expected response** (with Neo4j running):

```json
{
  "results": [
    {"n": {"sessionId": "...", "applicationId": "...", ...}},
    ...
  ],
  "total": 5
}
```

### Request schema

| Field | Type | Required | Description |
|---|---|---|---|
| `entity_type` | `str` | ✅ | Neo4j node label: `Session`, `LLMCall`, `ToolCall`, `Agent`, `Step` |
| `filters` | `dict` | ❌ | Exact-match property filters, e.g. `{"applicationId": "my-app"}` |
| `where_clause` | `str` | ❌ | Raw Cypher WHERE fragment (without `WHERE`), e.g. `"n.cost > 0.1"` |
| `columns` | `list[str]` | ❌ | Properties to return (default: all with `RETURN n`) |
| `order_by` | `list[str]` | ❌ | Sort fields, prefix `-` for DESC, e.g. `["-cost"]` |
| `limit` | `int` | ❌ | Max rows (default: 100, max: 10,000) |

### Examples with filters

```bash
# All LLMCall nodes with errors
curl -s -X POST http://localhost:8001/api/v1/kg/query \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "LLMCall",
    "where_clause": "n.error IS NOT NULL",
    "limit": 10
  }' | python3 -m json.tool

# Sessions for a specific app, sorted by most recent
curl -s -X POST http://localhost:8001/api/v1/kg/query \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "Session",
    "filters": {"applicationId": "Hercule-Poirot"},
    "order_by": ["-startTime"],
    "limit": 20
  }' | python3 -m json.tool
```

---

## 8. Legacy KG endpoints (pre-existing)

These endpoints predate this PR and are included here for completeness.

### Session state

```bash
curl -s "http://localhost:8001/api/v1/kg/get_state_by_session_id/${SESSION_ID}" | python3 -m json.tool
```

### Semantic neighbors

Find sessions semantically similar to a given session (embedding-based).

```bash
curl -s -X POST http://localhost:8001/api/v1/kg/neighbors \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
    "max_neighbors": 5,
    "metric_names": ["CyclesCount", "Duration"]
  }' | python3 -m json.tool
```

---

## Summary table

| Endpoint | Method | Neo4j | Description |
|---|---|---|---|
| `/healthz` | GET | ❌ | Liveness probe |
| `/metrics/catalog` | GET | ❌ | All 43 MCE metrics |
| `/metrics/catalog/{scope}` | GET | ❌ | Catalog filtered by scope (`Session`, `ExecutionElement`) |
| `/metrics/info` | GET | ❌ | Subsystem metadata (providers, scopes, total) |
| `/metrics/compute` | POST | ❌ | Compute metrics for a batch of sessions |
| `/metrics/timeseries` | GET | ✅ | Time-bucketed metric aggregation |
| `/metrics/sessions/{id}` | GET | ✅ | Read persisted metrics for a session |
| `/metrics/sessions/{id}` | POST | ✅ | Write metrics to a session |
| `/kg/query` | POST | ✅ | Generic parameterized Cypher node query |
| `/kg/neighbors` | POST | ✅ | Embedding-based session similarity search |
| `/kg/get_state_by_session_id/{id}` | GET | ✅ | Raw session state from KG |

> Endpoints marked ✅ for Neo4j return `503` or connection-refused when Neo4j is not running.
