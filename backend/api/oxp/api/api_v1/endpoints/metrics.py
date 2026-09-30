#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /metrics endpoint.

Endpoints
---------
GET  /metrics/info
    Descriptive information about this endpoint.
GET  /metrics/catalog
    List all discoverable metrics (id, provider, scope, target_types).
GET  /metrics/catalog/{scope}
    List metrics filtered by attachment scope.
GET  /metrics/timeseries
    Single-query aggregated time-series for one metric (plot-ready).
GET  /metrics/sessions/{session_id}
    Read session-level metrics (with optional ``hops`` for sub-graph).
POST /metrics/sessions/{session_id}
    Write metrics to a session.
POST /metrics/compute
    Compute metrics for a batch of session IDs.

All operations delegate to an :class:`MetricsProvider` instance.
"""

from __future__ import annotations

import functools
import importlib.util
import logging
import os
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from oxp.api.api_v1.endpoints.helpers import get_client
from oxp.cache import cached, make_cache_key
from oxp.client._metrics import _metric_results_to_items
from oxp.client.utils import parse_epoch_range
from oxp.connectors.base import Connector
from oxp.core.config import settings
from oxp.dependencies import get_neo4j_db, get_redis
from oxp.interfaces.metrics_provider import MetricsProvider
from oxp.interfaces.models import MetricResult
from oxp.models.otel_traces import (
    MetricCatalogItem,
    MetricCatalogResponse,
    MetricInfoItemResponse,
    MetricsComputeRequest,
    MetricsComputeResponse,
    MetricsWriteResponse,
    MetricTimePoint,
    MetricTimeSeriesResponse,
    SessionMetricsResponse,
    SessionMetricsWriteRequest,
    SpanMetricsResponse,
    SpanMetricsWriteRequest,
)
from oxp.providers import OXPMetricsProvider
from oxp.providers.kg_query_runner import KGQueryExecutionError

logger = logging.getLogger(__name__)


class MetricsInfoResponse(BaseModel):
    """Response model for ``GET /metrics/info``."""

    subsystem: str
    total_metrics: int
    scopes: list[str]
    providers: list[str]
    metrics: list[dict[str, str]]


router = APIRouter()


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Lazily resolve the shared client from the Neo4j dependency."""
    return get_client(api_client=db)


# ── provider wiring ──────────────────────────────────────────────────────────
# Providers are initialised eagerly so the connection is validated at startup.
# If Neo4j is unavailable, _provider is set to None and every endpoint returns
# 503 until the DB becomes reachable.

_logger = logging.getLogger(__name__)

_provider: Optional[MetricsProvider] = None
_neo4j_graph_provider: Any = None  # singleton for /compute


def _init_metrics_provider() -> MetricsProvider:
    """Create a metrics provider backed by the shared Neo4j connector."""
    neo4j_db = next(get_neo4j_db())
    return OXPMetricsProvider(db=neo4j_db)


try:
    _provider = _init_metrics_provider()
except Exception as _exc:
    _logger.warning(
        "Neo4j unavailable at startup — metrics endpoints will return 503 "
        "until the database is reachable. Reason: %s",
        _exc,
    )


def _require_provider() -> MetricsProvider:
    """Return the active MetricsProvider or raise HTTP 503."""
    global _provider
    if _provider is None:
        try:
            _provider = _init_metrics_provider()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Neo4j is unavailable. Metrics endpoint is degraded.",
            ) from exc
    return _provider


def _client(db: Connector = Depends(get_neo4j_db)):  # noqa: B008
    """Resolve a Neo4j-backed client with the active metrics provider."""
    return get_client(api_client=db, metrics_provider=_require_provider())


def _get_neo4j_graph_provider() -> Any:
    """Return (and lazily create) the singleton Neo4jGraphProvider."""
    global _neo4j_graph_provider
    if _neo4j_graph_provider is None:
        # Avoid import cycle if oxp.providers -> metrics_endpoint
        from oxp.providers import Neo4jGraphProvider

        _neo4j_graph_provider = Neo4jGraphProvider()
    return _neo4j_graph_provider


def _get_configured_llm_model() -> str:
    """Return the model name configured for MCE runtime evaluation."""
    return os.getenv("MCE_LLM_MODEL") or os.getenv("LLM_MODEL_NAME") or "gpt-4o"


