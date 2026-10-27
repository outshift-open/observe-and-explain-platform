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

RUN uv sync --package stateful-eval-worker --frozen --no-editable

# ── LLM price table ──────────────────────────────────────────────────────────
# The price table stateful-evals bills with is refreshed from LiteLLM on every
# build, in the installed package. MODEL_PRICES_REFRESHED_AT changes on every build (see docker-bake.hcl), so this
# layer is never served from cache; for a plain `docker build`, pass a new value
# or use --no-cache. If LiteLLM cannot be reached or its file is invalid, the
# table committed in the repo stays.
ARG MODEL_PRICES_REFRESHED_AT=unset
COPY scripts/update_model_prices.py /tmp/update_model_prices.py
RUN /opt/.venv/bin/python /tmp/update_model_prices.py \
      --full-file "$(/opt/.venv/bin/python -c 'import pathlib, stateful_evals_be as p; print(pathlib.Path(p.__file__).parent / "data" / "model_prices_and_context_window.json")')" \
    || echo "WARNING: could not refresh the LLM price table from LiteLLM; keeping the one committed in the repo"

# ── Run stage ─────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt

COPY --from=builder /opt/.venv /opt/.venv
COPY workers/stateful-eval-worker/deploy/docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
