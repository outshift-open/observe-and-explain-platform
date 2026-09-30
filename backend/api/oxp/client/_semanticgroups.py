#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Semantic-groups-domain methods for :class:`LocalClient`."""

from __future__ import annotations

import json
import logging
from typing import Any

from oxp.connectors.base import Connector
from oxp.connectors.neo4j import (
    SEMANTICGROUP_NODE_CHILDREN_NODES,
    SEMANTICGROUP_NODE_GROUP_NAME,
    SEMANTICGROUP_NODE_GROUP_SUMMARY,
    SEMANTICGROUP_NODE_ID,
    SEMANTICGROUP_NODE_N_SESSIONS,
    SEMANTICGROUP_NODE_SESSION_IDS,
)
from oxp.core.exceptions import DatabaseError, NotFoundError
from oxp.models.otel_traces import (
    SemanticgroupAnomalyItem,
    SemanticgroupAnomalyResponse,
    SemanticgroupConsistencyItem,
    SemanticgroupConsistencyResponse,
    SemanticgroupDetailsResponse,
    SemanticgroupNormalBehaviorItem,
    SemanticgroupNormalBehaviorResponse,
)
from oxp.query_builders import semanticgroups as sg_queries

logger = logging.getLogger(__name__)


class SemanticGroupsClient:
    """Semantic-group operations mixed into :class:`LocalClient`."""

    db: Connector

    @staticmethod
    def _execute_stmt(db: Connector, stmt: Any):
        """Execute either a single statement or a ``(query, params)`` pair."""
        if isinstance(stmt, tuple) and len(stmt) == 2:
            query, params = stmt
            return db.execute(query, params)
        return db.execute(stmt)

    def get_semanticgroup_normal_behavior(
        self,
        *,
        semanticgroup_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupNormalBehaviorResponse:
        """Return normal behaviour report for a semantic group."""
        stmt = sg_queries.get_normal_behaviour_report(semanticgroup_id)
        try:
            rows = self._execute_stmt(self.db, stmt)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get normal behaviour report for '{semanticgroup_id}': {exc}"
            ) from exc

        if not rows:
            raise NotFoundError(
                f"No normal behaviour report found for semantic group: {semanticgroup_id}"
            )

        reports = [
            SemanticgroupNormalBehaviorItem(
                metadata=row["metadata"],
                centroid=row["centroid"],
            )
            for row in rows
        ]
        return SemanticgroupNormalBehaviorResponse(reports=reports)

    def get_semanticgroup_consistency_report(
        self,
        *,
        semanticgroup_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupConsistencyResponse:
        """Return consistency report for a semantic group."""
        stmt = sg_queries.get_consistency_report(semanticgroup_id)
        try:
            rows = self._execute_stmt(self.db, stmt)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get consistency report for '{semanticgroup_id}': {exc}"
            ) from exc

        if not rows:
            raise NotFoundError(
                f"No consistency report found for semantic group: {semanticgroup_id}"
            )

        reports = [
            SemanticgroupConsistencyItem(
                metadata=row["metadata"],
                mean=row["mean"],
                confidence_indicator=row["confidence_indicator"],
            )
            for row in rows
        ]
        return SemanticgroupConsistencyResponse(reports=reports)

    def get_semanticgroup_anomaly_report(
        self,
        *,
        semanticgroup_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupAnomalyResponse:
        """Return anomaly report for a semantic group."""
        stmt = sg_queries.get_anomaly_report(semanticgroup_id)
        try:
            rows = self._execute_stmt(self.db, stmt)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get anomaly report for '{semanticgroup_id}': {exc}"
            ) from exc

        if not rows:
            raise NotFoundError(
                f"No anomaly report found for semantic group: {semanticgroup_id}"
            )

        reports = [
            SemanticgroupAnomalyItem(
                metadata=row["r"]["metadata"],
                outliers_values=json.loads(row["r"]["outliersValues"]),
            )
            for row in rows
        ]
        return SemanticgroupAnomalyResponse(reports=reports)

    def get_semanticgroup_details(
        self,
        *,
        semanticgroup_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupDetailsResponse:
        """Return details for a semantic group."""
        stmt = sg_queries.get_details(semanticgroup_id)
        try:
            rows = self._execute_stmt(self.db, stmt)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get details for '{semanticgroup_id}': {exc}"
            ) from exc

        if not rows:
            raise NotFoundError(f"Semantic group not found: {semanticgroup_id}")

        node = rows[0]["s"]
        return SemanticgroupDetailsResponse(
            children_nodes=node[SEMANTICGROUP_NODE_CHILDREN_NODES],
            group_name=node[SEMANTICGROUP_NODE_GROUP_NAME],
            group_summary=node[SEMANTICGROUP_NODE_GROUP_SUMMARY],
            id=node[SEMANTICGROUP_NODE_ID],
            n_sessions=node[SEMANTICGROUP_NODE_N_SESSIONS],
            session_ids=node[SEMANTICGROUP_NODE_SESSION_IDS],
        )
