#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""API v1 router — composes all v1 sub-routers under ``/api/v1``."""

from __future__ import annotations

from fastapi import APIRouter

from oxp.api.api_v1.endpoints import (
    agentic_protocols_metrics,
    applications,
    cache,
    concepts,
    features,
    kg,
    labels,
    reasoning,
    metrics,
    semanticgroups,
    sessions,
    spans,
    symbolic,
    ui,
    waste_estimation,
    live_topology,
)
from oxp.health import healthz as _healthz

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/healthz")
def healthz() -> dict:
    """Version-scoped health check."""
    return _healthz()


# ── Include domain sub-routers ────────────────────────────────────────────────

router.include_router(cache.router, prefix="/cache", tags=["cache"])
router.include_router(reasoning.router, prefix="")
router.include_router(
    agentic_protocols_metrics.router,
    prefix="",
    tags=["agentic-protocols-metrics"],
)
router.include_router(ui.router, prefix="/ui", tags=["ui"])
router.include_router(kg.router, prefix="/kg", tags=["kg"])
router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
router.include_router(features.router, prefix="/features", tags=["features"])
router.include_router(
    semanticgroups.router, prefix="/semanticgroups", tags=["semanticgroups"]
)
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
router.include_router(spans.router, prefix="/spans", tags=["spans"])
router.include_router(
    applications.router, prefix="/applications", tags=["applications"]
)
router.include_router(concepts.router, prefix="/concepts", tags=["concepts"])
router.include_router(labels.router, prefix="/labels", tags=["labels"])
router.include_router(symbolic.router, prefix="/symbolic", tags=["symbolic"])
router.include_router(
    waste_estimation.router,
    prefix="/waste-estimation",
    tags=["waste-estimation"],
)
router.include_router(
    live_topology.router,
    prefix="/live_topology",
    tags=["live_topology"],
)
