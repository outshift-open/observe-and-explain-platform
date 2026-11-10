# rt-norm-worker

Standalone worker (no `worker-base`) that normalizes OTel **spans** and **logs**, one record at a
time, into the Neo4j knowledge graph, and calls back the URL of every rule a log record matches.

Nothing is kept between records: each is normalized against the graph as stored. What each log
event creates is in [`backend/norm/docs/events.md`](../../norm/docs/events.md).

All commands run from `backend/`.

## Setup

Neo4j must be running, and its credentials loaded into the shell (`NEO4J_AUTH`,
`NEO4J_PASSWORD` in `backend/.env`):

```bash
cd backend
set -a; source .env; set +a
```

Not needed with `--dry-run`.

## Run

The CLI is `rt-norm-worker-cli` (or `python -m rt_norm_worker.cli`).

### From a file

```bash
# log records (events)
uv run --package rt-norm-worker rt-norm-worker-cli --input ~/claris/otel_logs.json --kind event

# spans (the default kind)
uv run --package rt-norm-worker rt-norm-worker-cli --input ~/claris/otel_traces.json --kind span
```

### Without the rules (no callbacks)

```bash
uv run --package rt-norm-worker rt-norm-worker-cli --no-rules --input ~/claris/otel_logs.json --kind event
```

### Dry run (in-memory graph, nothing written to Neo4j)

```bash
uv run --package rt-norm-worker rt-norm-worker-cli --dry-run --no-rules --input ~/claris/otel_logs.json --kind event
```

### From the OTel collector

```bash
uv run --package rt-norm-worker rt-norm-worker-cli --serve                       # 0.0.0.0:4318
uv run --package rt-norm-worker rt-norm-worker-cli --serve --host 127.0.0.1 --port 4318
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--input FILE` | `~/claris/otel_traces.json` | JSON array of spans or log records to read |
| `--kind span\|event` | `span` | what each record of the input is |
| `--rules FILE` | `rules.yaml` next to `pyproject.toml` | rules loaded into memory at startup |
| `--no-rules` | off | do not load the rules; no callbacks |
| `--serve` | off | receive records from the collector instead of reading `--input` |
| `--host`, `--port` | `0.0.0.0`, `4318` | where `--serve` listens |
| `--dry-run` | off | throwaway in-memory graph instead of Neo4j |

## Receiving from the collector (`--serve`)

The worker is an OTLP/HTTP receiver. Only **OTLP/JSON** is accepted (gzip is fine), so the
collector's exporter needs `encoding: json`:

```yaml
exporters:
  otlphttp/rt-norm:
    endpoint: http://rt-norm-worker:4318
    encoding: json
service:
  pipelines:
    traces:
      exporters: [clickhouse, otlphttp/rt-norm]
    logs:
      exporters: [clickhouse, otlphttp/rt-norm]
```

| Request | Does |
|---|---|
| `POST /v1/traces` | normalizes the spans |
| `POST /v1/logs` | normalizes the log records, then runs the rules |
| `GET /healthz` | liveness, `200` |

`200` once every record of the request is in the graph; `400` malformed JSON; `415` not JSON;
`500` normalization failed (the collector retries). Requests are processed one at a time.

```bash
# try it by hand
curl -s -X POST localhost:4318/v1/logs -H 'Content-Type: application/json' -d @logs-request.json
curl -s localhost:4318/healthz
```

## Rules and callbacks

A rule is a `name`, a `callback_url` and, for the rules that take one, a `value`. What a name
selects is built into the worker. After a log record is normalized, it is checked against every
rule; for each match the worker **POSTs** to the rule's `callback_url`:

```json
{"rule": "agent_events", "value": "researcher", "event": { "...the log record..." }}
```

Calls run in the background (5 s timeout); a failure is logged, not retried. Spans never call back.

| Rule | Matches when (on `LogAttributes`) |
|---|---|
| `all` | always |
| `tool_events` / `llm_events` | `event.name` starts with `tool.` / `llm.` |
| `tool_completed` / `llm_completed` | `event.name` is `tool.completed` / `llm.completed` |
| `mcp_traffic` | `network.protocol.name` is `mcp` |
| `agent_handoffs` | `topology.edge.kind` is `agent_handoff` and `source.agent` ≠ `target.agent` |
| `agent_events` (`value`) | `value` is `agent.name`, `source.agent` or `target.agent` |
| `service_events` (`value`) | `value` is the record's `ServiceName` |

### `rules.yaml`

See [`rules.example.yaml`](rules.example.yaml). A rule that takes a value can be listed once per value.

```yaml
rules:
  - name: all
    callback_url: https://audit.example.com/hooks/events
  - name: agent_events
    value: researcher
    callback_url: https://agents.example.com/hooks/researcher
```

### Managing the rules while `--serve` runs

Each rule has a key: its name, or `name=value`. Rules added this way live only in memory; a
restart goes back to the file.

```bash
curl -s localhost:4318/rules                                   # list
curl -s -X POST localhost:4318/rules -H 'Content-Type: application/json' \
  -d '{"name": "agent_events", "value": "planner", "callback_url": "http://localhost:9000/planner"}'
curl -s -X POST localhost:4318/rules -H 'Content-Type: application/json' \
  -d '{"rules": [{"name": "llm_events", "callback_url": "http://localhost:9000/llm"}]}'   # several
curl -s -X DELETE 'localhost:4318/rules/agent_events%3Dplanner'  # remove (key, URL-encoded)
```

## Neo4j

```bash
# wipe the graph (deletes everything!)
set -a; source .env; set +a
uv run python -I - <<'PY'
from oxp.dependencies import get_neo4j_connector
c = get_neo4j_connector()
c.execute_command("MATCH (n) DETACH DELETE n")
c.close()
PY

# count the nodes by label
uv run python -I - <<'PY'
from oxp.dependencies import get_neo4j_connector
c = get_neo4j_connector()
for r in c.execute("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS n ORDER BY n DESC"):
    print(r["l"], r["n"])
c.close()
PY
```

## Tests

```bash
uv run --package rt-norm-worker pytest workers/rt-norm-worker/tests -q   # the worker
uv run --package norm pytest norm/tests -q                               # the normalization
```

## Code

| File | What |
|---|---|
| `cli.py` | command line |
| `worker.py` | reads files; `process_record` normalizes one record, then notifies |
| `server.py` | OTLP/HTTP receiver and the `/rules` endpoints |
| `otlp.py` | flattens OTLP/JSON into the rows the files hold |
| `rules.py` | the rules in memory (`RuleSet`) and how each one matches |
| `callbacks.py` | POSTs to the callback URLs |
| `store.py` | Neo4j read/write |