def _configure_llm_runtime() -> str:
    """Configure the shared LLM runtime used by native and external metrics."""
    from mce.engine.llm import LLMService

    model_name = _get_configured_llm_model()
    LLMService.configure(
        mode=os.getenv("MCE_LLM_MODE", "live"),
        cache_path=os.getenv("MCE_LLM_CACHE_PATH", "llm_cache.json"),
        api_key=os.getenv("OPENAI_API_KEY") or None,
        model=model_name,
        base_url=(
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("LITELLM_BASE_URL")
            or None
        ),
    )
    return model_name


def _get_configured_engine_max_workers() -> int:
    """Return the MetricEngine worker count for API-side metric execution."""
    env_value = os.getenv("MCE_ENGINE_MAX_WORKERS")
    if env_value:
        try:
            parsed = int(env_value)
            if parsed >= 1:
                return parsed
        except ValueError:
            logger.warning(
                "Invalid MCE_ENGINE_MAX_WORKERS=%r, using default",
                env_value,
            )

    return 8


def _prepare_metric_for_runtime(metric: Any, model_name: str) -> Any:
    """Clone mutable external wrappers before injecting runtime model state."""
    init_with_model = getattr(metric, "init_with_model", None)
    if not callable(init_with_model):
        return metric

    runtime_metric = deepcopy(metric)
    runtime_metric.init_with_model(model_name)
    return runtime_metric


def _build_metric_engine(metric_ids: list[str] | None = None) -> Any:
    """Build a MetricEngine configured with the Neo4j graph provider."""
    try:
        from mce.core.registry import get_default_metrics
        from mce.engine.engine import MetricEngine
    except ImportError as exc:
        raise HTTPException(
            status_code=501, detail=f"mce-core not available: {exc}"
        ) from exc

    engine = MetricEngine(max_workers=_get_configured_engine_max_workers())
    engine.set_data_provider(_get_neo4j_graph_provider())
    llm_model = _configure_llm_runtime()

    all_metrics = get_default_metrics()
    selected = [m for m in all_metrics if not metric_ids or m.metric_id in metric_ids]
    if metric_ids and not selected:
        raise HTTPException(
            status_code=400,
            detail="No valid metrics found for the requested metric_names.",
        )

    for metric in selected:
        engine.register_metric(_prepare_metric_for_runtime(metric, llm_model))
    return engine


def _compute_session_metrics(
    session_id: str,
    metric_ids: list[str],
    *,
    recursive: bool,
) -> list[MetricResult]:
    """Compute session-level metrics for the requested metric IDs."""
    engine = _build_metric_engine(metric_ids)
    try:
        computed = engine.compute_session(session_id, recursive=recursive)
    except KGQueryExecutionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Knowledge graph unavailable while computing metrics: {exc}",
        ) from exc

    by_name: dict[str, MetricResult] = {}
    for result in computed:
        if result.resource_id != session_id:
            continue
        if result.metric_id not in metric_ids:
            continue
        by_name.setdefault(result.metric_id, result)

    return [by_name[name] for name in metric_ids if name in by_name]


def _normalize_metric_names(
    metric_names: list[str] | None,
    raw_metric_names: list[str],
) -> list[str] | None:
    """Normalize metric names from parsed and raw query parameters."""
    candidates = raw_metric_names or (metric_names or [])
    normalized: list[str] = []
    for candidate in candidates:
        for part in candidate.split(","):
            name = part.strip()
            if name:
                normalized.append(name)
    if not normalized:
        return None
    return list(dict.fromkeys(normalized))


def set_metrics_provider(provider: MetricsProvider) -> None:
    """Replace the active MetricsProvider at runtime (used by tests)."""
    global _provider
    _provider = provider


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


def _mce_discovery_providers_available() -> bool:
    """Return True when at least one MCE provider module is importable.

    Avoid calling discover_all_metrics() when only mce-core is installed, because
    mce-core probes optional provider modules and emits noisy import warnings.
    """
    provider_modules = (
        "mce.providers.native.metrics",
        "mce.providers.sdk",
        "mce.providers.deepeval.wrapper",
        "mce.providers.ragas.wrapper",
        "mce.providers.opik.wrapper",
    )
    return any(
        importlib.util.find_spec(module) is not None for module in provider_modules
    )


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


