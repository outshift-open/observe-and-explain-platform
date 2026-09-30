#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Abstract base client for the OXP API.

``OXPAPIClient`` is the single type that consumers depend on.
Concrete back-ends (:class:`LocalClient`, a future ``RemoteClient``, …)
inherit from this class and implement the abstract methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OXPAPIClient(ABC):
    """Base class for all OXP API clients.

    Concrete back-ends implement the abstract methods below.  Callers
    can also use the context-manager protocol::

        with LocalClient() as client:
            sessions = client.get_sessions(app_name="my-app")
    """

    # ── lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:  # noqa: B027 — intentionally empty
        """Release resources held by this client.  Override if needed."""

    def __enter__(self):
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── common ────────────────────────────────────────────────────────────

    @abstractmethod
    def info(self, domain: str = "oxp") -> str:
        """Return a human-readable greeting for *domain*."""

    # ── UI operations ─────────────────────────────────────────────────────

    # ── KG operations ─────────────────────────────────────────────────────

    # ── Metric operations ─────────────────────────────────────────────────

    # ── Feature operations ────────────────────────────────────────────────
