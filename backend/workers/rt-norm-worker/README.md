# rt-norm-worker

Standalone worker (no `worker-base`) that normalizes OTel spans and logs, one record at a time,
into the Neo4j knowledge graph. Nothing is kept between records: each is normalized against the
graph as stored (see `backend/norm/docs/events.md`).

It reads its records from one of two places.

## From files

```bash
cd backend
uv run --package rt-norm-worker rt-norm-worker-cli --input ~/claris/otel_logs.json --kind event
uv run --package rt-norm-worker rt-norm-worker-cli --input ~/claris/otel_traces.json --kind span
```

`--kind` says what the file holds: `span` (default) or `event` (OTel log records).
`--dry-run` uses a throwaway in-memory graph instead of Neo4j.

## From the OTel collector

```bash
uv run --package rt-norm-worker rt-norm-worker-cli --serve [--host 0.0.0.0] [--port 4318]
```

The worker is an OTLP/HTTP receiver: `POST /v1/traces` are normalized as spans, `POST /v1/logs`
as events. It answers `200` once every record of the request is in the graph, `5xx` if
normalization fails (the collector retries), `GET /healthz` for liveness.

Only **OTLP/JSON** is accepted (gzip is fine), so the collector's exporter must use
`encoding: json`:

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

Requests are processed one at a time, in arrival order. `rt_norm_worker/otlp.py` flattens the
nested OTLP request into the same rows the files hold (`SpanAttributes`, `LogAttributes`,
`ServiceName`, ...), so both inputs go through the same code.