@router.get("/catalog", response_model=MetricCatalogResponse)
def get_metrics_catalog() -> Any:
    """List all discoverable metrics with their provider, scope, and target types."""
    items = _build_catalog()
    return MetricCatalogResponse(total=len(items), metrics=items)


@router.get("/catalog/{scope}", response_model=MetricCatalogResponse)
def get_metrics_catalog_by_scope(scope: str) -> Any:
    """List metrics filtered by attachment scope (session, span, execution_element)."""
    all_items = _build_catalog()
    filtered = [m for m in all_items if m.scope == scope]
    return MetricCatalogResponse(total=len(filtered), metrics=filtered)


@router.get("/catalog_with_categories")
def get_metrics_catalog_with_categories() -> Any:
    """Return the metric catalog organized by configured categories."""

    categories = settings.METRIC_CATEGORIES
    return categories


@router.get("/catalog_with_categories_meta")
def get_metrics_catalog_with_categories_meta() -> Any:
    """Return the metric catalog organized by configured categories."""

    categories = settings.METRIC_CATEGORIES_META
    # categories = settings.METRIC_CATEGORIES
    # meta = getattr(settings, "METRIC_CATEGORIES_META", {}) or {}
    # enriched: dict[str, Any] = {}
    # for key, metrics in categories.items():
    #     md = meta.get(key, {})
    #     metric_names = list(metrics.keys()) if isinstance(metrics, dict) else []
    #     enriched[key] = {
    #         "name": md.get("name") or key,
    #         "description": md.get("description") or f"Metrics in the {key} category",
    #         "key": md.get("key") or key,
    #         "metrics_names_list": md.get("metrics_list") or metric_names,
    #         "metrics": metrics,
    #     }
    # return enriched
    return categories


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


# ── helpers ───────────────────────────────────────────────────────────────────

_DURATION_RE = re.compile(
    r"^(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$", re.IGNORECASE
)


def _parse_duration(s: str) -> timedelta:
    """Parse a human-readable duration string into a timedelta.

    Supported units: w (weeks), d (days), h (hours), m (minutes).
    Examples: ``7d``, ``2w3d``, ``24h``, ``1w2d6h``.
    """
    m = _DURATION_RE.match(s.strip())
    if not m or not any(m.groups()):
        raise ValueError(
            f"Invalid duration '{s}'. Use combinations of w/d/h/m, e.g. '7d', '2w', '24h', '1w3d6h'."
        )
    weeks, days, hours, minutes = (int(v or 0) for v in m.groups())
    return timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes)


# ── Time-series metrics ─────────────────────────────────────────────────


