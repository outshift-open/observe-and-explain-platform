# Intelligence Worker

Standalone worker that executes intelligence catalog templates against the knowledge graph and ingests the resulting insights.

Built on the reusable worker-base framework.

## Overview

The Intelligence Worker:
- Listens for application-level trigger messages
- Loads insight templates from the intelligence catalog
- Executes each template query against Neo4j
- Builds and ingests insight nodes into the knowledge graph

## Running the Worker

```bash
intelligence-worker-cli \
  --rabbitmq-url amqp://<user>:<password>@rabbitmq:5672/ \
  --input-queue new_session_to_intelligence \
  --catalog-root intelligence-catalog
```

RabbitMQ can be configured with either a full `RABBITMQ_URL`, or split env vars: `RABBITMQ_HOST`/`RABBITMQ_PORT` plus required `RABBITMQ_USER` and `RABBITMQ_PASSWORD` and optional `RABBITMQ_VHOST`.

Run-once mode:

```bash
intelligence-worker-cli \
  --run-once \
  --input /tmp/input.json \
  --output /tmp/output.json \
  --catalog-root intelligence-catalog
```
