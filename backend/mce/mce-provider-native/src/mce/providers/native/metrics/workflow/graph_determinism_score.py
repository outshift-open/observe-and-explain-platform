#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from itertools import combinations
from typing import Any
import networkx as nx
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry


class GraphDeterminismScore(Metric):
    """Measures mean edit distance in execution paths across sessions."""

    metadata = SpecRegistry.require("GraphDeterminismScore").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements()

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        sessions = context.get("sessions") or context.get("session_set")
        if not isinstance(sessions, list) or not sessions:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=-1,
                metric_class=self.ontology_class,
                reasoning="No session set provided for population metric.",
            )

        graphs = []
        entities_involved: list[str] = []

        for session in sessions:
            # We expect session objects or minimal wrappers
            # Assume session has .spans or .agent_transitions

            # Reconstruct flow from spans if possible
            session_spans = getattr(session, "spans", []) if session else []
            filtered_names = []

            for span in session_spans:
                # Extract names robustly
                name = None
                if isinstance(span, dict):
                    name = (
                        span.get("toolName")
                        or span.get("agentName")
                        or span.get("tool_name")
                        or span.get("agent_id")
                    )
                else:
                    name = (
                        getattr(span, "toolName", None)
                        or getattr(span, "agentName", None)
                        or getattr(span, "tool_name", None)
                        or getattr(span, "agent_id", None)
                    )

                if name:
                    filtered_names.append(str(name))
                    entities_involved.append(str(name))

            edges = []
            for idx in range(len(filtered_names) - 1):
                edges.append((filtered_names[idx], filtered_names[idx + 1]))
            graphs.append(edges)

        nx_graphs = []
        for edges in graphs:
            graph = nx.DiGraph()
            graph.add_edges_from(edges)
            nx_graphs.append(graph)

        edit_distances = []
        for g1, g2 in combinations(nx_graphs, 2):
            edges1 = set(g1.edges())
            edges2 = set(g2.edges())
            diff = len(edges1.symmetric_difference(edges2))
            edit_distances.append(diff)

        if edit_distances:
            mean_edit_distance = sum(edit_distances) / len(edit_distances)
            reasoning = (
                f"Mean edit distance across {len(nx_graphs)} graphs "
                f"({len(edit_distances)} pairwise comparisons)"
            )
        elif len(nx_graphs) < 2:
            mean_edit_distance = 0.0
            reasoning = "Not enough executions to compute (need at least 2 sessions)."
        else:
            mean_edit_distance = 0.0
            reasoning = "No valid graph transitions found in any session."

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=mean_edit_distance,
            metric_class=self.ontology_class,
            reasoning=reasoning,
            metadata={
                "total_graphs": len(nx_graphs),
                "pairwise_comparisons": len(edit_distances),
                "edit_distances": edit_distances,
                "entities_involved": list(set(entities_involved)),
            },
        )
