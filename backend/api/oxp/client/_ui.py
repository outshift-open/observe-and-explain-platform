#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""UI-domain methods for :class:`LocalClient`."""

from __future__ import annotations

from typing import Optional

from oxp.client.application_charts import (
    _get_application_charts,
)
from oxp.client.applications import (
    _get_application_agent_tools,
    _get_application_agents,
    _get_application_details,
    _get_application_names,
    _get_application_semanticgroup_impact_assessment,
    _get_application_semanticgroups,
    _get_application_sessions,
    _get_application_sessions_with_stateful_eval_multiquery,
    _get_application_sessions_with_stateful_eval,
    _get_application_topology,
    _get_applications,
    _get_applications_multiquery,
    _get_applications_from_clickhouse,
    _get_applications_from_clickhouse_multiquery,
)
from oxp.client.sessions import (
    _get_children_spans,
    _get_session_agent_details,
    _get_session_agents,
    _get_session_conversation,
    _get_session_execution_graph,
    _get_session_impact_assessment,
    _get_session_latent_space,
    _get_session_timeline,
    _get_session_timeline_waterfall,
    _get_session_trajectory,
    _get_sessions,
)
from oxp.client.agentic_protocols import (
    _get_agentic_protocols_metrics,
)
from oxp.client.spans import (
    _get_spans,
)
from oxp.connectors.base import Connector
from oxp.models.otel_traces import (
    AgentConversationResponse,
    AgentDetailsResponse,
    AgenticProtocolsMetricsResponse,
    ApplicationAgentToolsResponse,
    ApplicationNamesResponse,
    ApplicationsResponse,
    CollectByApplicationResponse,
    GraphResponse,
    ImpactAssessmentResponse,
    LatentSpaceResponse,
    MonitorApplicationLevelData,
    MonitorByApplicationResponse,
    SemanticgroupsResponse,
    SpanDetailsResponse,
    TracesResponse,
    UniqueAgentPerSession,
    WaterfallResponse,
    WaterfallSpan,
)
from oxp.query_builders.types import Dialect


