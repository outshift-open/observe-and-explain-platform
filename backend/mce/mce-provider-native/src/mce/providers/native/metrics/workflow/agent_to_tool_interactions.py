#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from collections import Counter
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry


class AgentToToolInteractions(Metric):
    """Collects agent-to-tool interaction counts."""

    metadata = SpecRegistry.require("AgentToToolInteractions").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            required_entities=["mas:ToolCall"], include_edges=True
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        tool_spans = context.get("tool_spans", [])
        session = context.get("session")
        if session:
            tool_spans = getattr(session, "tool_spans", tool_spans)

        transitions: list[str] = []
        for span in tool_spans:
            if isinstance(span, dict):
                workflow_name = span.get("agent_id") or span.get("workflow.name")
                tool_name = span.get("toolName") or span.get("tool_name")
            else:
                workflow_name = getattr(span, "agent_id", None)
                tool_name = getattr(span, "toolName", None) or getattr(
                    span, "tool_name", None
                )

            if not workflow_name or not tool_name:
                continue
            transitions.append(f"(Agent: {workflow_name}) -> (Tool: {tool_name})")

        counts = Counter(transitions)
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=len(transitions),
            metric_class=self.ontology_class,
            metadata={
                "total_tool_calls": len(transitions),
                "unique_interactions": len(counts),
                "interaction_counts": dict(counts),
            },
        )
