#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MetricLayer(Enum):
    RAW = "Raw"  # L0  — unprocessed OTel / telemetry data
    EXECUTION = (
        "Execution"  # L0.5 — ontology-structured execution data (Session, LLMCall …)
    )
    DERIVED = "Derived"  # L1  — computed from raw/execution data
    AGGREGATION = "Aggregation"  # L1.5 — virtual (aggregates of other metrics)
    STATISTICAL = "Statistical"  # L2  — vector / embedding / geometric metrics
    SEMANTIC = "Semantic"  # L3  — concept-level semantic metrics
    CAUSAL = "Causal"  # L4  — causal inference metrics
    GOVERNANCE = "Governance"  # L5  — policy / safety / bias metrics


class MetricNature(Enum):
    DETERMINISTIC = "Deterministic"
    STOCHASTIC = "Stochastic"
    GEOMETRIC = "Geometric"
    TOPOLOGICAL = "Topological"


class MetricScope(Enum):
    TOKEN = "Token"
    SPAN = "Span"
    TRACE = "Trace"
    SESSION = "Session"
    AGENT = "Agent"
    MAS = "MAS"
    EXECUTION_ELEMENT = (
        "ExecutionElement"  # Applies to all of the above (abstract base)
    )


class MetricImplementationType(Enum):
    ABSTRACT = "Abstract"
    CONCRETE = "Concrete"
    VIRTUAL = "Virtual"


@dataclass
class RetrievalScope:
    """Selection scope for a provider retrieval request.

    A retrieval may target one or more explicit session IDs, arbitrary anchor
    resource IDs, or a time interval for cross-session computations.
    """

    session_ids: list[str] = field(default_factory=list)
    resource_ids: list[str] = field(default_factory=list)
    start_time: str | None = None
    end_time: str | None = None


@dataclass
class NodeFacet:
    """Describe which nodes should be retrieved from the KG."""

    entity_type: str
    alias: str | None = None
    fields: list[str] = field(default_factory=list)
    filters: dict[str, object] = field(default_factory=dict)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None


@dataclass
class EdgeFacet:
    """Describe which relations should be traversed or materialized."""

    relation_type: str
    source_entity: str | None = None
    target_entity: str | None = None
    direction: str = "out"
    min_hops: int = 1
    max_hops: int = 1


@dataclass
class AggregateFacet:
    """Describe a provider-side aggregate to compute if supported."""

    function: str
    field_name: str | None = None
    entity_type: str | None = None
    alias: str | None = None
    group_by: list[str] = field(default_factory=list)


@dataclass
class RetrievalRequest:
    """Faceted V1 retrieval protocol for query-language-agnostic KG access.

    Providers should translate this declarative request into as few backend
    queries as practical, ideally a single request when the backend supports it.
    """

    scope: RetrievalScope = field(default_factory=RetrievalScope)
    nodes: list[NodeFacet] = field(default_factory=list)
    edges: list[EdgeFacet] = field(default_factory=list)
    aggregates: list[AggregateFacet] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None


@dataclass
class MetricRequirements:
    """
    Defines the data subset required from the KG (Semantic Graph).
    """

    # 1. Semantic Entities (Ontology Classes)
    required_entities: list[str] = field(default_factory=list)

    # 2. Field Projections
    text_fields: list[str] = field(default_factory=list)
    vector_fields: list[str] = field(default_factory=list)
    scalar_fields: list[str] = field(default_factory=list)

    # 3. Graph Context
    include_edges: bool = False
    allowed_relations: list[str] = field(default_factory=list)

    # 4. Evaluation Flags
    ground_truth: bool = False

    # 5. Retrieval Protocol
    retrieval: RetrievalRequest | None = None


_AGG_OPS = ("avg", "max", "min", "sum")


def format_metric_display_name(metric_id: str) -> str:
    """Convert an internal metric_id to a human-readable display name.

    Aggregate IDs (``avg_X``, ``max_X`` …) are rendered as templated syntax
    (``Avg<X>``).  All other IDs are returned unchanged.

    This is the single source of truth for display-name formatting; both
    ``MetricResult.display_name`` and ``MetricMetadata.get_display_name``
    delegate here.
    """
    for op in _AGG_OPS:
        if metric_id.startswith(f"{op}_"):
            base = metric_id[len(op) + 1 :]
            return f"{op.capitalize()}<{base}>"
    return metric_id


@dataclass
class MetricMetadata:
    """
    Metadata defining a metric's characteristics in the MCE Catalog.
    Aligned with metrics.json and the MAS ontology.
    """

    name: str
    description: str
    layer: MetricLayer
    nature: MetricNature
    scope: MetricScope
    ontology_class: str
    version: str = "1.0.0"
    attachment_point: str | None = None
    display_name: str | None = None
    target_types: set[str] = field(default_factory=set)
    dependencies: list[str] = field(default_factory=list)
    provider: str = ""
    implementation_type: MetricImplementationType = MetricImplementationType.CONCRETE

    def get_display_name(self) -> str:
        """Human-readable name. Delegates to module-level format_metric_display_name()."""
        return self.display_name or format_metric_display_name(self.name)

    def to_dict(self):
        return {
            "Name": self.name,
            "Version": self.version,
            "Description": self.description,
            "Layer": self.layer.value,
            "Nature": self.nature.value,
            "Scope": self.scope.value,
            "Dependencies": self.dependencies,
            "Implementation Type": self.implementation_type.value,
        }
