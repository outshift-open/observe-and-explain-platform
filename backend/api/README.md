# OXP API

Unified DB access layer across OXP. It consolidates the fragmented data access patterns currently spread across oxp-backend, DAL, ontology-hub, and workflow components into one single library and provides an optional REST API, for use by the downstream components.

## Tech stack

- **Python 3.13+**
- **SQLAlchemy** — ORM / database toolkit (SQLite & ClickHouse backends)
- **clickhouse-connect** — native ClickHouse driver
- **FastAPI** + **Uvicorn** — async HTTP server

## Quick start

```bash
# 1. Create a virtual environment & install dependencies
uv venv
source .venv/bin/activate
uv sync
```

# 2. Run the server
```bash
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_USERNAME=oxpclickhouseuser
export CLICKHOUSE_PASSWORD=oxpclickhousepassword
export CLICKHOUSE_DATABASE=oxp
uv run dev
```

The API will be available at **http://127.0.0.1:8000**.

OpenAPI specification docs are available at **http://127.0.0.1:8000/docs**.

## Running tests

```bash
# Recreate a dedicated test environment from the project metadata
uv venv .venv_tests
source .venv_tests/bin/activate
uv sync --active --dev

# Run the test suites
python -m pytest tests/ -v
```

The `uv sync --active --dev` step installs both the main project dependencies
and the test-only dependencies declared in `pyproject.toml`, including vendored
wheel dependencies such as `mce-core`, `mce-provider-native`, and
`mce-provider-sdk`.

No additional `uv pip install` commands are required for metric compute in local
dev or CI when syncing with `--group dev`.

### Vendored wheel maintenance (important for Docker builds)

The API image build uses Docker `context: api`, so `uv.lock` cannot contain
sources outside that directory (for example `../mce/...`). Keep
`[tool.uv.sources]` and `api/uv.lock` pointing to `api/vendor/*.whl` paths.

When updating `mce-core` or MCE providers:

```bash
# From repo root
uv build mce/mce-core
uv build mce/mce-provider-native
uv build mce/mce-provider-sdk

cp mce/dist/mce_core-2.0.0rc1-py3-none-any.whl api/vendor/
cp mce/dist/mce_provider_native-0.1.0-py3-none-any.whl api/vendor/
cp mce/dist/mce_provider_sdk-0.1.0-py3-none-any.whl api/vendor/

uv lock --project ./api
```

## Docker

### Build the image

```bash
docker build -t oxp-api -f Dockerfile .
```

or use `docker compose` to build as part of the full stack:

```bash
docker compose -f deploy/docker-compose.yml --build oxp-api
```

### Run the container standalone

```bash
docker run --rm -p 8000:8000 \
  -e CLICKHOUSE_HOST=host.docker.internal \
  -e CLICKHOUSE_PORT=8123 \
  -e CLICKHOUSE_USERNAME=oxpclickhouseuser \
  -e CLICKHOUSE_PASSWORD=oxpclickhousepassword \
  -e CLICKHOUSE_DATABASE=default \
  oxp-api
```
The init script ([data/clickhouse/otel_traces.sql](data/clickhouse/otel_traces.sql)) runs automatically on first startup, creating the `oxp` database.

| Service | URL |
|---------|-----|
| OXP API | `http://localhost:8000` |
| ClickHouse HTTP | `http://localhost:8123` |
| ClickHouse TCP | `localhost:9000` |

## Test HTTP REST API

```bash
make test-rest-api
```

## Using as a Python library

Besides running as a REST server, `oxp-api` can be imported directly into any Python project as a library.

### Installation

```bash
# directly from Git
pip install git+https://github.com/cisco-eti/oxp-api.git
```

This installs the `oxp` package and all its dependencies.

### Quick example

```python
from oxp import LocalClient

with LocalClient() as client:
    apps     = client.get_application_names()
    sessions = client.get_sessions(app_name="my-app", limit=10)
```

### Specifying database credentials

