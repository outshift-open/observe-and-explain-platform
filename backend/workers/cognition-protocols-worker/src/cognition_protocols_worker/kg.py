"""The platform's knowledge-graph providers, configured the way the platform's workers are.

Workers read and write the graph only through these: ``OXPKGProvider`` to read a
session, ``OXPCognitionProtocolReportProvider`` to write the Cognition protocol reports. Nothing here, or in the
workers, holds a Cypher query.
"""

from __future__ import annotations

import os
from typing import Any


def get_connector() -> Any:
    """The platform's shared Neo4j connector, to hand to a provider.

    It reads ``NEO4J_URI``, ``NEO4J_USERNAME`` and ``NEO4J_PASSWORD``. The compose
    stack gives the combined ``NEO4J_AUTH`` (``user/password``) instead, which the
    workers' own CLIs accept, so it is split here when the separate ones are unset.
    """
    from worker_base.utils import resolve_neo4j_auth

    user, password = resolve_neo4j_auth()
    if user:
        os.environ.setdefault("NEO4J_USERNAME", user)
    if password:
        os.environ.setdefault("NEO4J_PASSWORD", password)

    from oxp.dependencies import get_neo4j_connector

    return get_neo4j_connector()


def reader() -> Any:
    """The provider that reads a session's spans (``OXPKGProvider``)."""
    from oxp.providers import OXPKGProvider

    return OXPKGProvider(db=get_connector())


def writer() -> Any:
    """The provider that writes the Cognition protocol reports (``OXPCognitionProtocolReportProvider``)."""
    from oxp.providers import OXPCognitionProtocolReportProvider

    return OXPCognitionProtocolReportProvider(db=get_connector())


def fetch_session(provider: Any, session_id: str) -> dict[str, Any]:
    """A session's spans (agent, LLM and tool calls with their content), as MCE metrics see them."""
    return provider.fetch(session_id, None)
