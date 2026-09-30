#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared data types for provider interfaces.

These types are used across :class:`MetricsProvider`, :class:`KGProvider`,
and :class:`DataProvider` ABCs.  They are intentionally kept as simple
data containers so that provider implementations can construct them
without pulling in heavy dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# ── Metric types ───────────────────────────────────────────────────────────────


@dataclass
class MetricResult:
    """A single computed metric result.

    Attributes
    ----------
    metric_id:
        Unique name of the metric (e.g. ``"duration"``, ``"accuracy"``).
    resource_id:
        ID of the KG resource this metric is attached to (session,
        span, agent call, …).
    provider:
        Name of the provider that produced this result.
    value:
        The metric value.  May be numeric, string, dict, etc.
    timestamp:
        When the metric was computed.
    metadata:
        Arbitrary provider-specific metadata.
    error:
        If non-None, indicates the metric computation failed.
    reasoning:
        Optional textual reasoning / explanation for the value.
    """

    metric_id: str
    resource_id: str
    provider: str = "oxp"
    value: Any = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class NumericMetricResult(MetricResult):
    """A :class:`MetricResult` whose ``value`` is always numeric."""

    value: float = 0.0


@dataclass
class RetrievalScope:
    """Selection scope for a provider retrieval request.

    Supports both single-session and cross-session retrieval by either explicit
    session identifiers, arbitrary resource anchors, or a time interval.
    """

    session_ids: list[str] = field(default_factory=list)
    resource_ids: list[str] = field(default_factory=list)
    start_time: str | None = None
    end_time: str | None = None


@dataclass
class NodeFacet:
    """Describe which KG node sets should be materialized."""

    entity_type: str
    alias: str | None = None
    fields: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None


@dataclass
class EdgeFacet:
    """Describe which KG relationships should be traversed or returned."""

    relation_type: str
    source_entity: str | None = None
    target_entity: str | None = None
    direction: str = "out"
    min_hops: int = 1
    max_hops: int = 1


@dataclass
class AggregateFacet:
    """Describe a provider-side aggregate request."""

    function: str
    field_name: str | None = None
    entity_type: str | None = None
    alias: str | None = None
    group_by: list[str] = field(default_factory=list)


@dataclass
class RetrievalRequest:
    """Faceted V1 retrieval protocol for query-language-agnostic KG access."""

    scope: RetrievalScope = field(default_factory=RetrievalScope)
    nodes: list[NodeFacet] = field(default_factory=list)
    edges: list[EdgeFacet] = field(default_factory=list)
    aggregates: list[AggregateFacet] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None


# ── Metric requirements ──────────────────────────────────────────────────────


@dataclass
class MetricRequirements:
    """Describes what data a metric computation needs.

    Providers use this to decide which data to fetch and return from
    :meth:`DataProvider.fetch`.

    Attributes
    ----------
    needs_session:
        Whether session-level properties are required.
    needs_spans:
        Whether span-level data (agent / LLM / tool calls) is required.
    needs_conversation:
        Whether conversation / State+Transition data is required.
    needs_embeddings:
        Whether embedding vectors are required.
    custom:
        Provider-specific requirements not covered above.
    """

    needs_session: bool = True
    needs_spans: bool = True
    needs_conversation: bool = True
    needs_embeddings: bool = False
    custom: dict[str, Any] = field(default_factory=dict)
    retrieval: RetrievalRequest | None = None


# ── Query options ─────────────────────────────────────────────────────────────


@dataclass
class QueryOptions:
    """SQL-like query options for generic KG node queries.

    Used by :meth:`KGProvider.query_nodes` to translate into the
    backend's native query language (Cypher, SQL, etc.).

    Attributes
    ----------
    filters:
        ``{property_name: value}`` equality filters.  Values may be
        lists for ``IN`` semantics.
    where_clause:
        Raw backend-native WHERE expression (use sparingly).
    columns:
        Specific properties to return.  ``["*"]`` or *None* returns all.
    order_by:
        List of property names to sort by.  Prefix with ``-`` for
        descending (e.g. ``["-timestamp"]``).
    limit:
        Maximum number of results to return.
    """

    filters: dict[str, Any] = field(default_factory=dict)
    where_clause: Optional[str] = None
    columns: Optional[list[str]] = None
    order_by: Optional[list[str]] = None
    limit: Optional[int] = None
