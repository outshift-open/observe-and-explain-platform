#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""KGProvider — abstract interface for generic knowledge-graph node queries.

Implementations handle:
- Querying nodes by entity type with SQL-like options (filters, sorting, etc.)
- Listing sessions, agents, and LLM calls
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from oxp.interfaces.models import QueryOptions


class KGProvider(ABC):
    """Abstract interface for generic KG node access.

    This is the contract for providers that expose arbitrary KG node
    queries with SQL-like filtering, sorting, and projection.

    Example
    -------
    ::

        class Neo4jRawProvider(KGProvider):
            def query_nodes(self, entity_type, options=None):
                # translate QueryOptions → Cypher MATCH/WHERE/RETURN
                ...
    """

    # ── generic node queries ──────────────────────────────────────────────

    @abstractmethod
    def query_nodes(
        self,
        entity_type: str,
        options: QueryOptions | None = None,
    ) -> list[dict[str, Any]]:
        """Query KG nodes of the given type with SQL-like options.

        Parameters
        ----------
        entity_type:
            Node label / type to query (e.g. ``"Session"``,
            ``"AgentCall"``, ``"*"`` for all).
        options:
            Filtering, sorting, projection, and limit options.
            *None* uses sensible defaults.
        """

    # ── convenience listing methods ───────────────────────────────────────

    @abstractmethod
    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List available sessions in the KG.

        Parameters
        ----------
        limit:
            Maximum number of sessions to return.

        Returns
        -------
        list[dict]
            Each dict should contain at least ``session_id``,
            ``name``, and ``timestamp`` keys.
        """

    @abstractmethod
    def list_agents(self, session_id: str) -> list[dict[str, Any]]:
        """List agents (AgentCalls) in a given session.

        Parameters
        ----------
        session_id:
            The session to list agents for.
        """

    @abstractmethod
    def list_llm_calls(self, session_id: str) -> list[dict[str, Any]]:
        """List LLM calls in a given session.

        Parameters
        ----------
        session_id:
            The session to list LLM calls for.

        """
