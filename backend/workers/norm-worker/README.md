# norm-worker

Normalization worker that converts telemetry sessions into a Knowledge Graph using [`mas-library-kg`](../../norm/README.md).

Built on the reusable [worker-base](../../worker-base/README.md) framework.

## Pipeline

```
RabbitMQ input queue
        ↓
NormWorker (extends BaseWorker)
        ↓
_fetch_spans()              — direct oxp LocalClient.get_session_spans() by session_id
        ↓
_inject_mas_boundaries()    — maps ioa_observe / traceloop attrs → mas.* attrs
        ↓
convert_spans_to_events()   — OTel spans → events list   [mas-library-kg]
        ↓
_patch_events()             — fills prompt, token counts, session I/O gaps
        ↓
normalize_events()          — events → annotated event list with ontology metadata
extract_graph()             — annotated events → (nodes, edges)
        ↓
_patch_kg_nodes()           — injects inputQuery / finalResponse on Session nodes
        ↓
denormalize()               — stamps appId, sessionId, source on every node/edge
        ↓
Neo4j (bolt)
        ↓
RabbitMQ output queues
```

## Dependencies

```
norm-worker
├── mas-library-kg       OTel → events → KG normalization + Neo4j push
├── worker-base          RabbitMQ worker lifecycle and message handling
├── oxp-api           LocalClient + DAL helpers (shared API access layer)
├── oxp-ontology      TTL files for MAS ontology (optional, preferred)
├── pydantic             Data validation
├── python-dotenv        Environment configuration
├── click                CLI framework
└── aio_pika / pika      RabbitMQ client
```

## Configuration

The CLI loads `.env` from `workers/norm-worker/` directory.

### Environment variables

```env
# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=default

# Neo4j
NEO4J_HOST=localhost
NEO4J_PORT=7687
NEO4J_USER=neo4j                      # or NEO4J_USERNAME
NEO4J_PASSWORD=
NEO4J_DB_AGENT=neo4j                  # or NEO4J_DATABASE

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost/

# Worker tuning (optional)
NORM_INPUT_QUEUE=new_session_in
NORM_OUTPUT_QUEUE=new_session_to_mce,new_session_to_embedding
NORM_FEEDBACK_QUEUE=
NORM_MAX_INFLIGHT_MESSAGES=10
```

## Usage

### Worker mode (RabbitMQ)

```bash
uv run --package norm-worker norm-worker-cli

# Custom queues
uv run --package norm-worker norm-worker-cli \
  --rabbitmq-url amqp://user:pass@rabbitmq:5672/ \
  --input-queue my_input \
  --output-queue queue1 \
  --output-queue queue2 \
  --max-inflight-messages 16
```

### Run-once mode (no RabbitMQ, process a single message)

```bash
# Normalize and push to Neo4j
uv run --package norm-worker norm-worker-cli \
  --run-once \
  --input input.json \
  --output /tmp/output.json

# Dump the KG to a file instead of pushing to Neo4j
uv run --package norm-worker norm-worker-cli \
  --run-once \
  --input input.json \
  --output /tmp/output.json \
  --kg-output /tmp/kg.json

# Dump the KG to a file AND push to Neo4j
uv run --package norm-worker norm-worker-cli \
  --run-once \
  --input input.json \
  --output /tmp/output.json \
  --kg-dump /tmp/kg.json
```

### Smoke test

```bash
uv run --package norm-worker norm-worker-cli --test
# → I'm Alive
```

### Input / output message format

**`input.json`**
```json
{ "session_id": "e9815583-76e1-479b-9098-ba0c3f066bc8" }
```

**`output.json`** (written by the worker on success)
```json
{ "session_id": "e9815583-76e1-479b-9098-ba0c3f066bc8" }
```

## CLI reference

| Option | Default | Description |
|---|---|---|
| `--rabbitmq-url` | `$RABBITMQ_URL` | RabbitMQ connection URL |
| `--input-queue` | `new_session_in` | Input queue name |
| `--output-queue` | mce + embedding queues | Output queue(s), repeatable |
| `--feedback-queue` | — | Optional feedback queue |
| `--max-sessions` | `-1` (unlimited) | Stop after N sessions |
| `--max-inflight-messages` | `10` | Max concurrent sessions |
| `--debug` | `False` | Verbose logging + `/tmp/` file dumps |
| `--override` | `False` | Delete existing Neo4j data before pushing |
| `--run-once` | `False` | Single-message mode (requires `--input` + `--output`) |
| `--input` | — | Input JSON file path (run-once) |
| `--output` | — | Output JSON file path (run-once) |
| `--kg-output` | — | Dump KG as JSON to this path, skip Neo4j |
| `--kg-dump` | — | Dump KG as JSON to this path and push to Neo4j |
| `--test` | `False` | Print `I'm Alive` and exit |

## Debug output

When `--debug` is set the worker writes to `/tmp/`:

| File | Contents |
|---|---|
| `norm_worker_events_<session_id>.jsonl` | Events after `_patch_events()` |
| `norm_worker_kg_<session_id>.json` | KG before Neo4j push (when no `--kg-dump`) |

## File structure

```
norm-worker/
├── pyproject.toml
├── README.md
├── input.json                          # example input for --run-once
└── src/norm_worker/
    ├── worker.py                       # NormWorker class (extends BaseWorker)
    ├── cli.py                          # CLI entry point
    ├── queues.py                       # Queue name constants
    └── wrapper/
        ├── __init__.py
        └── norm_wrapper.py         # MasLabWrapper — full normalization pipeline
```

## Key components

| Component | File | Responsibility |
|---|---|---|
| `NormWorker` | `worker.py` | Extends `BaseWorker`, dispatches to `MasLabWrapper` |
| `MasLabWrapper` | `wrapper/norm_wrapper.py` | Fetches spans, normalizes, pushes to Neo4j |
| `cli` | `cli.py` | Canonical CLI entrypoint used by `norm-worker-cli` |
| `mas-library-kg` | `../../norm/` | OTel → events → KG pipeline + Neo4j push |

## Default queue names

| Queue | Name |
|---|---|
| Input | `new_session_in` |
| Output → MCE worker | `new_session_to_mce` |
| Output → Embedding worker | `new_session_to_embedding` |
