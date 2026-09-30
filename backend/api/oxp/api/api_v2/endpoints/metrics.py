#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the v2 /metrics endpoint.

This module starts as a clone of the v1 metrics endpoint. Endpoints will be
reimplemented here incrementally without touching v1.

Endpoints
---------
GET  /metrics/applications/{application_id}/metrics
    Return metric values for an application given an explicit list of metric names.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from oxp.api.api_v1.endpoints.helpers import get_client

# Reuse v1 provider wiring and helpers until v2 introduces its own.
from oxp.api.api_v1.endpoints.metrics import (
    _mce_discovery_providers_available,
    _require_provider,
)
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_neo4j_db
from oxp.models.otel_traces import (
    MetricCatalogItem,
    MetricCatalogResponse,
    MetricInfoItemResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Resolve a Neo4j-backed client with the active metrics provider."""
    return get_client(api_client=db, metrics_provider=_require_provider())


# ── Metrics catalog ───────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def _build_catalog() -> list[MetricCatalogItem]:
    """Discover all registered metrics using the mce-core registry.

    Result is cached for the lifetime of the process — metrics are
    registered at import time and do not change at runtime.
    """
    try:
        if _mce_discovery_providers_available():
            from mce.core.registry.discovery import (
                discover_all_metrics,
                ensure_target_types,
                get_provider_name,
            )

            items = []
            for metric_cls in discover_all_metrics():
                ensure_target_types(metric_cls)
                meta = getattr(metric_cls, "metadata", None)
                scope = getattr(meta, "scope", None) if meta else None
                scope_val = (
                    scope.value
                    if hasattr(scope, "value")
                    else str(scope)
                    if scope
                    else "session"
                )
                target_types = getattr(meta, "target_types", None) or set()
                description = getattr(meta, "description", None)
                display_name = (
                    meta.get_display_name()
                    if meta and hasattr(meta, "get_display_name")
                    else metric_cls.metric_id
                )
                items.append(
                    MetricCatalogItem(
                        metric_id=metric_cls.metric_id,
                        id=metric_cls.metric_id,
                        name=display_name,
                        provider=get_provider_name(metric_cls),
                        scope=scope_val,
                        target_types=sorted(target_types),
                        description=description,
                    )
                )
            return items

        logger.info(
            "MCE provider modules not installed; serving fallback metric catalog from METRIC_CATEGORIES"
        )
    except Exception as exc:
        logger.warning(
            "Metric discovery failed; falling back to configured catalog: %s", exc
        )

    return _build_fallback_catalog_from_settings()


def _build_fallback_catalog_from_settings() -> list[MetricCatalogItem]:
    """Build a static metric catalog from application settings.

    This keeps /metrics/catalog useful in minimal environments where optional
    MCE provider wheels are intentionally not installed.
    """
    items: list[MetricCatalogItem] = []
    seen: set[str] = set()

    for category in settings.METRIC_CATEGORIES.values():
        for metric_id, cfg in category.items():
            if metric_id in seen:
                continue
            seen.add(metric_id)

            items.append(
                MetricCatalogItem(
                    metric_id=metric_id,
                    id=metric_id,
                    name=cfg.get("name") or metric_id,
                    provider="OXP",
                    scope="session",
                    target_types=["mas:Session"],
                    description=cfg.get("description"),
                )
            )

    return sorted(items, key=lambda item: item.metric_id.lower())


# ── get_metrics ───────────────────────────────────────────────────────────────


# @router.get("/applications/{application_id}/metrics")
# def get_metrics(
#     application_id: str,
#     metric_names: list[str] = Query(..., description="List of metric names to retrieve"),
#     start_time: str | None = Query(None, description="ISO-8601 or epoch start time filter"),
#     end_time: str | None = Query(None, description="ISO-8601 or epoch end time filter"),
#     agent_id: str | None = Query(None, description="Optional agent ID filter"),
#     metrics_client=Depends(_client),  # noqa: B008
# ) -> Any:
#     """Return metric values for an application given an explicit list of metric names."""
#     return metrics_client.get_metrics(
#         application_id,
#         metric_names,
#         agent_id=agent_id,
#         start_time=start_time,
#         end_time=end_time,
#     )


@router.get("/info")
def metrics_info(
    metric_id: Optional[str] = Query(
        None,
        description="Metric ID to look up (returns single-metric detail when provided)",
    ),
) -> Any:
    """Return descriptive information about the metrics subsystem.

    * Without ``?metric_id=``: returns the full MCE metric catalog (same shape as ``/catalog``).
    * With ``?metric_id=<id>``: returns detailed info for that specific metric.
    """

    logger.debug(">>> oxp-api v2 >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    catalog = _build_catalog()
    if metric_id is not None:
        match = next(
            (m for m in catalog if m.metric_id == metric_id or m.id == metric_id),
            None,
        )
        if match is None:
            raise HTTPException(
                status_code=404, detail=f"Metric '{metric_id}' not found"
            )
        return MetricInfoItemResponse(
            id=match.id,
            name=match.name,
            description=match.description,
            unit=match.unit,
            type=match.type,
            dimensions=match.target_types,
        )
    return MetricCatalogResponse(total=len(catalog), metrics=catalog)
