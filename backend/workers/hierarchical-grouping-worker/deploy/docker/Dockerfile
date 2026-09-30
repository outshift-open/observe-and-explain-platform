#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

COPY pyproject.toml uv.lock /app/
COPY workers/hierarchical-grouping-worker /app/workers/hierarchical-grouping-worker
COPY worker-base /app/worker-base
COPY api /app/api
COPY dem /app/dem

RUN uv sync --package hierarchical-grouping-worker --frozen

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/api

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/workers/hierarchical-grouping-worker /app/workers/hierarchical-grouping-worker
COPY --from=builder /app/worker-base /app/worker-base
COPY --from=builder /app/dem /app/dem
COPY api /app/api

COPY workers/hierarchical-grouping-worker/deploy/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]