#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from mce.engine.engine import MetricEngine
from mce.engine.llm import LLMService
from mce.core.registry import get_default_metrics
from mce.client.config import MCEClientConfig
from mce.client.setup import build_oxp_kg_provider
# from mce.adapters.json_provider import JsonDataProvider

# FastAPI service exposing MCE compute and metadata endpoints.

app = FastAPI(
    title="Metrics Computation Engine",
    description="MCE service for computing metrics on AI agent telemetry data",
    version="2.0.0",
)


class MetricsRequest(BaseModel):
    session_ids: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    # file: str | None = None
    llm_mode: str = "replay"
    llm_cache: str | None = None  # None → LLMService uses MCE_LLM_CACHE_PATH env var


def _get_kg_provider():
    """Instantiate a OXPKGProvider (oxp-api). Patchable in tests."""
    provider = build_oxp_kg_provider(MCEClientConfig.from_env())
    if provider is None:
        raise RuntimeError("oxp-api is required to build the KG provider")
    return provider


def _select_metrics(metric_names: list[str]):
    all_metrics = get_default_metrics()
    if not metric_names or "all" in metric_names:
        return all_metrics

    selected = []
    for name in metric_names:
        match = next(
            (
                metric
                for metric in all_metrics
                if metric.metric_id == name or metric.ontology_class == name
            ),
            None,
        )
        if match:
            selected.append(match)
    return selected


@app.get("/")
async def root():
    return {
        "message": "Metrics Computation Engine",
        "version": "2.0.0",
        "endpoints": {
            "compute_metrics": "/compute_metrics",
            "health": "/status",
            "list_metrics": "/metrics",
        },
    }


@app.get("/metrics")
async def list_metrics():
    metrics = get_default_metrics()
    return {
        "total_metrics": len(metrics),
        "metrics": [m.metadata.to_dict() for m in metrics],
    }


@app.get("/status")
async def status():
    return {
        "status": "ok",
        "message": "Metrics Computation Engine is running",
        "timestamp": datetime.now().isoformat(),
        "service": "mce",
        "api_base_url": os.getenv("API_BASE_URL", ""),
        "kg_base_url": os.getenv("KG_BASE_URL", ""),
    }


@app.post("/compute_metrics")
async def compute_metrics(request: MetricsRequest):
    if not request.session_ids:
        raise HTTPException(status_code=400, detail="No session_ids provided.")

    LLMService.configure(
        cache_path=request.llm_cache
        or os.getenv("MCE_LLM_CACHE_PATH", "llm_cache.json"),
        mode=request.llm_mode,
        api_key=os.getenv("OPENAI_API_KEY") or None,
        model=os.getenv("MCE_LLM_MODEL") or "gpt-4o",
        base_url=(
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("LITELLM_BASE_URL")
            or None
        ),
    )

    # if request.file:
    #     provider = JsonDataProvider(request.file)
    # else:
    try:
        provider = _get_kg_provider()
    except (RuntimeError, Exception) as exc:
        raise HTTPException(
            status_code=503, detail=f"KG data provider unavailable: {exc}"
        ) from exc

    engine = MetricEngine()
    engine.set_data_provider(provider)

    selected_metrics = _select_metrics(request.metrics)
    if not selected_metrics:
        raise HTTPException(status_code=400, detail="No valid metrics selected.")

    for metric in selected_metrics:
        engine.register_metric(metric)

    results = []
    session_ids = request.session_ids
    # if not session_ids and request.file:
    #     if hasattr(provider, "list_session_ids"):
    #         session_ids = provider.list_session_ids()

    for session_id in session_ids:
        results.extend(engine.compute_session(session_id))

    return {
        "results": [res.to_legacy_dict() for res in results],
    }
