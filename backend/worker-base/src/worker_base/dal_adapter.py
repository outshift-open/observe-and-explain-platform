#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

"""Adapter exposing the methods workers used on the old ``KG_DAL`` instance,
delegating to the stateless ``oxp.client.dal`` API functions instead.
"""

from typing import Any, Dict, List

from oxp.client.dal import (
    analysis_pre_check as oxp_api_analysis_pre_check,
)
from oxp.client.dal import (
    generate_insights_from_query as oxp_api_generate_insights_from_query,
)
from oxp.client.dal import (
    get_all_application_ids as oxp_api_get_all_application_ids,
)
from oxp.client.dal import (
    get_analysis_data_for_semantic_group as oxp_api_get_analysis_data_for_semantic_group,
)
from oxp.client.dal import (
    get_mas_name as oxp_api_get_mas_name,
)
from oxp.client.dal import (
    get_semantic_group_hierarchy as oxp_api_get_semantic_group_hierarchy,
)
from oxp.client.dal import (
    get_session_io_embeddings as oxp_api_get_session_io_embeddings,
)
from oxp.client.dal import (
    ingest_anomaly_report as oxp_api_ingest_anomaly_report,
)
from oxp.client.dal import (
    ingest_consistency_report as oxp_api_ingest_consistency_report,
)
from oxp.client.dal import (
    ingest_insights as oxp_api_ingest_insights,
)
from oxp.client.dal import (
    ingest_normal_behaviour_report as oxp_api_ingest_normal_behaviour_report,
)
from oxp.client.dal import (
    wait_for_hierarchical_grouping_unlock as oxp_api_wait_for_hierarchical_grouping_unlock,
)
from oxp.connectors.base import Connector


class OXPApiDALAdapter:
    """Compatibility adapter that exposes the methods used by workers.

    The implementation delegates to API DAL functions instead of KG_DAL methods.
    """

    def __init__(self, connector: Connector):
        self._connector = connector

    def close(self):
        self._connector.close()

    async def wait_for_hierarchical_grouping_unlock(self):
        return await oxp_api_wait_for_hierarchical_grouping_unlock(db=self._connector)

    def analysis_pre_check(
        self,
        group_id: str,
        report_type: str,
        group_hash: str = "",
        session_id: str = "",
    ):
        return oxp_api_analysis_pre_check(
            db=self._connector,
            group_id=group_id,
            report_type=report_type,
            group_hash=group_hash,
            session_id=session_id,
        )

    def get_analysis_data_for_semantic_group(
        self,
        group_id: str,
        group_hash: str = "",
        embedding_model: str = "",
        skip: int = 0,
        limit: int = 0,
    ):
        return oxp_api_get_analysis_data_for_semantic_group(
            db=self._connector,
            group_id=group_id,
            group_hash=group_hash,
            embedding_model=embedding_model,
            skip=skip,
            limit=limit,
        )

    def ingest_consistency_report(
        self,
        group_id: str,
        group_hash: str,
        consistency_report: Any,
        source: Any = None,
    ) -> bool:
        """``consistency_report`` is a
        ``oxp_ontology.models.nodes.consistency_report.ConsistencyReport`` instance.
        ``source`` is the ``dem.consistency.utils.ConsistencySessions`` it was
        computed from, used only to recover non-ontology bookkeeping (metadata)."""
        return oxp_api_ingest_consistency_report(
            db=self._connector,
            group_id=group_id,
            group_hash=group_hash,
            report=consistency_report,
            source=source,
        )

    def ingest_anomaly_report(
        self,
        group_id: str,
        group_hash: str,
        anomaly_report: Any,
        source: Any = None,
    ) -> bool:
        """``anomaly_report`` is a
        ``oxp_ontology.models.nodes.anomaly_report.AnomalyReport`` instance.
        ``source`` is the ``dem.anomaly.AnomalyDetectionSessions`` it was
        computed from, used only to recover non-ontology bookkeeping
        (metadata, inlier/outlier sessions)."""
        return oxp_api_ingest_anomaly_report(
            db=self._connector,
            group_id=group_id,
            group_hash=group_hash,
            report=anomaly_report,
            source=source,
        )

    def ingest_normal_behaviour_report(
        self,
        group_id: str,
        group_hash: str,
        normal_behaviour_report: Any,
        source: Any = None,
    ) -> bool:
        """``normal_behaviour_report`` is a
        ``oxp_ontology.models.nodes.normal_behaviour_report.NormalBehaviourReport`` instance.
        ``source`` is the ``dem.normal_behaviour.utils.NormalBehaviourSessions``
        it was computed from, used only to recover non-ontology bookkeeping
        (metadata)."""
        return oxp_api_ingest_normal_behaviour_report(
            db=self._connector,
            group_id=group_id,
            group_hash=group_hash,
            report=normal_behaviour_report,
            source=source,
        )

    def get_mas_name(self, session_id: str) -> str:
        return oxp_api_get_mas_name(db=self._connector, session_id=session_id)

    def get_semantic_group_hierarchy(
        self,
        embedding_model: str,
        application_id: str,
    ) -> List[Dict[str, Any]]:
        return oxp_api_get_semantic_group_hierarchy(
            db=self._connector,
            embedding_model=embedding_model,
            application_id=application_id,
        )

    def get_session_io_embeddings(self, session_id: str) -> Dict[str, Any]:
        return oxp_api_get_session_io_embeddings(db=self._connector, session_id=session_id)

    def generate_insights_from_query(
        self,
        query: str,
        application_id: str,
    ) -> List[Dict[str, Any]]:
        return oxp_api_generate_insights_from_query(
            db=self._connector,
            query=query,
            application_id=application_id,
        )

    def ingest_insights(self, insights: List[Any]) -> None:
        """``insights`` is a list of ``oxp_ontology.models.nodes.insight.Insight`` instances."""
        return oxp_api_ingest_insights(
            db=self._connector,
            insights=insights,
        )

    def get_all_application_ids(self) -> List[str]:
        return oxp_api_get_all_application_ids(db=self._connector)
