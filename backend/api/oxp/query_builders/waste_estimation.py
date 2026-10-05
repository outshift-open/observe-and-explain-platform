#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for waste-estimation and insights endpoints."""

from __future__ import annotations

from typing import Any


def waste_estimations_query(limit: int) -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (n:WasteEstimation)
    RETURN properties(n) AS waste_estimation
    LIMIT $limit
    """
    return query, {"limit": limit}


def top_wasteful_sessions_query(
    threshold: float,
    limit: int,
    start_time: int | None,
    end_time: int | None,
    application_name: str,
) -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (n:WasteEstimation)
    WHERE n.estimatedWaste > $threshold
    MATCH (s:Session {sessionId: n.sessionId})
    WHERE ($start_time IS NULL OR s.startTime >= $start_time)
      AND ($end_time IS NULL OR s.startTime <= $end_time)
      AND EXISTS {
        MATCH (s)-[:executesSession]->(:MAS {id: $application_name})
      }
    OPTIONAL MATCH (g:SemanticGroup)-[:containsSession]->(s)
    WITH n, s, head(collect(g.groupName)) AS semanticGroup,
         head(collect(g.id)) AS semanticGroupId
    RETURN properties(n) AS waste_estimation,
           semanticGroup,
           semanticGroupId
    ORDER BY n.estimatedWaste DESC
    LIMIT $limit
    """
    return query, {
        "threshold": threshold,
        "limit": limit,
        "start_time": start_time,
        "end_time": end_time,
        "application_name": application_name,
    }


def waste_estimations_semantic_groups_query() -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (sg:SemanticGroup {childrenNodes: []})
    OPTIONAL MATCH (sg)-[:containsSession]->(s:Session)
    WITH sg, collect(DISTINCT s.sessionId) AS sessionIds
    UNWIND sessionIds AS sid
    OPTIONAL MATCH (w:WasteEstimation {sessionId: sid})
    WITH sg, sum(COALESCE(w.actualCost, 0)) AS totalCost
    RETURN sg.id AS groupId, sg.groupName AS groupName, totalCost
    ORDER BY totalCost DESC
    """
    return query, {}


def cost_efficiency_grouped_sessions_query(
    application_name: str,
) -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (sg:SemanticGroup {childrenNodes: []})-[:containsSession]->(s:Session)
    MATCH (w:WasteEstimation {sessionId: s.sessionId})
    WHERE w.actualCost <> 0
      AND EXISTS {
        MATCH (s)-[:executesSession]->(:MAS {id: $application_name})
      }
    RETURN s.sessionId AS sessionId,
           s.startTime AS startTime,
           sg.groupName AS groupName,
           sg.id AS groupId,
           w.costEfficiency AS costEfficiency,
           w.actualCost AS actualCost,
           w.estimatedWaste AS estimatedWaste
    ORDER BY sg.groupName, s.sessionId
    """
    return query, {"application_name": application_name}


def wasted_resources_features_score_query(
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (s:WastedResourcesFeatureScore)
    WHERE s.sessionId = $session_id
    WITH s.qualityTarget AS qt, s
    ORDER BY qt, s.rank ASC
    WITH qt, collect({
        qualityTarget: qt,
        rank: s.rank,
        feature: s.featureName,
        score: s.score
    }) AS items
    WITH qt, items, size(items) AS total
    WITH qt,
      CASE WHEN total <= 10 THEN items
        ELSE items[..5] + items[total-5..]
      END AS selected
    UNWIND selected AS row
    RETURN row AS item
    ORDER BY item.qualityTarget, item.rank ASC
    """
    return query, {"session_id": session_id}


def semantic_groups_insights_query(
    start_time: int | None,
    end_time: int | None,
    application_name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (s:SemanticGroup)-[:hasInsight]->(i:Insight)
    WHERE ($start_time IS NULL OR datetime(i.createdAt) >= datetime({epochSeconds: $start_time}))
      AND ($end_time IS NULL OR datetime(i.createdAt) <= datetime({epochSeconds: $end_time}))
      AND ($application_name IS NULL OR EXISTS {
        MATCH (:MAS {masName: $application_name})-[:containsSemanticGroup]->(s)
      })
    RETURN s.groupName AS groupName,
           s.groupSummary AS groupSummary,
           s.id AS groupId,
           s.sessionIds AS sessionIds,
           toString(i.createdAt) AS createdAt,
           i.description AS description,
           i.id AS insightId,
           i.name AS name,
           i.labels AS labels,
           i.priority AS priority,
           i.targetNodeId AS targetNodeId
    ORDER BY i.priority DESC
    """
    return query, {
        "start_time": start_time,
        "end_time": end_time,
        "application_name": application_name,
    }


def sessions_insights_query(
    start_time: int | None,
    end_time: int | None,
    semantic_group_id: str | None,
    limit: int,
    offset: int,
    application_name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (s:Session)-[:hasInsight]->(i:Insight)
    WHERE ($start_time IS NULL OR datetime(i.createdAt) >= datetime({epochSeconds: $start_time}))
      AND ($end_time IS NULL OR datetime(i.createdAt) <= datetime({epochSeconds: $end_time}))
      AND ($application_name IS NULL OR EXISTS {
        MATCH (s)-[:executesSession]->(:MAS {id: $application_name})
      })
      AND ($semantic_group_id IS NULL OR EXISTS {
        MATCH (:SemanticGroup {id: $semantic_group_id})-[:containsSession*1..]->(s)
      })
    RETURN s.duration AS duration,
           s.endTime AS endTime,
           s.sessionId AS sessionId,
           s.startTime AS startTime,
           toString(i.createdAt) AS createdAt,
           i.description AS description,
           i.id AS insightId,
           i.name AS name,
           i.labels AS labels,
           i.priority AS priority,
           i.targetNodeId AS targetNodeId
    ORDER BY i.priority ASC
    SKIP $offset LIMIT $limit
    """
    return query, {
        "start_time": start_time,
        "end_time": end_time,
        "semantic_group_id": semantic_group_id,
        "application_name": application_name,
        "offset": offset,
        "limit": limit,
    }


def session_insights_query(
    session_id: str,
    start_time: int | None,
    end_time: int | None,
    limit: int,
    offset: int,
) -> tuple[str, dict[str, Any]]:
    query = """
    MATCH (s:Session)-[:hasInsight]->(i:Insight)
    WHERE s.sessionId = $session_id
      AND ($start_time IS NULL OR datetime(i.createdAt) >= datetime({epochSeconds: $start_time}))
      AND ($end_time IS NULL OR datetime(i.createdAt) <= datetime({epochSeconds: $end_time}))
    RETURN s.duration AS duration,
           s.endTime AS endTime,
           s.sessionId AS sessionId,
           s.startTime AS startTime,
           toString(i.createdAt) AS createdAt,
           i.description AS description,
           i.id AS insightId,
           i.name AS name,
           i.labels AS labels,
           i.priority AS priority,
           i.targetNodeId AS targetNodeId
    ORDER BY i.priority ASC
    SKIP $offset LIMIT $limit
    """
    return query, {
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "offset": offset,
        "limit": limit,
    }
