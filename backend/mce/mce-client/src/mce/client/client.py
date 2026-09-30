#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCEClient — high-level entry point for metrics retrieval and computation.

This module is the data access layer (DAL) that sits on top of ``mce`` (the pure
computation engine).  Workers and applications should import from ``mce.client``
rather than from ``mce`` internals directly.

Architecture::

    mce-core     (computation: providers, metrics, engine)
        ↑
    oxp-api   (KG provider, connector ownership)
        ↑
    mce-client   (DAL: config + orchestration)
        ↑
    workers / API handlers
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from .config import MCEClientConfig
from .setup import build_oxp_kg_provider

logger = logging.getLogger(__name__)


def _build_api_graph_provider(config: MCEClientConfig):
    """Build the graph provider via oxp-api, not via mce-local adapters."""
    config.validate()
    provider = build_oxp_kg_provider(config, combined=True)
    if provider is None:
        raise RuntimeError("oxp-api is required to build the MCE graph provider")
    return provider


class MCEClient:
    """High-level client for the Metrics Computation Engine.

    Encapsulates the oxp-api data access layer and the metric computation
    engine behind a single, stable API. Internal backend details are not exposed.

    Usage::

        client = MCEClient()
        results = client.get_metrics(
            "76bc0800-8f02-416a-9ff3-f172e0ad68c2",
            metric_ids=["Duration", "Cost", "AnswerRelevancy"],
        )

    Parameters
    ----------
    config:
        An explicit :class:`MCEClientConfig` instance.
    kg_provider:
        Optional pre-built KG provider. When supplied, the client skips
        provider construction and uses this provider directly. Useful for
        testing or when the caller already holds a connected provider instance.
    """

    def __init__(
        self,
        config: Optional[MCEClientConfig] = None,
        kg_provider: Optional[Any] = None,
    ) -> None:
        self._config = config or MCEClientConfig()
        self._kg_provider: Any = kg_provider  # pre-injected or lazy provider init
        self._engine: Any = None  # Lazy: created on first access

    # ------------------------------------------------------------------
    # Internal lazy initializers
    # ------------------------------------------------------------------

    def _get_kg_provider(self):
        """Return the KG provider, lazily building one from explicit config.

        When ``kg_provider`` was injected at construction (e.g. in tests or
        when called from oxp-api), that instance is returned directly.

        When no provider was injected, the client delegates provider creation
        to oxp-api using the explicit config supplied at the boundary.
        """
        if self._kg_provider is None:
            self._kg_provider = _build_api_graph_provider(self._config)
        return self._kg_provider

    def _get_engine(self):
        """Return a MetricEngine instance (lazy init).

        The engine is intentionally *not* wired to a data provider here —
        callers that need KG access must call ``engine.set_data_provider()``
        themselves.  This keeps engine init free from network connections.

        All native metrics discovered via :func:`~mce.core.registry.discovery.
        discover_all_metrics` are registered on the engine at init time.
        Engine runtime parameters (``max_workers``, ``execution_strategy``) are
        read from :attr:`_config`.
        """
        if self._engine is None:
            from mce.engine.engine import MetricEngine
            from mce.core.registry.discovery import discover_all_metrics

            self._engine = MetricEngine(
                max_workers=self._config.engine_max_workers,
                execution_strategy=self._config.engine_strategy,
            )
            for metric in discover_all_metrics():
                self._engine.register_metric(metric)
        return self._engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_metrics(
        self,
        resource_id: str,
        metric_ids: Optional[List[str]] = None,
        recursive: bool = False,
    ) -> List[Any]:
        """Retrieve pre-computed metric results from the knowledge graph.

        Parameters
        ----------
        resource_id:
            Session ID or execution element ID (``exec-llm-*``, etc.).
        metric_ids:
            Metric names to retrieve.  When *None* all available metrics are
            returned.
        recursive:
            When *True*, also retrieve metrics for nested execution elements
            (LLMCalls, ToolCalls, …).

        Returns
        -------
        List of :class:`mce.core.types.MetricResult` objects.
        """
        kg = self._get_kg_provider()
        return kg.get_metrics(resource_id, metric_ids=metric_ids, recursive=recursive)

    def list_sessions(self, limit: int = 50) -> List[str]:
        """Return the most recent session IDs from the knowledge graph.

        Parameters
        ----------
        limit:
            Maximum number of session IDs to return.
        """
        kg = self._get_kg_provider()
        raw = kg.list_sessions(limit=limit)
        return [row.get("sessionId") or row.get("id", "") for row in raw if row]

    def close(self) -> None:
        """Release the underlying provider when it exposes a close hook."""
        if self._kg_provider is not None:
            try:
                self._kg_provider.close()
            except Exception:
                pass
            self._kg_provider = None

    def compute_and_store(
        self,
        resource_id: str,
        metric_ids: Optional[List[str]] = None,
    ) -> List[Any]:
        """Compute metrics for a session and persist them to the knowledge graph.

        Equivalent to the old ``processor.compute_metrics()`` — kept for API
        stability with workflow consumers.  Delegates to
        :class:`~mce.client.worker.MCEWorkerService`.
        """
        from mce.client.worker import MCEWorkerService

        svc = MCEWorkerService(
            kg_provider=self._kg_provider,
            client_config=self._config,
        )
        return svc.process_session(resource_id)

    # Context manager support
    def __enter__(self) -> "MCEClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
