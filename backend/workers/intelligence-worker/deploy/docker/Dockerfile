#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# --- Builder stage ----------------------------------------------------------
# Copy the full uv workspace so uv can validate all workspace members declared
# in the root pyproject.toml when syncing this package.
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

COPY . /app

RUN --mount=type=secret,id=ARTIFACTORY_USERNAME,env=UV_INDEX_OUTSHIFT_PYPI_USERNAME \
    --mount=type=secret,id=ARTIFACTORY_PASSWORD,env=UV_INDEX_OUTSHIFT_PYPI_PASSWORD \
    uv sync --package intelligence-worker --frozen

# --- Runtime stage ----------------------------------------------------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/workers/intelligence-worker /app/workers/intelligence-worker
COPY --from=builder /app/worker-base /app/worker-base
COPY --from=builder /app/api /app/api
COPY --from=builder /app/dem /app/dem
COPY --from=builder /app/intelligence-catalog /app/intelligence-catalog

COPY workers/intelligence-worker/deploy/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
