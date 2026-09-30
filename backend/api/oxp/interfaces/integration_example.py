#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Full integration example: Plugging an external MetricsProvider into oxp-api.
==========================================================================

This shows exactly how someone (e.g. the mce team) would:

  1. Implement MetricsProvider using their own Neo4j connection
  2. Plug it into oxp-api so all /metrics endpoints use their impl
  3. Start the server — existing endpoints work, no code changes needed

"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase

# ── Import the interface + types from oxp ──────────────────────────────────
from oxp.interfaces import MetricResult, MetricsProvider, NumericMetricResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. THE EXTERNAL PROVIDER  (this is what the mce team writes)
# ═══════════════════════════════════════════════════════════════════════════════


class Neo4jMetricsProvider(MetricsProvider):
    """
    MetricsProvider implementation using a direct neo4j-driver connection.

    This replaces oxp' built-in OXPMetricsProvider. The endpoints
    don't know or care — they just call MetricsProvider methods.
    """

    def __init__(self, uri: str, user: str = "neo4j", password: str = "password"):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self._driver.close()

    # ── MetricsProvider.get_metrics ─────────────────────────────────────────

    def get_metrics(
        self,
        resource_ids: str | list[str],
        metric_ids: str | list[str] | None = None,
        session_id: str | None = None,
        recursive: bool = False,
        **kwargs: Any,
    ) -> list[MetricResult]:
        rids = [resource_ids] if isinstance(resource_ids, str) else resource_ids
        mids = [metric_ids] if isinstance(metric_ids, str) else metric_ids

        query = """
        UNWIND $rids AS rid
        MATCH (r)
        WHERE r.id = rid OR r.executionId = rid
           OR (r:Session AND r.sessionId = rid)
        MATCH (r)-[:hasMetric]->(m:Metric)
        WHERE $mids IS NULL OR m.metricName IN $mids
        RETURN
            CASE WHEN 'Session' IN labels(r)
                 THEN r.sessionId
                 ELSE coalesce(r.id, r.executionId)
            END AS resource_id,
            m.metricName  AS metric_id,
            m.metricResult AS value_json,
            m.timestamp    AS timestamp
        """

        results = []
        with self._driver.session() as session:
            for record in session.run(query, rids=rids, mids=mids):
                raw = record["value_json"]
                val, metadata = 0.0, {}
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                    val = (
                        parsed.get("value", 0.0)
                        if isinstance(parsed, dict)
                        else float(parsed)
                    )
                    if isinstance(parsed, dict):
                        metadata = parsed
                except (ValueError, TypeError, json.JSONDecodeError):
                    metadata = {"raw_value": str(raw)}

                results.append(
                    NumericMetricResult(
                        metric_id=record["metric_id"],
                        resource_id=record["resource_id"],
                        provider="neo4j-mce",
                        value=val,
                        timestamp=record.get("timestamp") or datetime.now(timezone.utc),
                        metadata=metadata,
                    )
                )
        return results

    # ── MetricsProvider.save_metrics ────────────────────────────────────────

    def save_metrics(self, metrics: MetricResult | list[MetricResult]) -> bool:
        items = [metrics] if isinstance(metrics, MetricResult) else metrics

        query = """
        UNWIND $batch AS item
        MATCH (r)
        WHERE (NOT r:Metric AND r.id = item.resource_id)
           OR (NOT r:Metric AND r.executionId = item.resource_id)
           OR (r:Session AND r.sessionId = item.resource_id)
        MERGE (m:Metric {metricName: item.metric_id, resourceId: item.resource_id})
        SET m.metricResult = item.value_json,
            m.timestamp    = datetime(item.timestamp),
            m.provider     = item.provider,
            m.value        = item.value
        MERGE (r)-[:hasMetric]->(m)
        """

        batch = [
            {
                "resource_id": m.resource_id,
                "metric_id": m.metric_id,
                "value_json": json.dumps({"value": m.value, "provider": m.provider}),
                "timestamp": m.timestamp.isoformat(),
                "provider": m.provider,
                "value": m.value,
            }
            for m in items
            if not m.error and m.value is not None
        ]
        if not batch:
            return True
        try:
            with self._driver.session() as session:
                session.run(query, batch=batch)
            return True
        except Exception as e:
            logger.error("save_metrics failed: %s", e)
            return False

    # ── MetricsProvider.clean_metrics ───────────────────────────────────────

    def clean_metrics(self, session_id: str | None = None) -> int:
        if session_id:
            q = """
            MATCH (r)-[:hasMetric]->(m:Metric)
            WHERE r.sessionId = $sid OR (r:Session AND r.sessionId = $sid)
            DETACH DELETE m RETURN count(m) AS deleted
            """
            p = {"sid": session_id}
        else:
            q = "MATCH (m:Metric) DETACH DELETE m RETURN count(m) AS deleted"
            p = {}
        with self._driver.session() as s:
            rec = s.run(q, **p).single()
            return rec["deleted"] if rec else 0

    # ── MetricsProvider.list_llm_calls ──────────────────────────────────────

    def list_llm_calls(self, session_id: str) -> list[dict[str, Any]]:
        q = """
        MATCH (lc:LLMCall {sessionId: $sid})
        RETURN coalesce(lc.executionId, lc.spanId) AS id,
               coalesce(lc.modelName, 'unknown') AS model,
               lc.timestamp AS timestamp
        ORDER BY timestamp
        """
        with self._driver.session() as session:
            return [dict(r) for r in session.run(q, sid=session_id)]


