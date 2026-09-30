#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **semantic groups** feature domain."""

from __future__ import annotations

from typing import Any


def get_normal_behaviour_report(semantic_group_id: str) -> tuple[str, dict[str, Any]]:
    """Cypher query for normal behaviour reports (metric type) of a semantic group."""
    query = """
    MATCH (s:SemanticGroup {id: $semantic_group_id})-[:hasNormalBehaviourReport]->(r:NormalBehaviourReport {dataType: "metric"})
    RETURN r.metadata AS metadata, r.centroid AS centroid
    """
    return query, {"semantic_group_id": semantic_group_id}


def get_consistency_report(semantic_group_id: str) -> tuple[str, dict[str, Any]]:
    """Cypher query for consistency reports (metric type) of a semantic group."""
    query = """
    MATCH (s:SemanticGroup {id: $semantic_group_id})-[:hasConsistencyReport]->(r:ConsistencyReport {dataType: "metric"})
    RETURN r.confidenceIndicator AS confidence_indicator, r.metadata AS metadata, r.mean AS mean
    """
    return query, {"semantic_group_id": semantic_group_id}


def get_anomaly_report(semantic_group_id: str) -> tuple[str, dict[str, Any]]:
    """Cypher query for anomaly reports (metric type) with non-empty outliers."""
    query = """
    MATCH (s:SemanticGroup {id: $semantic_group_id})-[:hasAnomalyReport]->(r:AnomalyReport {dataType: "metric"})
    WHERE r.outliersValues <> "[]"
      AND r.outliersValues IS NOT NULL
      AND r.outliersValues <> ""
    RETURN r
    """
    return query, {"semantic_group_id": semantic_group_id}


def get_details(semantic_group_id: str) -> tuple[str, dict[str, Any]]:
    """Cypher query for semantic group node details."""
    query = """
    MATCH (s:SemanticGroup {id: $semantic_group_id})
    RETURN s
    """
    return query, {"semantic_group_id": semantic_group_id}
