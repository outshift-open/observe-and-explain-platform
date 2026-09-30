#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared helpers for endpoint modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from oxp.client.base import OXPAPIClient
from oxp.connectors.base import Connector as _Connector
from oxp.models.otel_traces import Filters

if TYPE_CHECKING:
    from oxp.interfaces.metrics_provider import MetricsProvider


def build_filters(request: Request) -> Filters:
    """Parse query-string parameters into a :class:`Filters` instance."""
    params = dict(request.query_params)
    return Filters(**{k: v for k, v in params.items() if k in Filters.model_fields})


# ── Client registry (one LocalClient per connector) ─────────────────────────

_clients: dict[int, "OXPAPIClient"] = {}


def get_client(
    api_client: _Connector | None = None,
    metrics_provider: MetricsProvider | None = None,
) -> OXPAPIClient:
    """Return (and lazily create) a :class:`LocalClient` for *api_client*.

    Each distinct connector instance gets its own ``LocalClient`` so that
    SQL-backed and Neo4j-backed endpoints don't share a single client.

    Parameters
    ----------
    api_client:
        Database connector.  *None* → use the default repository.
    metrics_provider:
        Optional :class:`MetricsProvider` to inject into the client.
        When given, the client delegates metric operations to it.
    """
    key = id(api_client) if api_client is not None else 0
    if key not in _clients:
        from oxp.client.local import LocalClient

        _clients[key] = (
            LocalClient(db=api_client, metrics_provider=metrics_provider)
            if api_client is not None
            else LocalClient(metrics_provider=metrics_provider)
        )
    else:
        # Update provider on an existing client if a new one is supplied
        if metrics_provider is not None:
            _clients[key].metrics_provider = metrics_provider  # type: ignore[attr-defined]
    return _clients[key]


def reset_client() -> None:
    """Force re-creation of all shared clients (used by tests)."""
    _clients.clear()