# ═══════════════════════════════════════════════════════════════════════════════
# 2A. PATTERN A — Swap at startup (recommended for production)
#     Wire the provider before the server starts serving requests.
# ═══════════════════════════════════════════════════════════════════════════════


def run_server_with_custom_provider():
    """
    Start oxp-api with the external Neo4jMetricsProvider.

    After this, every HTTP call to:
        GET  /api/v1/metrics/sessions/{id}
        POST /api/v1/metrics/sessions/{id}
        GET  /api/v1/metrics/sessions/{id}/spans/{span_id}
        POST /api/v1/metrics/sessions/{id}/spans/{span_id}

    flows through Neo4jMetricsProvider instead of OXPMetricsProvider.
    The endpoint code is UNTOUCHED.
    """
    import uvicorn

    # 1. Create the external provider
    provider = Neo4jMetricsProvider(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
    )

    # 2. Swap it in — this is the ONE line that matters
    from oxp.api.api_v1.endpoints.metrics import set_metrics_provider

    set_metrics_provider(provider)

    # 3. Start the server as normal
    #    All /metrics endpoints now use Neo4jMetricsProvider
    print("Starting oxp-api with Neo4jMetricsProvider...")
    uvicorn.run("oxp.api:app", host="0.0.0.0", port=8000)


# ═══════════════════════════════════════════════════════════════════════════════
# 2B. PATTERN B — Hot-swap at runtime (e.g. from a management endpoint)
#     The server is already running, swap provider without restart.
# ═══════════════════════════════════════════════════════════════════════════════


def hot_swap_example():
    """
    Call this from anywhere (admin endpoint, management script, etc.)
    to switch the active provider while the server is running.

    Example admin endpoint you could add:

        @router.post("/admin/set-provider")
        def admin_set_provider(body: dict):
            provider = Neo4jMetricsProvider(uri=body["uri"], ...)
            set_metrics_provider(provider)
            return {"status": "switched to Neo4jMetricsProvider"}
    """
    from oxp.api.api_v1.endpoints.metrics import set_metrics_provider

    provider = Neo4jMetricsProvider(
        uri="bolt://production-neo4j:7687",
        password=os.getenv("NEO4J_PASSWORD", "password"),
    )
    set_metrics_provider(provider)
    print("Provider swapped! All /metrics requests now use Neo4jMetricsProvider.")


# ═══════════════════════════════════════════════════════════════════════════════
# 2C. PATTERN C — Library usage (no server, just the provider directly)
#     Use the provider from Python code without starting FastAPI.
# ═══════════════════════════════════════════════════════════════════════════════


def library_usage_example():
    """
    Use Neo4jMetricsProvider directly as a library — no server needed.

    This is how the mce engine would use it in a batch pipeline:

        for session_id in session_ids:
            data = data_provider.fetch(session_id, requirements)
            result = compute_metric(data)
            metrics_provider.save_metrics(result)
    """
    provider = Neo4jMetricsProvider(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
    )

    session_id = "demo-session-001"

    # ── Write a metric ────────────────────────────────────────────────────
    result = NumericMetricResult(
        metric_id="accuracy",
        resource_id=session_id,
        provider="mce-engine",
        value=0.92,
        reasoning="Based on ground-truth comparison",
    )
    ok = provider.save_metrics(result)
    print(f"Saved: {'OK' if ok else 'FAILED'}")

    # ── Read it back (same provider) ──────────────────────────────────────
    stored = provider.get_metrics(session_id, metric_ids=["accuracy"])
    for m in stored:
        print(f"  {m.metric_id} = {m.value} (provider={m.provider})")

    # ── Clean up ──────────────────────────────────────────────────────────
    # deleted = provider.clean_metrics(session_id=session_id)
    # print(f"Cleaned {deleted} metrics")

    provider.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_server_with_custom_provider()
