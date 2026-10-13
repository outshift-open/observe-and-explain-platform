#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# ── Build stage ──────────────────────────────────────────────────────────────
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
COPY workers/mce-worker /app/workers/mce-worker
COPY worker-base /app/worker-base
COPY mce /app/mce
COPY api /app/api

RUN uv sync --package mce-worker --frozen --no-editable \
    --no-install-package numba \
    --no-install-package llvmlite

# ── LLM price table ──────────────────────────────────────────────────────────
# The price table the MCE bills with is refreshed from LiteLLM on every
# build, in the installed package. MODEL_PRICES_REFRESHED_AT changes on every build (see docker-bake.hcl), so this
# layer is never served from cache; for a plain `docker build`, pass a new value
# or use --no-cache. If LiteLLM cannot be reached or its file is invalid, the
# table committed in the repo stays.
ARG MODEL_PRICES_REFRESHED_AT=unset
COPY scripts/update_model_prices.py /tmp/update_model_prices.py
RUN /opt/venv/bin/python /tmp/update_model_prices.py \
      --trimmed-file "$(/opt/venv/bin/python -c 'import pathlib, mce.engine as p; print(pathlib.Path(p.__file__).parent / "data" / "model_prices.json")')" \
    || echo "WARNING: could not refresh the LLM price table from LiteLLM; keeping the one committed in the repo"

# ── Run stage ─────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY workers/mce-worker/deploy/docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
