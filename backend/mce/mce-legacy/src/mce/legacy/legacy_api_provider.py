#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.provider import DataProvider
from mce.core.metric import MetricRequirements
import logging

logger = logging.getLogger(__name__)


class LegacyApiProvider(DataProvider):
    """
    LEGACY: Adapter for backward compatibility with telemetry-hub/metrics-compute-engine.
    Fetches OTel traces from ClickHouse via REST API (port 8081).

    This provider is kept for backward compatibility only. New code should use
    oxp-api providers through mce-client.
    """

    def __init__(self):
        # Lazy import of the Semantic Access Layer
        self._semantic_client = None
        self._legacy_fetch_fn = None

        # 1. Try to load Semantic Client (New)
        # Note: SemanticClient is not yet implemented - fallback to legacy DAL

        try:
            # 2. Try to load Legacy DAL (Old)
            from dal.api_client import get_api_client  # type: ignore[import]

            self._dal_client = get_api_client()
        except ImportError:
            logger.debug("Legacy DAL not found.")

        # 3. New API Provider (V2 Adapter)
        from mce.legacy.adapters.api_provider import ApiDataProvider

        self._api_provider = ApiDataProvider()  # Uses env vars

        self._available = (
            self._semantic_client is not None
            or hasattr(self, "_dal_client")
            or self._api_provider
        )

    def fetch(
        self, resource_id: str, requirements: MetricRequirements
    ) -> dict[str, Any]:
        """Fetch semantic entities or legacy trace data based on requirements."""
        # STRATEGY 1: Semantic Mode (Preferred)
        if requirements and requirements.required_entities and self._semantic_client:
            return self._fetch_semantic(resource_id, requirements)

        # STRATEGY 2: API Provider (New V2 -> V1 API)
        if self._api_provider:
            try:
                return self._api_provider.fetch(resource_id, requirements)
            except Exception as e:
                logger.warning(f"API Provider fetch failed: {e}")

        # STRATEGY 3: Legacy DAL Integration (Fallback)
        return self._fetch_legacy(resource_id, requirements)

    def _fetch_legacy(
        self, resource_id: str, requirements: MetricRequirements | None = None
    ) -> dict[str, Any]:
        """
        Replicates V1: fetch traces -> process -> return SessionEntity context.
        Uses injected function (for testing) or falls back to DAL.
        """
        # 1. Use injected fetch function (Testing/Mock)
        if self._legacy_fetch_fn:
            try:
                raw_data = self._legacy_fetch_fn(resource_id)
                if not raw_data:
                    return {}
                return self._adapt_legacy_keys(raw_data)
            except Exception as e:
                logger.error(f"Legacy Fetch Fn Error: {e}")
                raise

        # 2. Use Real DAL (Production)
        if hasattr(self, "_dal_client") and self._dal_client:
            try:
                traces = self._dal_client.get_traces_by_session(resource_id)
                if not traces:
                    return {}

                try:
                    from normalization.core.trace_processor_wrapper import (
                        traces_processor,
                    )  # type: ignore[import]

                    session_entity = traces_processor({resource_id: traces})
                    return {
                        "session": session_entity,
                        "tool_spans": session_entity.tool_spans,
                        "agent_spans": session_entity.agent_spans,
                        "llm_spans": session_entity.llm_spans,
                        "conversation": session_entity.conversation_data.get(
                            "conversation", ""
                        ),
                        "conversation_data": session_entity.conversation_data,
                        "input_text": session_entity.conversation_data.get("query", ""),
                        "output_text": session_entity.conversation_data.get(
                            "response", ""
                        ),
                    }
                except ImportError:
                    logger.warning(
                        "Normalization engine not found. Returning raw traces only."
                    )
                    return {"traces": traces}
            except Exception as e:
                logger.error(f"Legacy DAL Error: {e}")
                raise

        logger.error("No Legacy Fetch mechanism available (neither Mock nor DAL).")
        return {}

    def _adapt_legacy_keys(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Adapt raw legacy dictionaries to MCE standard keys."""
        context = raw_data.copy()
        if "query" in raw_data and "input_text" not in context:
            context["input_text"] = raw_data["query"]
        if "response" in raw_data and "output_text" not in context:
            context["output_text"] = raw_data["response"]
        return context

    def _fetch_semantic(
        self, resource_id: str, reqs: MetricRequirements
    ) -> dict[str, Any]:
        """Fetch using Semantic Client (Entity-based)."""
        context: dict[str, Any] = {}
        for entity_type in reqs.required_entities:
            if self._semantic_client:
                data = self._semantic_client.get_entities(
                    scope_id=resource_id,
                    type_uri=entity_type,
                    fields=reqs.text_fields + reqs.scalar_fields,
                )
                context[entity_type] = data

        if reqs.include_edges and reqs.allowed_relations and self._semantic_client:
            edges = self._semantic_client.get_edges(
                scope_id=resource_id,
                relations=reqs.allowed_relations,
            )
            context["edges"] = edges

        return context
