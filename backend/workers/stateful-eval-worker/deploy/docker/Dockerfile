#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

COPY pyproject.toml uv.lock /opt/
COPY workers/stateful-eval-worker /opt/workers/stateful-eval-worker
COPY worker-base /opt/worker-base
COPY stateful-evals /opt/stateful-evals
COPY api /opt/api

RUN --mount=type=secret,id=ARTIFACTORY_USERNAME,env=UV_INDEX_OUTSHIFT_PYPI_USERNAME \
    --mount=type=secret,id=ARTIFACTORY_PASSWORD,env=UV_INDEX_OUTSHIFT_PYPI_PASSWORD \
    uv sync --package stateful-eval-worker --frozen --no-editable

# ── Run stage ─────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt

COPY --from=builder /opt/.venv /opt/.venv
COPY workers/stateful-eval-worker/deploy/docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
