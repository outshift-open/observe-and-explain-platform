#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mce.helper.interfaces — Abstract interfaces owned by MCE.

``MetricsProvider`` defines the contract for metric CRUD operations.
Implementations live in oxp-api (``OXPMetricsProvider``).

``DataProvider`` is intentionally **not** defined here.  MCE's compute
engine uses ``mce.core.provider.DataProvider`` (a ``typing.Protocol`` with
``fetch`` only — no KG-specific methods).  oxp-api owns its own
``DataProvider`` ABC (with ``resolve_session_id``) in
``oxp.interfaces.data_provider``.

Dependency direction::

    mce-core       → DataProvider Protocol (fetch only)
                   → MetricResult, MetricRequirements
    mce-helper     → MetricsProvider ABC            ← this file
    oxp-api     → DataProvider ABC (resolve_session_id + fetch)
                   → OXPKGProvider(DataProvider)
                   → OXPMetricsProvider(MetricsProvider)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from mce.core.types import MetricResult


class MetricsProvider(ABC):
    """Abstract interface for metric CRUD operations on a knowledge graph.

    Implementations handle storing and retrieving pre-computed metric results,
    cleaning stale metric nodes, and serving time-series aggregations.

    Implementations live in oxp-api (``OXPMetricsProvider``).
    """

    # ── metric retrieval ──────────────────────────────────────────────────

    @abstractmethod
    def get_metrics(
        self,
        resource_ids: str | list[str],
        metric_ids: str | list[str] | None = None,
        session_id: str | None = None,
        recursive: bool = False,
        **kwargs: Any,
    ) -> list[MetricResult]:
        """Retrieve metrics for one or more KG resources.

        Parameters
        ----------
        resource_ids:
            Single resource ID or list of IDs to fetch metrics for.
        metric_ids:
            Optional metric name(s) to filter by. *None* returns all.
        session_id:
            Optional session context filter.
        recursive:
            If *True*, also match child resources sharing the same ``sessionId``.
        """

    # ── metric persistence ────────────────────────────────────────────────

    @abstractmethod
    def save_metrics(self, metrics: MetricResult | list[MetricResult]) -> bool:
        """Persist one or more metric results.

        Returns *True* if the save succeeded, *False* otherwise.
        """

    @abstractmethod
    def clean_metrics(self, session_id: str | None = None) -> int:
        """Delete stored metric nodes.

        Parameters
        ----------
        session_id:
            If provided, only delete metrics attached to resources in this
            session. *None* deletes **all** metrics.

        Returns the count of deleted nodes.
        """

    def delete_metrics(
        self,
        session_id: str | None = None,
        metric_ids: list[str] | None = None,
    ) -> int:
        """Delete metrics matching the given filters.

        Returns the count of deleted nodes.
        Default implementation delegates to clean_metrics.
        """
        return self.clean_metrics(session_id=session_id)

    def list_resources(
        self,
        session_id: str,
        resource_type: str = "llm_call",
    ) -> list[dict[str, Any]]:
        """List execution resources (LLM calls, tool calls, …) for a session.

        Default implementation returns an empty list.
        Providers may override for richer resource listing.
        """
        return []

    # ── time-series ───────────────────────────────────────────────────────

    @abstractmethod
    def get_metrics_over_time(
        self,
        metric_id: str,
        start: datetime,
        end: datetime | None = None,
        bucket: Literal["minute", "hour", "day"] = "hour",
        app_name: str | None = None,
    ) -> list[dict]:
        """Return aggregated time-series data for one metric.

        Each returned dict has keys: ``bucket`` (ISO-8601 str),
        ``avg_value``, ``min_value``, ``max_value``, ``n_sessions``.
        """
