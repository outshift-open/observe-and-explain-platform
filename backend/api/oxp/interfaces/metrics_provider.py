#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MetricsProvider — abstract interface for metric storage and retrieval.

Implementations handle:
- Retrieving metrics by resource ID(s) and/or metric name(s)
- Saving computed metric results to the KG
- Cleaning / deleting stored metrics
- Listing execution-level resources (e.g. LLM calls in a session)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from oxp.interfaces.models import MetricResult


class MetricsProvider(ABC):
    """Abstract interface for metric CRUD operations on a knowledge graph.

    This is the primary contract that metric providers must implement.
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
            A resource can be a Session, AgentCall, LLMCall, etc.
        metric_ids:
            Optional metric name(s) to filter by.  *None* returns all.
        session_id:
            Optional session context filter — only return metrics whose
            owning node belongs to this session.
        recursive:
            If *True*, also match child resources that share the same
            ``sessionId`` (not just the exact ``resource_ids``).
        **kwargs:
            Provider-specific options.

        Returns
        -------
        list[MetricResult]
            Matching metrics, possibly empty.
        """

    # ── metric persistence ────────────────────────────────────────────────

    @abstractmethod
    def save_metrics(self, metrics: MetricResult | list[MetricResult]) -> bool:
        """Persist one or more metric results.

        Parameters
        ----------
        metrics:
            A single result or list of results to save.

        Returns
        -------
        bool
            *True* if the save succeeded, *False* otherwise.
        """

    @abstractmethod
    def clean_metrics(self, session_id: str | None = None) -> int:
        """Delete stored metric nodes.

        Parameters
        ----------
        session_id:
            If provided, only delete metrics attached to resources in
            this session.  If *None*, delete **all** metrics.

        Returns
        -------
        int
            Number of metric nodes deleted.
        """
