#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Local (in-process, DB-backed) implementation of :class:`OXPAPIClient`.

Usage::

    from oxp.client import LocalClient

    with LocalClient.from_settings() as client:
        sessions = client.list_sessions(limit=10)
        apps     = client.get_applications()
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import Optional

from oxp.client._concepts import ConceptsClient
from oxp.client._kg import KGClient
from oxp.client._labels import LabelsClient
from oxp.client._live_topology import LiveTopologyClient
from oxp.client._metrics import MetricsClient
from oxp.client._semanticgroups import SemanticGroupsClient
from oxp.client._sessions import SessionsClient
from oxp.client._symbolic import SymbolicClient
from oxp.client._ui import UIClient
from oxp.client.base import OXPAPIClient
from oxp.connectors.base import Connector
from oxp.interfaces.metrics_provider import MetricsProvider
from oxp.query_builders.types import Dialect


class LocalClient(
    UIClient,
    KGClient,
    SessionsClient,
    MetricsClient,
    ConceptsClient,
    LabelsClient,
    SemanticGroupsClient,
    SymbolicClient,
    LiveTopologyClient,
    OXPAPIClient,
):
    """Concrete client that queries a local database via :class:`Connector`.

    Domain-specific operations are provided by sub-clients:

    * :class:`~oxp.client._ui.UIClient` — UI operations
    * :class:`~oxp.client._kg.KGClient` — KG (knowledge-graph) operations

    Internally follows a three-step pipeline for every operation:

    1. **Query Builder** → ``oxp.query_builders.<domain>`` → SQLAlchemy ``Select``
    2. **Connector**     → ``self.db.execute(stmt)`` → raw rows
    3. **Model mapping** → Pydantic response models → typed result

    Parameters
    ----------
    db:
        An explicit connector instance.  When *None* the factory in
        ``oxp.repositories`` picks the right backend based on
        the ``OXP_LOCAL`` environment variable.
    metrics_provider:
        An optional :class:`MetricsProvider` instance.  When given, all
        metric operations delegate to this provider. When omitted, a
        OXPMetricsProvider is created using the supplied connector.
    """

    def __init__(
        self,
        db: Optional[Connector] = None,
        metrics_provider: Optional[MetricsProvider] = None,
    ) -> None:
        self._owned_resources = ExitStack()
        if db is not None:
            self.db = db
        else:
            from oxp.repositories import get_otel_repository

            self.db = get_otel_repository()

        if metrics_provider is not None:
            self.metrics_provider = metrics_provider
        else:
            from oxp.providers import OXPMetricsProvider

            self.metrics_provider = OXPMetricsProvider(db=self.db)

    @classmethod
    def from_settings(cls, *, persist_metrics: bool = False) -> LocalClient:
        """Create a client with owned connections from API-library settings.

        Read spans from ClickHouse. When requested, persist metrics through the
        Neo4j provider. Use as a context manager or call close() after use.
        Explicitly injected connectors in LocalClient(db=...) remain caller-owned.
        """
        from oxp.connectors.clickhouse import ClickHouseConnector
        from oxp.core.config import settings

        with ExitStack() as resources:
            db = ClickHouseConnector(
                host=settings.CLICKHOUSE_HOST,
                port=settings.CLICKHOUSE_PORT,
                username=settings.CLICKHOUSE_USERNAME,
                password=settings.CLICKHOUSE_PASSWORD,
                database=settings.CLICKHOUSE_DATABASE,
            )
            resources.callback(db.close)
            provider = None
            if persist_metrics:
                from oxp.connectors.neo4j import Neo4JConnector
                from oxp.providers import OXPMetricsProvider

                kg = Neo4JConnector(
                    host=settings.NEO4J_HOST,
                    port=settings.NEO4J_PORT,
                    username=settings.NEO4J_USERNAME,
                    password=settings.NEO4J_PASSWORD,
                    database=settings.NEO4J_DATABASE,
                )
                resources.callback(kg.close)
                provider = OXPMetricsProvider(db=kg)
            client = cls(db=db, metrics_provider=provider)
            client._owned_resources = resources.pop_all()
            return client

    @property
    def _dialect(self) -> Dialect:
        """Infer the SQL dialect from the connector type."""
        from oxp.connectors.neo4j import Neo4JConnector
        from oxp.connectors.sqlalchemy import SQLAlchemyConnector

        if isinstance(self.db, Neo4JConnector):
            return Dialect.NEO4J
        if isinstance(self.db, SQLAlchemyConnector):
            url = getattr(self.db, "_url", "")
            if "sqlite" in str(url):
                return Dialect.SQLITE
            return Dialect.CLICKHOUSE
        return Dialect.CLICKHOUSE

    # ── lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close only connections created by from_settings(); safe to call twice."""
        self._owned_resources.close()

    # ── common ────────────────────────────────────────────────────────────

    def info(self, domain: str = "oxp") -> str:
        return f"Hello! This is the {domain.upper()} endpoint."