@router.get("/timeseries", response_model=MetricTimeSeriesResponse)
def get_metric_timeseries(
    metric_id: str = Query(..., description="Metric name, e.g. 'Groundedness'"),
    # ── Unix epoch timestamps (harmonized with /applications/{id}/agent/{id}/charts) ──
    start_time: Optional[str] = Query(
        None,
        description="Unix epoch timestamp (seconds) for the start of the range. "
        "Takes precedence over 'start', 'duration', and 'window_hours' when provided.",
    ),
    end_time: Optional[str] = Query(
        None,
        description="Unix epoch timestamp (seconds) for the end of the range. "
        "Defaults to now. Used together with 'start_time' or 'duration'.",
    ),
    # ── Human-readable duration ───────────────────────────────────────────────
    duration: Optional[str] = Query(
        None,
        description="Human-readable duration ending at 'end_time'/'end' (or now). "
        "Combinations of w/d/h/m: '7d', '2w', '24h', '1w3d6h'. "
        "Mutually exclusive with 'start_time' and 'window_hours'.",
    ),
    window_hours: Optional[int] = Query(
        None,
        ge=1,
        le=8760,
        description="Rolling window in hours (legacy). Prefer 'duration'. "
        "Mutually exclusive with 'start_time' and 'start'.",
    ),
    # ── ISO-8601 explicit range ───────────────────────────────────────────────
    start: Optional[datetime] = Query(
        None,
        description="ISO-8601 start datetime (UTC). Used when neither start_time, duration nor window_hours is given.",
    ),
    end: Optional[datetime] = Query(
        None,
        description="ISO-8601 end datetime (UTC). Ignored when end_time is provided.",
    ),
    # ── Aggregation & filters ─────────────────────────────────────────────────
    bucket: Literal["minute", "hour", "day"] = Query(
        "hour", description="Time-bucket granularity for aggregation."
    ),
    app_name: Optional[str] = Query(
        None, description="Filter by application name (alias: application_id)."
    ),
    application_id: Optional[str] = Query(
        None, description="Filter by application ID (alias for app_name)."
    ),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID."),
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return aggregated time-series data for one metric.

    **Parameter priority** (highest to lowest):

    1. ``start_time`` / ``end_time`` — Unix epoch seconds (harmonized with ``/applications/{id}/charts``)
    2. ``duration`` — human-readable window relative to ``end_time`` or now
    3. ``window_hours`` — legacy integer window in hours
    4. ``start`` / ``end`` — explicit ISO-8601 datetimes

    When ``end_time`` / ``end`` are omitted the window extends up to now (open-ended).

    **Examples**:

    Unix epoch (same format as ``/applications/{id}/charts``)::

        ?metric_id=Groundedness&start_time=1773187200&end_time=1773360000&bucket=day

    Human-readable duration ending now::

        ?metric_id=Groundedness&duration=7d&bucket=day

    Human-readable duration ending at a specific epoch::

        ?metric_id=Cost&duration=2w&end_time=1773360000&bucket=day

    ISO-8601 explicit range::

        ?metric_id=Duration&start=2026-03-01T00:00:00Z&end=2026-03-13T00:00:00Z&bucket=day
    """
    # Validate mutually exclusive params before cache lookup so invalid requests always 422.
    if duration is not None and window_hours is not None:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'duration' or 'window_hours', not both.",
        )
    if duration is not None:
        try:
            _parse_duration(duration)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    key = make_cache_key(
        "metrics:timeseries",
        {
            "metric": metric_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "window_hours": window_hours,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "bucket": bucket,
            "app": app_name or application_id,
            "agent": agent_id,
        },
    )

    def _fetch():
        # Resolve end first (needed by duration logic)
        if end_time is not None:
            _start_e, end_e = parse_epoch_range("", end_time)
            resolved_end = datetime.fromtimestamp(end_e, tz=timezone.utc)
        elif end is not None:
            resolved_end = end
        else:
            resolved_end = datetime.now(timezone.utc)

        # Resolve start
        if start_time is not None:
            start_e, _ = parse_epoch_range(start_time, "")
            resolved_start = datetime.fromtimestamp(start_e, tz=timezone.utc)
        elif duration is not None:
            resolved_start = resolved_end - _parse_duration(duration)
        elif window_hours is not None:
            resolved_start = resolved_end - timedelta(hours=window_hours)
        else:
            resolved_start = start or (resolved_end - timedelta(hours=24))

        resolved_end_param = resolved_end if (end_time or end) else None

        effective_app = app_name or application_id
        rows = _require_provider().get_metrics_over_time(
            metric_id,
            start=resolved_start,
            end=resolved_end_param,
            bucket=bucket,
            app_name=effective_app,
            agent_id=agent_id,
        )
        return MetricTimeSeriesResponse(
            metric_id=metric_id,
            bucket_size=bucket,
            start=resolved_start.isoformat(),
            end=resolved_end_param.isoformat() if resolved_end_param else None,
            points=[
                MetricTimePoint(
                    bucket=r["bucket"],
                    avg_value=r["avg_value"],
                    min_value=r["min_value"],
                    max_value=r["max_value"],
                    n_sessions=r["n_sessions"],
                )
                for r in rows
            ],
        )

    return cached(
        redis_client=redis_client,
        key=key,
        fetch=_fetch,
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


# ── Session-level metrics ─────────────────────────────────────────────────────


@router.get("/sessions/{session_id}", response_model=SessionMetricsResponse)
def get_session_metrics(
    request: Request,
    session_id: str,
    hops: int = Query(1, ge=0, le=5, description="Sub-graph traversal depth"),
    metric_names: list[str] | None = Query(
        None,
        description="Optional list of metric names to return; repeated query parameter supported",
    ),
    compute: bool = Query(
        True, description="Compute requested missing metrics on the fly"
    ),
    persist: bool = Query(
        False, description="Persist successfully computed session-level metrics"
    ),
    recursive: bool = Query(
        False, description="Enable recursive span fetching when compute=true"
    ),
    use_cache: bool = Query(
        True,
        description="Read persisted metrics before computing missing ones. Set to false to force live computation only.",
    ),
) -> Any:
    """Return session-level metrics from the knowledge graph."""
    metric_names = _normalize_metric_names(
        metric_names,
        request.query_params.getlist("metric_names"),
    )

    if persist and not compute:
        raise HTTPException(
            status_code=400, detail="persist=true requires compute=true."
        )
    if not use_cache and not compute:
        raise HTTPException(
            status_code=400, detail="use_cache=false requires compute=true."
        )
    if not use_cache and not metric_names:
        raise HTTPException(
            status_code=400,
            detail="use_cache=false requires metric_names so the API knows what to compute.",
        )

    provider = _require_provider()
    persisted_results = provider.get_metrics(session_id, hops=hops) if use_cache else []

    if not metric_names:
        results = persisted_results
    else:
        requested_names = list(dict.fromkeys(metric_names))
        persisted_by_name = {
            result.metric_id: result
            for result in persisted_results
            if result.metric_id in requested_names
        }

        computed_by_name: dict[str, MetricResult] = {}
        missing_names = [
            name for name in requested_names if name not in persisted_by_name
        ]
        if compute and missing_names:
            computed_results = _compute_session_metrics(
                session_id,
                missing_names,
                recursive=recursive,
            )
            computed_by_name = {result.metric_id: result for result in computed_results}

            if persist:
                to_persist = [
                    result
                    for result in computed_results
                    if result.error is None and result.value is not None
                ]
                if to_persist:
                    provider.save_metrics(to_persist)

        results = []
        for name in requested_names:
            if name in persisted_by_name:
                results.append(persisted_by_name[name])
            elif name in computed_by_name:
                results.append(computed_by_name[name])
            else:
                results.append(
                    MetricResult(
                        metric_id=name,
                        resource_id=session_id,
                        provider="oxp",
                        error="missing data",
                    )
                )

    return SessionMetricsResponse(
        session_id=session_id,
        metrics=_metric_results_to_items(results, metric_names),
    )


@router.post("/sessions/{session_id}", response_model=MetricsWriteResponse)
def post_session_metrics(
    session_id: str,
    body: SessionMetricsWriteRequest,
) -> Any:
    """Write metrics to a session in the knowledge graph."""
    items = [
        MetricResult(
            metric_id=m.name,
            resource_id=session_id,
            provider=m.provider,
            value=m.value,
            metadata={
                "metric_id": m.metric_id or m.name,
                "source": m.source,
            },
            reasoning=m.reasoning,
        )
        for m in body.metrics
    ]
    ok = _require_provider().save_metrics(items)
    if ok:
        return MetricsWriteResponse(written=len(items))
    return MetricsWriteResponse(
        written=0, errors=["save_metrics returned False — check server logs"]
    )


# ── Compute metrics ──────────────────────────────────────────────────────────


@router.post("/compute", response_model=MetricsComputeResponse)
def compute_metrics(body: MetricsComputeRequest) -> Any:
    """Compute metrics for a batch of sessions using MetricEngine + OXPKGProvider."""
    import uuid as _uuid

    effective_ids = body.metric_ids or ([body.metric_id] if body.metric_id else None)
    engine = _build_metric_engine(effective_ids)

    computed = 0
    failed = 0
    errors: list[str] = []
    all_results: list[dict] = []
    for session_id in body.session_ids:
        try:
            session_results = engine.compute_session(
                session_id, recursive=body.recursive
            )
            all_results.extend(
                [
                    {
                        "session_id": session_id,
                        "metric_id": r.metric_id,
                        "value": r.value,
                        "resource_id": getattr(r, "resource_id", session_id),
                        "error": r.error,
                        "reasoning": getattr(r, "reasoning", None),
                    }
                    for r in session_results
                ]
            )
            computed += 1
        except KGQueryExecutionError as exc:
            failed += 1
            errors.append(f"{session_id}: knowledge graph unavailable ({exc})")
        except Exception as exc:
            import logging as _logging

            _logging.getLogger(__name__).exception(
                "compute_session failed for %s", session_id
            )
            failed += 1
            errors.append(f"{session_id}: {exc}")

    return MetricsComputeResponse(
        job_id=f"job_{_uuid.uuid4().hex[:6]}",
        status="completed" if not errors else "partial",
        message=f"Metric computation completed for {len(body.session_ids)} session{'s' if len(body.session_ids) != 1 else ''}",
        total_sessions=len(body.session_ids),
        computed=computed,
        failed=failed,
        errors=errors,
        results=all_results,
    )


@router.get(
    "/sessions/{session_id}/spans/{span_id}",
    response_model=SpanMetricsResponse,
)
def get_span_metrics(
    session_id: str,
    span_id: str,
    hops: int = Query(1, ge=0, le=5, description="Sub-graph traversal depth"),
    metrics_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return span-level metrics from the knowledge graph."""
    key = make_cache_key(
        "metrics:span",
        {"session": session_id, "span": span_id, "hops": hops},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: metrics_client.get_span_metrics(
            span_id,
            session_id=session_id,
            hops=hops,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.post(
    "/sessions/{session_id}/spans/{span_id}",
    response_model=MetricsWriteResponse,
)
def post_span_metrics(
    session_id: str,
    span_id: str,
    body: SpanMetricsWriteRequest,
    metrics_client=Depends(_client),  # noqa: B008
) -> Any:
    """Write metrics to a span in the knowledge graph."""
    result = metrics_client.write_span_metrics(
        session_id,
        span_id,
        metrics=[m.model_dump() for m in body.metrics],
    )
    return MetricsWriteResponse(**result)


# ── Category-level metrics ───────────────────────────────────────────────────


@router.get(
    "/applications/{application_id}/summary",
)
def get_metrics_summary(
    application_id: str,
    start_time: str | None = Query(None, description="ISO-8601 start time filter"),
    end_time: str | None = Query(None, description="ISO-8601 end time filter"),
    metrics_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    key = make_cache_key(
        "metrics:app_summary",
        {"app": application_id, "start": start_time, "end": end_time},
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: metrics_client.get_application_metrics_summary(
            application_id=application_id
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/applications/{application_id}/metrics")
def get_application_metrics(
    application_id: str,
    metric_names: list[str] = Query(
        ..., description="List of metric names to retrieve"
    ),
    start_time: str | None = Query(
        None, description="ISO-8601 or epoch start time filter"
    ),
    end_time: str | None = Query(None, description="ISO-8601 or epoch end time filter"),
    agent_id: str | None = Query(None, description="Optional agent ID filter"),
    metrics_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return metric values for an application given an explicit list of metric names."""
    key = make_cache_key(
        "metrics:app_metrics",
        {
            "app": application_id,
            "metrics": sorted(metric_names),
            "start": start_time,
            "end": end_time,
            "agent": agent_id,
        },
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: metrics_client.get_metrics(
            application_id,
            metric_names,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


@router.get("/applications/{application_id}/category/{cat_key}")
def get_application_metrics_by_category(
    application_id: str,
    cat_key: str,
    start_time: str | None = Query(
        None, description="ISO-8601 or epoch start time filter"
    ),
    end_time: str | None = Query(None, description="ISO-8601 or epoch end time filter"),
    agent_id: str | None = Query(None, description="Optional agent ID filter"),
    metrics_client=Depends(_client),  # noqa: B008
    redis_client: redis_lib.Redis = Depends(get_redis),  # noqa: B008
) -> Any:
    """Return metric values for an application filtered by a configured category key."""
    key = make_cache_key(
        "metrics:app_category",
        {
            "app": application_id,
            "cat": cat_key,
            "start": start_time,
            "end": end_time,
            "agent": agent_id,
        },
    )
    return cached(
        redis_client=redis_client,
        key=key,
        fetch=lambda: metrics_client.get_metrics_per_category(
            application_id,
            cat_key,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        ),
        ttl=settings.CACHE_TTL_SECONDS,
        enabled=settings.CACHE_ENABLED,
    )


def get_metrics_by_category(
    application_id: str,
    metric_defs_or_names: Any,
    category: str | None = None,
    metrics_client: Any | None = None,
) -> dict[str, Any]:
    """Helper exported for tests: delegate to a LocalClient or provided client.

    Kept as a plain function (not a route) so tests can import it directly.
    """
    # Accept either a dict of metric defs or a list of metric names.
    if isinstance(metric_defs_or_names, dict):
        metric_names = list(metric_defs_or_names.keys())
    else:
        metric_names = list(metric_defs_or_names or [])

    if metrics_client is None:
        from oxp.client import LocalClient

        client = LocalClient()
        return client.get_metrics(application_id, metric_names)
    return metrics_client.get_metrics(application_id, metric_names)
