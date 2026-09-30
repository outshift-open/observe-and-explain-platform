#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry


class CyclesCount(Metric):
    """Counts contiguous cycles in agent and tool interactions."""

    metadata = SpecRegistry.require("CyclesCount").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            required_entities=["mas:AgentCall", "mas:ToolCall"], include_edges=True
        )

    def count_contiguous_cycles(self, seq: list[str], min_cycle_len: int = 2) -> int:
        """Count contiguous cycles in a sequence of identifiers."""
        n = len(seq)
        cycle_count = 0
        i = 0
        while i < n:
            found_cycle = False
            for k in range(min_cycle_len, (n - i) // 2 + 1):
                if seq[i : i + k] == seq[i + k : i + 2 * k]:
                    cycle_count += 1
                    found_cycle = True
                    i += k
                    break
            if not found_cycle:
                i += 1
        return cycle_count

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        spans = context.get("spans", [])
        session = context.get("session")
        if session:
            spans = getattr(session, "spans", []) or spans

        # Fallback to separate lists if spans main list is empty
        if not spans:
            spans = (context.get("agent_spans", []) or []) + (
                context.get("tool_spans", []) or []
            )

        events: list[str] = []
        for span in spans:
            if isinstance(span, dict):
                entity_name = (
                    span.get("toolName")
                    or span.get("agentName")
                    or span.get("tool_name")
                    or span.get("agent_id")
                )
            else:
                entity_name = (
                    getattr(span, "toolName", None)
                    or getattr(span, "agentName", None)
                    or getattr(span, "tool_name", None)
                    or getattr(span, "agent_id", None)
                )

            if entity_name:
                events.append(str(entity_name))

        cycle_count = self.count_contiguous_cycles(events)
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=cycle_count,
            metric_class=self.ontology_class,
            reasoning="Count of contiguous cycles in agent and tool interactions",
            metadata={
                "event_sequence": events,
                "total_events": len(events),
            },
        )
