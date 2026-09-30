#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Abstract base class for database connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class Connector(ABC):
    """Uniform interface for database connections."""

    # ── lifecycle ─────────────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> None:
        """Open a connection to the database."""

    @abstractmethod
    def close(self) -> None:
        """Close the current connection, releasing resources."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return *True* if the connection is alive."""

    def ensure_connected(self) -> None:
        """Call :meth:`connect` if not already connected."""
        if not self.is_connected():
            self.connect()

    # ── context manager ───────────────────────────────────────────────────

    def __enter__(self):
        self.ensure_connected()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── query execution ───────────────────────────────────────────────────

    @abstractmethod
    def execute(self, query: Any, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a read query and return result rows."""

    @abstractmethod
    def execute_command(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> None:
        """Execute a DDL/DML command (INSERT, DELETE, CREATE TABLE, …)."""