class UIClient:
    """UI operations mixed into :class:`LocalClient`."""

    db: Connector
    _dialect: Dialect

    # ── Sessions ─────────────────────────────────────────────────────────

    def get_sessions(
        self,
        *,
        app_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TracesResponse:
        return _get_sessions(
            self.db,
            self._dialect,
            app_name=app_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_session_agents(
        self,
        *,
        session_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UniqueAgentPerSession]:
        return _get_session_agents(
            self.db,
            self._dialect,
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_session_agent_details(
        self,
        *,
        session_id: str,
        agent_id: str,
    ) -> AgentDetailsResponse:
        """Return detailed information about an agent in a session."""
        return _get_session_agent_details(
            self.db,
            self._dialect,
            session_id=session_id,
            agent_id=agent_id,
        )

    def get_session_impact_assessment(
        self,
        *,
        session_id: str,
    ) -> ImpactAssessmentResponse:
        """Return impact assessment for a session."""
        return _get_session_impact_assessment(
            self.db,
            self._dialect,
            session_id=session_id,
        )

    def get_session_timeline_waterfall(
        self,
        *,
        session_id: str,
    ) -> WaterfallResponse:
        """Build a waterfall span tree for a session."""
        return _get_session_timeline_waterfall(
            self.db,
            self._dialect,
            session_id=session_id,
        )

    def get_session_timeline(
        self,
        *,
        session_id: str,
        level: Optional[str] = None,
    ) -> GraphResponse:
        """Build a timeline for a session."""
        return _get_session_timeline(
            self.db,
            self._dialect,
            session_id=session_id,
            level=level,
        )

    def get_session_trajectory(
        self,
        *,
        session_id: str,
    ) -> GraphResponse:
        """Build an execution graph for a session."""
        return _get_session_trajectory(
            self.db,
            self._dialect,
            session_id=session_id,
        )

    def get_session_execution_graph(
        self,
        *,
        session_id: str,
    ) -> GraphResponse:
        """Build an execution graph for a session."""
        return _get_session_execution_graph(
            self.db,
            self._dialect,
            session_id=session_id,
        )

    def get_session_conversation(
        self,
        *,
        session_id: str,
    ) -> AgentConversationResponse:
        """Return the ordered list of agent-level turns for a session."""
        return _get_session_conversation(
            self.db,
            self._dialect,
            session_id=session_id,
        )

    def get_session_latent_space(
        self,
        *,
        session_id: str,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
    ) -> LatentSpaceResponse:
        """Project state embeddings to 2D latent space using UMAP."""
        return _get_session_latent_space(
            self.db,
            self._dialect,
            session_id=session_id,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
        )

    # ── Spans ────────────────────────────────────────────────────────────

    def get_spans(self, *, span_id: str) -> SpanDetailsResponse:
        """Return detailed information about a single span."""
        return _get_spans(
            self.db,
            self._dialect,
            span_id=span_id,
        )

    # ── Applications ─────────────────────────────────────────────────────

    def get_application_names(
        self,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationNamesResponse:
        """Return the list of known application names."""
        return _get_application_names(
            self.db,
            self._dialect,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_applications_from_clickhouse_multiquery(
        self,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationsResponse:
        """Return the list of applications with agents, LLMs, cost, and performance."""
        return _get_applications_from_clickhouse_multiquery(
            self.db,
            self._dialect,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_applications_multiquery(
        self,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationsResponse:
        """Return the list of applications using multiple Neo4j queries."""
        return _get_applications_multiquery(
            self.db,
            self._dialect,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_applications_from_clickhouse(
        self,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationsResponse:
        """Return the list of applications using optimized ClickHouse queries."""
        return _get_applications_from_clickhouse(
            self.db,
            self._dialect,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_applications(
        self,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ApplicationsResponse:
        """Return applications using the appropriate backend for the active dialect."""
        if self._dialect == Dialect.CLICKHOUSE:
            return _get_applications_from_clickhouse(
                self.db,
                self._dialect,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )
        return _get_applications(
            self.db,
            self._dialect,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_application_details(
        self,
        *,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
        given_session_ids: Optional[list[str]] = None,
    ) -> MonitorApplicationLevelData:
        """Return application-level monitoring data."""
        return _get_application_details(
            self.db,
            self._dialect,
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
            given_session_ids=given_session_ids,
        )

    def get_application_agents(
        self,
        *,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
        given_session_ids: Optional[list[str]] = None,
    ) -> MonitorByApplicationResponse:
        """Return per-agent monitoring data for an application."""
        return _get_application_agents(
            self.db,
            self._dialect,
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
            given_session_ids=given_session_ids,
        )

    def get_application_sessions(
        self,
        *,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> CollectByApplicationResponse:
        """Return session-level data for an application."""
        return _get_application_sessions(
            self.db,
            self._dialect,
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
        )

    def get_application_sessions_with_stateful_eval_multi_query(
        self,
        *,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> CollectByApplicationResponse:
        """Return session-level data including stateful evaluation metric."""
        return _get_application_sessions_with_stateful_eval_multiquery(
            self.db,
            self._dialect,
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
            get_session_metrics_fn=self.get_session_metrics,
        )

    def get_application_sessions_with_stateful_eval(
        self,
        *,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
        semantic_group_id: str = "",
    ) -> CollectByApplicationResponse:
        """Return session-level data using one query for stateful eval + metrics."""
        return _get_application_sessions_with_stateful_eval(
            self.db,
            self._dialect,
            application_id=application_id,
            start_time=start_time,
            end_time=end_time,
            semantic_group_id=semantic_group_id,
        )

    def get_application_charts(
        self,
        *,
        application_id: str,
        agent_id: str,
        chart_type: str,
        start_time: str = "",
        end_time: str = "",
        given_session_ids: Optional[list[str]] = None,
    ):
        """Return chart data for an application by chart type."""
        return _get_application_charts(
            self.db,
            self._dialect,
            application_id=application_id,
            agent_id=agent_id,
            chart_type=chart_type,
            start_time=start_time,
            end_time=end_time,
            given_session_ids=given_session_ids,
        )

    def get_application_topology(
        self,
        *,
        application_id: str,
    ) -> dict:
        """Return the static topology for an application from the DB."""
        return _get_application_topology(
            self.db,
            self._dialect,
            application_id=application_id,
        )

    def get_application_agent_tools(
        self,
        *,
        application_id: str,
    ) -> ApplicationAgentToolsResponse:
        """Return each agent's tools for an application (Neo4j-backed)."""
        return _get_application_agent_tools(
            self.db,
            application_id=application_id,
        )

    # ── Agentic protocols ─────────────────────────────────────────────────

    def get_agentic_protocols_metrics(
        self,
        *,
        application: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> AgenticProtocolsMetricsResponse:
        """Return SLIM agentic-protocol metrics for *application*."""
        return _get_agentic_protocols_metrics(
            self.db,
            application=application,
            start_time=start_time,
            end_time=end_time,
        )

    def get_application_semanticgroups(
        self,
        *,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupsResponse:
        """Return all semantic groups for an application."""
        return _get_application_semanticgroups(
            self.db,
            self._dialect,
            application_id=application_id,
        )

    def get_application_semanticgroups_table(
        self,
        *,
        application_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> SemanticgroupsResponse:
        """Return leaf semantic groups for an application."""
        return _get_application_semanticgroups(
            self.db,
            self._dialect,
            application_id=application_id,
            only_leaf_nodes=True,
        )

    def get_application_semanticgroup_impact_assessment(
        self,
        *,
        application_id: str,
        semanticgroup_id: str,
        start_time: str = "",
        end_time: str = "",
    ) -> ImpactAssessmentResponse:
        """Return impact assessment for a semantic group."""
        return _get_application_semanticgroup_impact_assessment(
            self.db,
            self._dialect,
            application_id=application_id,
            semanticgroup_id=semanticgroup_id,
            start_time=start_time,
            end_time=end_time,
        )

    # ── Static helpers (kept for backward-compat references) ─────────────

    @staticmethod
    def _get_children_spans(
        parent_id: str,
        parent_child_map: dict[str, list[dict]],
        used_node_map: dict[str, bool],
    ) -> tuple[list[WaterfallSpan], str, str]:
        """Recursively build child spans for a given parent."""
        return _get_children_spans(parent_id, parent_child_map, used_node_map)