`LocalClient` accepts an optional `db` argument — a **Connector** instance that
you configure with explicit credentials. When `db` is omitted, the backend is
chosen automatically through the `OXP_LOCAL` environment variable (see
[Environment-variable mode](#environment-variable-mode) below).

#### Option A — ClickHouse (via `clickhouse-connect`)

```python
from oxp import LocalClient
from oxp.connectors.clickhouse import ClickHouseConnector

db = ClickHouseConnector(
    host="clickhouse.example.com",
    port=8123,
    username="oxp_user",
    password="s3cret",
    database="oxp",
)

with LocalClient(db=db) as client:
    apps = client.get_applications()
```

#### Option B —  PostgreSQL (via SQLAlchemy)

```python
from oxp import LocalClient
from oxp.connectors.sqlalchemy import SQLAlchemyConnector

# PostgreSQL
db = SQLAlchemyConnector(url="postgresql://user:pass@host:5432/oxp")

with LocalClient(db=db) as client:
    sessions = client.list_sessions(limit=20)
```

#### Option C — Neo4j (for KG, metrics, and concepts operations)

KG, metrics, and concepts methods require a Neo4j-backed connector:

```python
from oxp import LocalClient
from oxp.connectors.neo4j import Neo4JConnector

db = Neo4JConnector(
    host="neo4j.example.com",
    port=7687,
    username="neo4j",
    password="s3cret",
    database="neo4j",
)

with LocalClient(db=db) as client:
    state  = client.get_state_by_session_id("session-abc")
    metrics = client.get_session_metrics("session-abc", hops=2)
    concepts = client.get_app_concepts("my-app")
```

#### Environment-variable mode

When you create `LocalClient()` **without** a `db` argument, the backend is
selected by the `OXP_LOCAL` environment variable:

| `OXP_LOCAL`             | Backend    | Credentials read from             |
|----------------------------|------------|-----------------------------------|
| `true` / `1` / `yes` *(default)* | SQLite     | Uses `oxp.db` in the working directory |
| Any other value            | ClickHouse | `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_USERNAME`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE` |

Neo4j settings (used by the REST server's dependency injection) are read from:

| Variable           | Default     |
|--------------------|-------------|
| `NEO4J_HOST`       | `localhost` |
| `NEO4J_PORT`       | `7687`      |
| `NEO4J_USERNAME`   | `neo4j`     |
| `NEO4J_PASSWORD`   | *(empty)*   |
| `NEO4J_DATABASE`   | `neo4j`     |

Example:

```bash
export OXP_LOCAL=false
export CLICKHOUSE_HOST=clickhouse.example.com
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_USERNAME=oxp_user
export CLICKHOUSE_PASSWORD=s3cret
export CLICKHOUSE_DATABASE=oxp
```

```python
from oxp import LocalClient

# Automatically connects to the ClickHouse instance above
client = LocalClient()
```

### Available client methods

| Domain | Method | Description |
|--------|--------|-------------|
| **Applications** | `get_application_names(...)` | List known application IDs |
| | `get_applications(...)` | Applications with agents, LLMs, cost, perf |
| | `get_application_details(...)` | Application-level monitoring data |
| | `get_application_agents(...)` | Per-agent monitoring for an app |
| **Sessions** | `get_sessions(...)` | Session/trace summaries |
| | `list_sessions(...)` | Flat session listing |
| | `get_session_agents(...)` | Agents within a session |
| | `get_session_agent_details(...)` | Detailed agent info in a session |
| | `_get_session_timeline(...)` | Waterfall span tree |
| | `get_session_spans(...)` | Span attributes for session(s) |
| **Spans** | `get_spans(...)` | Single span details |
| **KG** | `get_state_by_session_id(...)` | Session state from knowledge graph |
| | `get_embedding_by_session_id(...)` | Embedding vector for a session |
| | `get_neighbors(...)` | Similar sessions by embedding distance |
| **Metrics** | `get_session_metrics(...)` | KG metrics for a session |
| | `get_span_metrics(...)` | KG metrics for a span |
| **Concepts** | `get_app_concepts(...)` | Neurosymbolic concepts for an app |
| | `get_span_concepts(...)` | Concepts scoped to a specific span |

### Type hints & return types

All methods return **Pydantic models** (e.g. `TracesResponse`,
`ApplicationsResponse`, `SpanDetailsResponse`) defined in
`oxp.models.otel_traces`. Results are fully typed and serializable:

```python
from oxp import LocalClient

with LocalClient() as client:
    resp = client.get_applications()
    for app in resp.applications:
        print(app.applicationName, app.cost)

    # Serialize to dict / JSON
    print(resp.model_dump_json(indent=2))
```

For dependency injection or testing, type-hint against the abstract base class:

```python
from oxp import OXPAPIClient, LocalClient

def analyze(client: OXPAPIClient):
    ...

analyze(LocalClient())
```


