#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
FROM python:3.13-slim-trixie AS builder

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.13 \
    UV_PROJECT_ENVIRONMENT=/app

WORKDIR /src

# Copy workspace root files and project metadata for dependency resolution.
# Separate layer for caching: dependency resolution is independent of source code changes.
COPY pyproject.toml /src/pyproject.toml
COPY uv.lock /src/uv.lock
COPY uv.lock /src/api/uv.lock
COPY api/pyproject.toml /src/api/pyproject.toml

# Install dependencies without installing source code yet.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=ARTIFACTORY_USERNAME,env=UV_INDEX_OUTSHIFT_PYPI_USERNAME \
    --mount=type=secret,id=ARTIFACTORY_PASSWORD,env=UV_INDEX_OUTSHIFT_PYPI_PASSWORD \
  cd /src && uv sync --frozen --no-dev --no-install-project --no-install-workspace --no-sources --project /src/api

# Copy the API source code.
COPY api /src/api

# Install the oxp-api package
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=ARTIFACTORY_USERNAME,env=UV_INDEX_OUTSHIFT_PYPI_USERNAME \
    --mount=type=secret,id=ARTIFACTORY_PASSWORD,env=UV_INDEX_OUTSHIFT_PYPI_PASSWORD \
  cd /src && uv sync --frozen --no-dev --no-editable --project /src/api

FROM python:3.13-slim-trixie AS runner

RUN useradd -m user

# Copy venv from builder with just the dependencies we need + our package
COPY --from=builder --chown=user:user /app /app

USER user

EXPOSE 8000

CMD ["/app/bin/dev"]