#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""API v2 router — composes all v2 sub-routers under ``/api/v2``."""

from __future__ import annotations

from fastapi import APIRouter

from oxp.api.api_v2.endpoints import metrics
from oxp.health import healthz as _healthz

router = APIRouter(prefix="/api/v2", tags=["v2"])


@router.get("/healthz")
def healthz() -> dict:
    """Version-scoped health check."""
    return _healthz()


# ── Include domain sub-routers ────────────────────────────────────────────────

router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
