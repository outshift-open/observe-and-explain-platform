#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from collections import Counter
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics.workflow.workflow_efficiency_workaround import (
    collapse_duplicate_agent_calls,
)


def _agent_name(agent_call: Any) -> str | None:
    if isinstance(agent_call, dict):
        return (
            agent_call.get("agentName")
            or agent_call.get("name")
            or agent_call.get("agent_id")
            or agent_call.get("id")
            or agent_call.get("executionId")
        )
    return (
        getattr(agent_call, "agentName", None)
        or getattr(agent_call, "name", None)
        or getattr(agent_call, "agent_id", None)
        or getattr(agent_call, "id", None)
        or getattr(agent_call, "executionId", None)
    )


def _derive_transitions(agent_calls: list[Any]) -> list[str]:
    # WORKAROUND: keep transition counts aligned with WorkflowEfficiency on
    # legacy graphs that duplicate one logical step as task/call AgentCalls.
    agent_calls = collapse_duplicate_agent_calls(agent_calls, _agent_name)
    names = [
        name for name in (_agent_name(agent_call) for agent_call in agent_calls) if name
    ]
    return [f"{left}->{right}" for left, right in zip(names, names[1:])]


class AgentToAgentInteractions(Metric):
    """Collects directed transitions from the ordered AgentCall sequence.

    Includes the same temporary legacy-KG workaround as WorkflowEfficiency so
    duplicated ``*_task_*`` / ``*_call_*`` AgentCall pairs do not inflate
    interaction counts.
    """

    metadata = SpecRegistry.require("AgentToAgentInteractions").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return SpecRegistry.require("AgentToAgentInteractions").input_requirements

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        agent_calls = context.get("agent_calls", [])

        session = context.get("session")
        if session:
            agent_calls = getattr(session, "agent_calls", agent_calls)

        transitions = _derive_transitions(agent_calls)
        counts = Counter(transitions)

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=len(transitions),
            metric_class=self.ontology_class,
            metadata={
                "total_transitions": len(transitions),
                "unique_transitions": len(counts),
                "transition_counts": dict(counts),
                "all_transitions": list(transitions),
            },
        )
