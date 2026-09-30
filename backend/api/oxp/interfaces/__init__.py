#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Abstract interfaces for pluggable KG providers."""

from oxp.interfaces.data_provider import DataProvider
from oxp.interfaces.kg_provider import KGProvider
from oxp.interfaces.metrics_provider import MetricsProvider
from oxp.interfaces.models import (
    AggregateFacet,
    EdgeFacet,
    MetricRequirements,
    MetricResult,
    NodeFacet,
    NumericMetricResult,
    QueryOptions,
    RetrievalRequest,
    RetrievalScope,
)

__all__ = [
    "DataProvider",
    "AggregateFacet",
    "EdgeFacet",
    "KGProvider",
    "MetricsProvider",
    "MetricRequirements",
    "MetricResult",
    "NodeFacet",
    "NumericMetricResult",
    "QueryOptions",
    "RetrievalRequest",
    "RetrievalScope",
]
