#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Abstract interface for OTEL trace data access."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from oxp.query_builders.types import Dialect


class OtelRepository(ABC):
    """Defines the data-retrieval contract for OTEL traces.

    Each concrete implementation (SQLite, ClickHouse, …) must provide
    these methods so the rest of the application stays backend-agnostic.
    """

    @property
    @abstractmethod
    def dialect(self) -> Dialect:
        """Return the SQL dialect used by this repository."""

    @abstractmethod
    def check_connection(self) -> None:
        """Verify that the underlying database is reachable.

        Raises
        ------
        RuntimeError
            If the connection cannot be established.
        """

    @abstractmethod
    def session_ids(
        self,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
    ) -> list[dict]:
        """Return distinct non-empty session IDs with their earliest timestamp.

        Parameters
        ----------
        start_dt, end_dt:
            Optional ``'YYYY-MM-DD HH:MM:SS'`` boundaries.

        Returns
        -------
        list[dict]
            Each dict has ``{"id": str, "start_timestamp": str}``,
            ordered by earliest timestamp descending.
        """

    @abstractmethod
    def traces(
        self,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
        app_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Return trace summaries grouped by trace_id.

        Returns
        -------
        list[dict]
            Each dict has ``{"trace_id": str, "application_id": str,
            "start_time": str, "end_time": str}``,
            ordered by earliest timestamp descending.
        """

    @abstractmethod
    def application_ids(
        self,
        start_dt: Optional[str] = None,
        end_dt: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Return distinct non-empty application IDs with their earliest timestamp.

        Same contract as :meth:`session_ids` but for the ``application_id`` column.
        """

    @abstractmethod
    def seed(self, csv_path: str) -> None:
        """Seed the otel_traces table from a CSV file (if not already seeded).

        The CSV is expected to have a ClickHouse type-hint row as row 2
        (immediately after the header), which must be skipped.
        """

    @abstractmethod
    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> list:
        """Execute an arbitrary SQL query and return the result rows."""
